"""FastAPI application factory, error handlers and request logging.

Run:  python -m uv run attendflow-api      (http://localhost:8000/docs)
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from attendflow import __version__
from attendflow.api.logging_setup import configure_logging, request_id_var
from attendflow.api.routes import router
from attendflow.clock import Clock, FixedClock
from attendflow.config import Settings, get_settings
from attendflow.db.session import make_engine, make_session_factory
from attendflow.errors import AppError
from attendflow.policy.models import load_policy

log = logging.getLogger("attendflow.api")

_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    415: "unsupported_media_type",
    422: "validation_error",
}


def _error(status: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details}},
    )


def _install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError):
        return _error(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        details = [
            {"loc": ".".join(str(p) for p in e["loc"]), "msg": e["msg"], "type": e["type"]}
            for e in exc.errors()
        ]
        return _error(422, "validation_error", "the request is not valid", details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        return _error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(OperationalError)
    async def db_down(_: Request, exc: OperationalError):
        log.error("database unavailable", extra={"event": "db_error", "error": str(exc.orig)})
        return _error(503, "database_unavailable", "the database cannot be reached")

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        log.exception("unhandled error", extra={"event": "unhandled_error"})
        return _error(500, "internal_error", "something went wrong; see the server log")


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_format, settings.log_level)
    engine = engine or make_engine(settings.database_url)

    app = FastAPI(
        title="AttendFlow AI",
        version=__version__,
        description=(
            "Finds timecard exceptions with a deterministic rule engine and routes each one "
            "to a human for a decision. Fixes are applied by code only after approval, in "
            "one transaction with the audit row. Acting endpoints need an `X-Actor-Id` header "
            "(no login yet): E101 Ravi, E102 Sunita (supervisors), E201 Priya (payroll admin), "
            "E001 Amit (worker)."
        ),
        openapi_tags=[
            {"name": "system", "description": "Health and demo reset"},
            {"name": "detection", "description": "Run the rule engine"},
            {"name": "exceptions", "description": "Read exceptions"},
            {"name": "decisions", "description": "Human decisions (status flow)"},
            {"name": "logs", "description": "Audit log and agent tool calls"},
        ],
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.policy = load_policy(settings.data_dir / "policy.json")
    app.state.clock = clock or FixedClock(settings.as_of)
    app.state.logger = log

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            log.info(
                "request",
                extra={
                    "event": "request",
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                    "actor_id": request.headers.get("X-Actor-Id"),
                },
            )
            request_id_var.reset(token)

    _install_error_handlers(app)
    app.include_router(router)
    log.info(
        "app started",
        extra={
            "event": "startup",
            "as_of": settings.as_of.isoformat(),
            "seed_enabled": settings.enable_seed,
        },
    )
    return app


def main() -> None:
    """Console entry point: attendflow-api [--host 127.0.0.1] [--port 8000] [--reload]."""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Run the AttendFlow API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="restart on code changes")
    args = parser.parse_args()
    uvicorn.run(
        "attendflow.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_config=None,
    )
