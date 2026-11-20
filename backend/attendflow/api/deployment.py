"""Shared-password access and static frontend for the temporary synthetic demo."""

from base64 import b64encode
from pathlib import Path
from secrets import compare_digest

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from starlette.staticfiles import StaticFiles

from attendflow.api.auth import session_identity
from attendflow.config import DEFAULT_DATABASE_URL, Settings
from attendflow.errors import UnauthorizedError

DEMO_USER = "demo"
PAGES = (
    "/",
    "/login",
    "/admin",
    "/dashboard",
    "/supervisor",
    "/supervisor/dashboard",
    "/activity",
    "/payroll",
    "/supervisor/payroll",
)


def _credentials(settings: Settings) -> bytes:
    return b64encode(f"{DEMO_USER}:{settings.demo_password}".encode("ascii"))


def log_secrets(settings: Settings) -> tuple[str, ...]:
    return tuple(
        value
        for value in (
            settings.demo_password,
            _credentials(settings).decode("ascii")
            if settings.deployed and settings.auth_mode == "header"
            else None,
            settings.session_secret,
            settings.device_api_key,
            settings.llm_api_key,
            settings.database_url,
            make_url(settings.database_url).password
            if settings.database_url != DEFAULT_DATABASE_URL
            else None,
        )
        if value
    )


def install_health(app: FastAPI) -> None:
    @app.get("/healthz", include_in_schema=False)
    def healthz(request: Request):
        try:
            with request.app.state.session_factory() as session:
                session.scalar(text("SELECT 1"))
        except SQLAlchemyError:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {"status": "ok"}


def _browser_write_allowed(request: Request) -> bool:
    if request.headers.get("sec-fetch-site") in {"cross-site", "same-site"}:
        return False
    origin = request.headers.get("origin")
    if origin is None:
        return True  # CLI callers may omit Origin and are still authenticated.
    host = request.headers.get("host", "")
    if origin == f"https://{host}":
        return True
    return request.url.hostname in {"localhost", "127.0.0.1", "::1"} and origin == f"http://{host}"


def install_private_demo(app: FastAPI, settings: Settings, frontend: Path) -> None:
    index = frontend / "index.html"
    if not index.is_file() or not (frontend / "assets").is_dir():
        raise RuntimeError("Deployed mode requires a built frontend (frontend/dist)")
    legacy = settings.auth_mode == "header"
    expected = _credentials(settings) if legacy else b""

    @app.middleware("http")
    async def private_demo(request: Request, call_next):
        scheme, _, credentials = request.headers.get("authorization", "").partition(" ")
        if (
            legacy
            and request.url.path != "/healthz"
            and (
                scheme.lower() != "basic"
                or not compare_digest(credentials.encode("utf-8"), expected)
            )
        ):
            response = JSONResponse(
                {"error": {"code": "demo_auth_required", "message": "Demo password required"}},
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="AttendFlow demo"'},
            )
        elif (
            legacy
            and request.method not in {"GET", "HEAD", "OPTIONS"}
            and not _browser_write_allowed(request)
        ):
            response = JSONResponse(
                {"error": {"code": "cross_origin_write", "message": "Use the demo origin"}},
                status_code=403,
            )
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="frontend_assets")

    def page(request: Request):
        if not legacy and request.url.path != "/login":
            try:
                session_identity(request)
            except UnauthorizedError:
                return RedirectResponse("/login", status_code=303)
        return FileResponse(index)

    for path in PAGES:
        app.add_api_route(path, page, methods=["GET", "HEAD"], include_in_schema=False)
