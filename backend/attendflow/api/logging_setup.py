"""Structured logging: one JSON object per line (or readable text with LOG_FORMAT=text).

Log timestamps are real UTC time (when the server did something), unlike business times,
which come from the demo clock. Every line written while handling a request carries its
request_id, which is also returned in the X-Request-ID header.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_STANDARD = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "request_id",
}


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def _extras(record: logging.LogRecord) -> dict:
    return {k: v for k, v in record.__dict__.items() if k not in _STANDARD}


def _ts(record: logging.LogRecord) -> str:
    return datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": _ts(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.request_id:
            data["request_id"] = record.request_id
        data.update(_extras(record))
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        extras = " ".join(f"{k}={v}" for k, v in _extras(record).items())
        rid = f" [{record.request_id}]" if record.request_id else ""
        line = f"{_ts(record)} {record.levelname:<5} {record.name}{rid} {record.getMessage()}"
        line = f"{line} {extras}".rstrip()
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


class RedactingFormatter(logging.Formatter):
    def __init__(self, formatter: logging.Formatter, secrets: tuple[str, ...]):
        super().__init__()
        self.formatter = formatter
        self.forms = sorted(
            {form for secret in secrets for form in (secret, json.dumps(secret)[1:-1])},
            key=len,
            reverse=True,
        )

    def format(self, record: logging.LogRecord) -> str:
        line = self.formatter.format(record)
        for form in self.forms:
            line = line.replace(form, "[redacted]")
        return line


def configure_logging(
    fmt: str = "json",
    level: str = "INFO",
    *,
    secrets: tuple[str, ...] = (),
) -> None:
    handler = logging.StreamHandler(sys.stdout)
    formatter = TextFormatter() if fmt == "text" else JsonFormatter()
    handler.setFormatter(RedactingFormatter(formatter, secrets) if secrets else formatter)
    handler.addFilter(_RequestIdFilter())
    for name in ("attendflow", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.setLevel(level)
        logger.propagate = False
    if secrets:
        for name in ("openai", "httpx", "httpcore", "sqlalchemy.engine"):
            logger = logging.getLogger(name)
            logger.handlers = [handler]
            logger.setLevel(logging.WARNING)
            logger.propagate = False
    # Our middleware logs every request, so uvicorn's own access log would be a duplicate.
    logging.getLogger("uvicorn.access").disabled = True
