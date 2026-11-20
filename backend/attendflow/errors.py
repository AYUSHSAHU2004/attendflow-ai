"""Domain errors. The API turns each one into the same JSON error shape:
{"error": {"code": ..., "message": ..., "details": ...}} with the HTTP status below."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, details: Any = None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class ConflictError(AppError):
    """The request is valid, but the current state does not allow it."""

    status_code = 409
    code = "conflict"


class InvalidTransitionError(ConflictError):
    code = "invalid_transition"


class InvalidFixError(AppError):
    """The chosen fix option or its params are not acceptable."""

    status_code = 422
    code = "invalid_fix"


class InvalidInputError(AppError):
    """Well-formed input that the business rules refuse (unknown worker, future time...)."""

    status_code = 422
    code = "invalid_input"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"


class RateLimitedError(AppError):
    """Too soon or over a budget (Phase 17 briefing refresh). details.retry_after_seconds."""

    status_code = 429
    code = "rate_limited"
