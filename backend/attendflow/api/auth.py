"""Employee session authentication and the session-mode authorization dependency."""

from __future__ import annotations

import hmac
import logging
import os
import re
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from ipaddress import ip_address
from pathlib import Path
from secrets import token_urlsafe
from tempfile import gettempdir
from threading import Lock
from time import monotonic
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import delete, func, select
from sqlalchemy.orm import undefer

from attendflow.config import Settings
from attendflow.data.schemas import EmployeeRole
from attendflow.db.credentials import (
    dummy_password_hash,
    normalize_email,
    valid_email,
    verify_password,
)
from attendflow.db.models import AuthSessionRow, EmployeeRow
from attendflow.errors import ForbiddenError, NotFoundError, RateLimitedError, UnauthorizedError

COOKIE = "attendflow_session"
SESSION_AGE = timedelta(hours=8)
WORKER = "worker"
SUPERVISOR = "supervisor"
ADMIN = "payroll_admin"
REVIEWERS = (SUPERVISOR, ADMIN)

log = logging.getLogger("attendflow.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: Annotated[str, Field(max_length=254)]
    password: Annotated[SecretStr, Field(max_length=1024)]


class EmployeeIdentity(BaseModel):
    id: str
    name: str
    role: EmployeeRole


class AuthState(BaseModel):
    mode: Literal["header", "session"]
    employee: EmployeeIdentity | None
    demo_accounts: bool


class LogoutOut(BaseModel):
    ok: bool


@dataclass
class FailureWindow:
    started: float
    count: int = 1
    locked_until: float = 0


def _signature(secret: str, text: str) -> str:
    return hmac.digest(secret.encode(), text.encode(), "sha256").hex()


def _unlock_path(secret: str, kind: str, value: str) -> Path:
    scope = _signature(secret, "unlock-directory")[:24]
    folder = Path(gettempdir()) / f"attendflow-auth-{os.getuid()}-{scope}"
    folder.mkdir(mode=0o700, exist_ok=True)
    status = folder.lstat()
    if not stat.S_ISDIR(status.st_mode) or status.st_uid != os.getuid() or status.st_mode & 0o077:
        raise RuntimeError("The auth unlock directory must be private to the app user")
    return folder / _signature(secret, f"unlock:{kind}:{value}")


def unlock_login(secret: str, kind: str, value: str) -> None:
    """Queue an unlock for the running app without exposing an HTTP control endpoint."""
    _unlock_path(secret, kind, value).touch(mode=0o600)


class LoginThrottle:
    ATTEMPTS = 5
    WINDOW = 600

    def __init__(self, secret: str):
        self.secret = secret
        self.entries: dict[tuple[str, str], FailureWindow] = {}
        self.lock = Lock()
        self.next_prune = 0.0

    def __enter__(self):
        self.lock.acquire()
        return self

    def __exit__(self, *_):
        self.lock.release()

    def blocked(self, keys: tuple[tuple[str, str], ...], now: float) -> bool:
        if now >= self.next_prune:
            self.entries = {
                key: entry
                for key, entry in self.entries.items()
                if max(entry.started + self.WINDOW, entry.locked_until) > now
            }
            self.next_prune = now + 60
        blocked = False
        for key in keys:
            marker = _unlock_path(self.secret, *key)
            try:
                marker.unlink()
            except FileNotFoundError:
                pass
            else:
                self.entries.pop(key, None)
            entry = self.entries.get(key)
            blocked |= entry is not None and entry.locked_until > now
        return blocked

    def fail(self, keys: tuple[tuple[str, str], ...], now: float) -> None:
        for key in keys:
            entry = self.entries.get(key)
            if entry is None or entry.started + self.WINDOW <= now:
                self.entries[key] = FailureWindow(now)
            else:
                entry.count += 1
                if entry.count >= self.ATTEMPTS:
                    entry.locked_until = now + self.WINDOW


def _client_ip(request: Request, settings: Settings) -> str:
    if settings.trusted_proxy:
        # Traefik is the one trusted hop and appends the address it received the request from.
        chain = request.headers.getlist("x-forwarded-for")
        forwarded = chain[-1].rsplit(",", 1)[-1].strip() if chain else ""
        try:
            return str(ip_address(forwarded))
        except ValueError:
            pass
    return request.client.host if request.client else "unknown"


def _token_hash(request: Request) -> str | None:
    cookie = request.cookies.get(COOKIE, "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}\.[0-9a-f]{64}", cookie):
        return None
    token, signature = cookie.split(".")
    expected = _signature(request.app.state.settings.session_secret, f"session:{token}")
    if not hmac.compare_digest(signature, expected):
        return None
    return sha256(token.encode()).hexdigest()


def session_identity(request: Request) -> EmployeeIdentity:
    cached = getattr(request.state, "employee", None)
    if cached is not None:
        return cached
    token_hash = _token_hash(request)
    if token_hash:
        with request.app.state.session_factory() as session:
            employee = session.scalar(
                select(EmployeeRow)
                .join(AuthSessionRow)
                .where(
                    AuthSessionRow.token_hash == token_hash,
                    AuthSessionRow.expires_at > datetime.now(UTC),
                )
            )
            if employee is not None:
                identity = EmployeeIdentity(
                    id=employee.employee_id, name=employee.name, role=employee.role
                )
                request.state.employee = identity
                return identity
    raise UnauthorizedError(
        "Sign in to continue",
        code="login_required",
        details={"demo_accounts": request.app.state.settings.demo_mode},
    )


def require_session(request: Request) -> None:
    if request.app.state.settings.auth_mode == "session":
        session_identity(request)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            require_browser_origin(request)


def require_roles(*roles: str):
    """Apply a role gate in session mode. Header-mode services retain their own checks."""

    def guard(request: Request) -> None:
        if request.app.state.settings.auth_mode == "session":
            employee = session_identity(request)
            if employee.role not in roles:
                raise ForbiddenError("This role cannot access the endpoint", code="role_forbidden")

    return Depends(guard)


def resolve_actor(
    request: Request,
    actor: Annotated[
        str | None,
        Header(alias="X-Actor-Id", description="Employee ID for header-mode requests only"),
    ] = None,
) -> str:
    if request.app.state.settings.auth_mode == "session":
        return session_identity(request).id
    if actor is not None and re.fullmatch(r"E[0-9]{3}", actor):
        return actor
    raise RequestValidationError(
        [
            {
                "loc": ("header", "X-Actor-Id"),
                "msg": "Field required" if actor is None else "Invalid employee ID",
                "type": "missing" if actor is None else "string_pattern_mismatch",
            }
        ]
    )


ActorId = Annotated[str, Depends(resolve_actor)]


def _browser_origin_allowed(request: Request) -> bool:
    try:
        origin = urlsplit(request.headers.get("origin", ""))
        return (
            origin.scheme in {"http", "https"}
            and bool(origin.hostname)
            and not (
                origin.username or origin.password or origin.path or origin.query or origin.fragment
            )
            and origin.netloc.lower() == request.headers.get("host", "").lower()
        )
    except ValueError:
        return False


def require_browser_origin(request: Request) -> None:
    if not _browser_origin_allowed(request):
        raise ForbiddenError("Use the application origin", code="cross_origin_write")


def _session_mode(request: Request) -> Settings:
    settings = request.app.state.settings
    if settings.auth_mode != "session":
        raise NotFoundError("Session authentication is disabled")
    return settings


@router.post("/login", response_model=AuthState)
def login(body: LoginIn, request: Request, response: Response):
    settings = _session_mode(request)
    require_browser_origin(request)
    email = normalize_email(body.email)
    keys = (("email", email), ("ip", _client_ip(request, settings)))
    throttle = request.app.state.login_throttle
    # Serialize the check and verification so a burst cannot bypass the failed-attempt limit.
    with throttle:
        if throttle.blocked(keys, monotonic()):
            log.warning("login blocked", extra={"event": "login_blocked"})
            raise RateLimitedError("Too many attempts. Try again later.", code="locked")
        with request.app.state.session_factory.begin() as session:
            employee = (
                session.scalar(
                    select(EmployeeRow)
                    .options(undefer(EmployeeRow.password_hash))
                    .where(func.lower(EmployeeRow.email) == email)
                    .with_for_update()
                )
                if valid_email(email)
                else None
            )
            stored = employee.password_hash if employee else None
            verified = verify_password(
                stored or dummy_password_hash(), body.password.get_secret_value()
            )
            if not stored or not verified:
                throttle.fail(keys, monotonic())
                log.warning("login failed", extra={"event": "login_failed"})
                raise UnauthorizedError("Invalid email or password", code="invalid_credentials")
            throttle.entries.pop(keys[0], None)
            now = datetime.now(UTC)
            token = token_urlsafe(32)
            session.execute(delete(AuthSessionRow).where(AuthSessionRow.expires_at <= now))
            previous_token = _token_hash(request)
            if previous_token:
                session.execute(
                    delete(AuthSessionRow).where(
                        AuthSessionRow.token_hash == previous_token,
                        AuthSessionRow.employee_id == employee.employee_id,
                    )
                )
            session.add(
                AuthSessionRow(
                    token_hash=sha256(token.encode()).hexdigest(),
                    employee_id=employee.employee_id,
                    expires_at=now + SESSION_AGE,
                )
            )
            identity = EmployeeIdentity(
                id=employee.employee_id, name=employee.name, role=employee.role
            )
    signature = _signature(settings.session_secret, f"session:{token}")
    response.set_cookie(
        COOKIE,
        f"{token}.{signature}",
        max_age=int(SESSION_AGE.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    log.info("login succeeded", extra={"event": "login_succeeded", "actor_id": identity.id})
    return AuthState(mode="session", employee=identity, demo_accounts=settings.demo_mode)


@router.get("/me", response_model=AuthState)
def me(request: Request):
    settings = request.app.state.settings
    if settings.auth_mode == "header":
        return AuthState(mode="header", employee=None, demo_accounts=False)
    return AuthState(
        mode="session", employee=session_identity(request), demo_accounts=settings.demo_mode
    )


@router.post("/logout", response_model=LogoutOut)
def logout(request: Request, response: Response):
    settings = _session_mode(request)
    session_identity(request)
    require_browser_origin(request)
    with request.app.state.session_factory.begin() as session:
        session.execute(
            delete(AuthSessionRow).where(AuthSessionRow.token_hash == _token_hash(request))
        )
    response.delete_cookie(COOKIE, secure=settings.cookie_secure, httponly=True, samesite="lax")
    return LogoutOut(ok=True)
