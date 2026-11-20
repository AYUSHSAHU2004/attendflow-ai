"""Runtime settings, read from environment variables (and .env if present)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AS_OF = "2026-04-16T08:00:00"
DEFAULT_OVERTIME_WARNING_MARGIN_HOURS = 4.0
DEFAULT_DATABASE_URL = "postgresql+psycopg://attendflow:attendflow@localhost:5433/attendflow"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def normalize_database_url(value: str) -> str:
    scheme, separator, rest = value.partition("://")
    if separator and scheme in {"postgres", "postgresql"}:
        return f"postgresql+psycopg://{rest}"
    return value


def _strong_secret(value: str | None) -> bool:
    return bool(
        value
        and len(value) >= 32
        and value.isascii()
        and value.isprintable()
        and not any(char.isspace() for char in value)
        and len(set(value)) >= 10
    )


def _llm_api_key() -> str | None:
    key = os.getenv("LLM_API_KEY") or None
    filename = os.getenv("LLM_API_KEY_FILE")
    if not filename:
        return key
    if key:
        raise ValueError("Set only one of LLM_API_KEY and LLM_API_KEY_FILE")
    try:
        value = Path(filename).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        raise ValueError("LLM_API_KEY_FILE must be a readable runtime secret file") from None
    if not value:
        raise ValueError("LLM_API_KEY_FILE is empty")
    return value


def parse_local_timestamp(value: str) -> datetime:
    """Parse a plain local ISO timestamp. Timezone offsets are rejected on purpose:
    all times in this project are wall-clock times, so we never depend on server timezone."""
    ts = datetime.fromisoformat(value)
    if ts.tzinfo is not None:
        raise ValueError(f"timestamp must not carry a timezone offset: {value!r}")
    return ts


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    as_of: datetime
    llm_base_url: str
    llm_model: str
    llm_api_key: str | None = field(repr=False)
    llm_timeout_seconds: float
    database_url: str = field(default=DEFAULT_DATABASE_URL, repr=False)
    enable_seed: bool = True  # POST /api/seed: must be off or protected when deployed
    log_format: str = "json"  # json | text
    log_level: str = "INFO"
    llm_reasoning_effort: str = "low"
    agent_max_steps: int = 5
    llm_investigation_budget_seconds: float = 45
    llm_diagnostics: bool = True
    llm_extraction_attempts: int = 2
    # Phase 11: mock attendance device, scheduler and demo helpers.
    device_api_key: str | None = field(default=None, repr=False)  # unset = disabled
    device_max_backdate_days: int = 7
    demo_mode: bool = False  # demo-only endpoints and the /admin Simulate punch panel
    demo_extra_week: bool = False
    scheduler_enabled: bool = False
    scheduler_interval_seconds: float = 60
    scheduler_investigations_per_cycle: int = 3
    scheduler_messages_per_cycle: int = 3
    scheduler_backlog: bool = False  # also work through cases detected before the start
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    # Phase 12: kill switch. Off = detection stores P2/P7 cases open for a person.
    auto_resolve_enabled: bool = True
    # Phase 13: no-reply ladder. Hours, measured on the clock's now() (fixed unless the demo
    # clock moves). Reminder and supervisor count from the start of the worker's wait; the
    # payroll admin step counts from the moment the supervisor was brought in.
    no_reply_escalation_enabled: bool = True
    no_reply_reminder_hours: float = 8
    no_reply_supervisor_hours: float = 24
    no_reply_admin_hours: float = 24
    overtime_warning_margin_hours: float = DEFAULT_OVERTIME_WARNING_MARGIN_HOURS
    # Phase 17: the daily briefing. Off = template only (no LLM call). Limits use real time.
    briefing_enabled: bool = True
    briefing_scheduled: bool = True  # the scheduler writes Priya's briefing once a workflow day
    briefing_min_interval_seconds: float = 300
    briefing_max_llm_calls_per_day: int = 40
    briefing_llm_deadline_seconds: float = 20
    deployed: bool = False
    demo_password: str | None = field(default=None, repr=False)
    demo_reset_enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "database_url", normalize_database_url(self.database_url))
        if self.deployed:
            self._validate_deployment()
        margin = self.overtime_warning_margin_hours
        if not isfinite(margin) or margin <= 0:
            raise ValueError("OVERTIME_WARNING_MARGIN_HOURS must be positive and finite")
        ladder = (
            self.no_reply_reminder_hours,
            self.no_reply_supervisor_hours,
            self.no_reply_admin_hours,
        )
        if not all(isfinite(h) and h > 0 for h in ladder):
            raise ValueError("NO_REPLY_*_HOURS must be positive numbers")
        if self.no_reply_reminder_hours >= self.no_reply_supervisor_hours:
            raise ValueError("NO_REPLY_REMINDER_HOURS must be less than NO_REPLY_SUPERVISOR_HOURS")
        interval = self.scheduler_interval_seconds
        if not isfinite(interval) or interval < 1:
            raise ValueError("SCHEDULER_INTERVAL_SECONDS must be at least 1")
        if self.scheduler_investigations_per_cycle < 0 or self.scheduler_messages_per_cycle < 0:
            raise ValueError("scheduler per-cycle limits must not be negative")
        if self.device_max_backdate_days < 1:
            raise ValueError("DEVICE_MAX_BACKDATE_DAYS must be positive")
        budget = self.llm_investigation_budget_seconds
        if not isfinite(budget) or budget <= 0:
            raise ValueError("LLM_INVESTIGATION_BUDGET_SECONDS must be positive and finite")
        if self.llm_extraction_attempts not in {1, 2}:
            raise ValueError("LLM_EXTRACTION_ATTEMPTS must be 1 or 2")
        interval_s = self.briefing_min_interval_seconds
        if not isfinite(interval_s) or interval_s < 0:
            raise ValueError("BRIEFING_MIN_INTERVAL_SECONDS must not be negative")
        if self.briefing_max_llm_calls_per_day < 0:
            raise ValueError("BRIEFING_MAX_LLM_CALLS_PER_DAY must not be negative")
        deadline = self.briefing_llm_deadline_seconds
        if not isfinite(deadline) or deadline <= 0:
            raise ValueError("BRIEFING_LLM_DEADLINE_SECONDS must be positive")
        if self.agent_max_steps < 1:
            raise ValueError("AGENT_MAX_STEPS must be positive")
        if self.llm_reasoning_effort not in {"off", "low", "medium", "high"}:
            raise ValueError("LLM_REASONING_EFFORT must be off, low, medium or high")

    def _validate_deployment(self) -> None:
        if not _strong_secret(self.demo_password):
            raise ValueError("ATTENDFLOW_DEMO_PASSWORD must be a strong random secret")
        if self.device_api_key is not None and not _strong_secret(self.device_api_key):
            raise ValueError("DEVICE_API_KEY must be a strong random secret or unset")
        if self.device_api_key and self.device_api_key == self.demo_password:
            raise ValueError("DEVICE_API_KEY must differ from ATTENDFLOW_DEMO_PASSWORD")
        if self.llm_diagnostics or self.log_level == "DEBUG":
            raise ValueError("Deployed mode requires LLM_DIAGNOSTICS=off and non-debug logging")
        if self.llm_api_key and self.llm_base_url.rstrip("/") != GROQ_BASE_URL:
            raise ValueError("A deployed LLM_API_KEY may only be sent to the Groq API")
        for origin in self.cors_origins:
            try:
                url = urlsplit(origin)
                valid = (
                    url.scheme == "https"
                    and url.hostname is not None
                    and not (url.path or url.query or url.fragment or url.username)
                    and url.password is None
                    and "*" not in origin
                )
            except ValueError:
                valid = False
            if not valid:
                raise ValueError("ATTENDFLOW_CORS_ORIGINS must list exact HTTPS origins")
        if self.demo_reset_enabled and not self.demo_mode:
            raise ValueError("ATTENDFLOW_DEMO_RESET_ENABLED requires ATTENDFLOW_DEMO_MODE")
        if self.demo_extra_week and not (self.demo_reset_enabled or self.enable_seed):
            raise ValueError("ATTENDFLOW_DEMO_EXTRA_WEEK requires an enabled reset or seed")
        try:
            database = make_url(self.database_url)
        except (ArgumentError, ValueError):
            raise ValueError("DATABASE_URL must be a valid PostgreSQL URL") from None
        if (
            database.drivername != "postgresql+psycopg"
            or not all((database.host, database.database, database.username, database.password))
            or database.password == "attendflow"
        ):
            raise ValueError("Deployed mode requires a non-default PostgreSQL DATABASE_URL")


def get_settings(env_file: Path | None = REPO_ROOT / ".env") -> Settings:
    """Build settings. Real environment variables win over values in .env."""
    if env_file is not None and env_file.exists():
        load_dotenv(env_file, override=False)
    deployed = _env_bool("ATTENDFLOW_DEPLOYED", default=False)
    origins = _env_list("ATTENDFLOW_CORS_ORIGINS")
    if not deployed and not origins:
        origins = ("http://localhost:5173", "http://127.0.0.1:5173")
    return Settings(
        data_dir=Path(os.getenv("ATTENDFLOW_DATA_DIR") or REPO_ROOT / "data"),
        as_of=parse_local_timestamp(os.getenv("ATTENDFLOW_AS_OF") or DEFAULT_AS_OF),
        llm_base_url=os.getenv("LLM_BASE_URL") or GROQ_BASE_URL,
        llm_model=os.getenv("LLM_MODEL") or "openai/gpt-oss-120b",
        llm_api_key=_llm_api_key(),
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS") or 30),
        database_url=os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL,
        enable_seed=_env_bool("ATTENDFLOW_ENABLE_SEED", default=not deployed),
        log_format=(os.getenv("LOG_FORMAT") or "json").lower(),
        log_level=(os.getenv("LOG_LEVEL") or "INFO").upper(),
        llm_reasoning_effort=(os.getenv("LLM_REASONING_EFFORT") or "low").lower(),
        agent_max_steps=int(os.getenv("AGENT_MAX_STEPS") or 5),
        llm_diagnostics=_env_bool("LLM_DIAGNOSTICS", default=not deployed),
        llm_extraction_attempts=int(os.getenv("LLM_EXTRACTION_ATTEMPTS") or 2),
        llm_investigation_budget_seconds=float(os.getenv("LLM_INVESTIGATION_BUDGET_SECONDS") or 45),
        device_api_key=os.getenv("DEVICE_API_KEY") or None,
        device_max_backdate_days=int(os.getenv("DEVICE_MAX_BACKDATE_DAYS") or 7),
        demo_mode=_env_bool("ATTENDFLOW_DEMO_MODE", default=False),
        demo_extra_week=_env_bool("ATTENDFLOW_DEMO_EXTRA_WEEK", default=False),
        scheduler_enabled=_env_bool("SCHEDULER_ENABLED", default=False),
        scheduler_interval_seconds=float(os.getenv("SCHEDULER_INTERVAL_SECONDS") or 60),
        scheduler_investigations_per_cycle=int(
            os.getenv("SCHEDULER_INVESTIGATIONS_PER_CYCLE") or 3
        ),
        scheduler_messages_per_cycle=int(os.getenv("SCHEDULER_MESSAGES_PER_CYCLE") or 3),
        scheduler_backlog=_env_bool("SCHEDULER_BACKLOG", default=False),
        cors_origins=origins,
        auto_resolve_enabled=_env_bool("AUTO_RESOLVE_ENABLED", default=True),
        no_reply_escalation_enabled=_env_bool("NO_REPLY_ESCALATION_ENABLED", default=True),
        no_reply_reminder_hours=float(os.getenv("NO_REPLY_REMINDER_HOURS") or 8),
        no_reply_supervisor_hours=float(os.getenv("NO_REPLY_SUPERVISOR_HOURS") or 24),
        no_reply_admin_hours=float(os.getenv("NO_REPLY_ADMIN_HOURS") or 24),
        overtime_warning_margin_hours=float(
            os.getenv("OVERTIME_WARNING_MARGIN_HOURS") or DEFAULT_OVERTIME_WARNING_MARGIN_HOURS
        ),
        briefing_enabled=_env_bool("BRIEFING_ENABLED", default=True),
        briefing_scheduled=_env_bool("BRIEFING_SCHEDULED", default=True),
        briefing_min_interval_seconds=float(os.getenv("BRIEFING_MIN_INTERVAL_SECONDS") or 300),
        briefing_max_llm_calls_per_day=int(os.getenv("BRIEFING_MAX_LLM_CALLS_PER_DAY") or 40),
        briefing_llm_deadline_seconds=float(os.getenv("BRIEFING_LLM_DEADLINE_SECONDS") or 20),
        deployed=deployed,
        demo_password=os.getenv("ATTENDFLOW_DEMO_PASSWORD") or None,
        demo_reset_enabled=_env_bool("ATTENDFLOW_DEMO_RESET_ENABLED", default=not deployed),
    )


def _env_list(name: str) -> tuple[str, ...]:
    raw = os.getenv(name) or ""
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"{name} must be true or false, got {raw!r}")
