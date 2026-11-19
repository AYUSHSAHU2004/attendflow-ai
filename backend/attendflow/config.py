"""Runtime settings, read from environment variables (and .env if present)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AS_OF = "2026-04-16T08:00:00"
DEFAULT_DATABASE_URL = "postgresql+psycopg://attendflow:attendflow@localhost:5433/attendflow"


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
    llm_api_key: str | None
    llm_timeout_seconds: float
    database_url: str = DEFAULT_DATABASE_URL
    enable_seed: bool = True  # POST /api/seed: must be off or protected when deployed
    log_format: str = "json"  # json | text
    log_level: str = "INFO"
    llm_reasoning_effort: str = "low"
    agent_max_steps: int = 5
    llm_investigation_budget_seconds: float = 45
    llm_diagnostics: bool = True
    llm_extraction_attempts: int = 2
    # Phase 11: mock attendance device, scheduler and demo helpers.
    device_api_key: str | None = None  # X-Device-Key for POST /api/punches; unset = disabled
    device_max_backdate_days: int = 7
    demo_mode: bool = False  # demo-only endpoints and the /admin Simulate punch panel
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

    def __post_init__(self) -> None:
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
        if self.agent_max_steps < 1:
            raise ValueError("AGENT_MAX_STEPS must be positive")
        if self.llm_reasoning_effort not in {"off", "low", "medium", "high"}:
            raise ValueError("LLM_REASONING_EFFORT must be off, low, medium or high")


def get_settings(env_file: Path | None = REPO_ROOT / ".env") -> Settings:
    """Build settings. Real environment variables win over values in .env."""
    if env_file is not None and env_file.exists():
        load_dotenv(env_file, override=False)
    return Settings(
        data_dir=Path(os.getenv("ATTENDFLOW_DATA_DIR") or REPO_ROOT / "data"),
        as_of=parse_local_timestamp(os.getenv("ATTENDFLOW_AS_OF") or DEFAULT_AS_OF),
        llm_base_url=os.getenv("LLM_BASE_URL") or "https://api.groq.com/openai/v1",
        llm_model=os.getenv("LLM_MODEL") or "openai/gpt-oss-120b",
        llm_api_key=os.getenv("LLM_API_KEY") or None,
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS") or 30),
        database_url=os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL,
        enable_seed=_env_bool("ATTENDFLOW_ENABLE_SEED", default=True),
        log_format=(os.getenv("LOG_FORMAT") or "json").lower(),
        log_level=(os.getenv("LOG_LEVEL") or "INFO").upper(),
        llm_reasoning_effort=(os.getenv("LLM_REASONING_EFFORT") or "low").lower(),
        agent_max_steps=int(os.getenv("AGENT_MAX_STEPS") or 5),
        llm_diagnostics=_env_bool("LLM_DIAGNOSTICS", default=True),
        llm_extraction_attempts=int(os.getenv("LLM_EXTRACTION_ATTEMPTS") or 2),
        llm_investigation_budget_seconds=float(os.getenv("LLM_INVESTIGATION_BUDGET_SECONDS") or 45),
        device_api_key=os.getenv("DEVICE_API_KEY") or None,
        device_max_backdate_days=int(os.getenv("DEVICE_MAX_BACKDATE_DAYS") or 7),
        demo_mode=_env_bool("ATTENDFLOW_DEMO_MODE", default=False),
        scheduler_enabled=_env_bool("SCHEDULER_ENABLED", default=False),
        scheduler_interval_seconds=float(os.getenv("SCHEDULER_INTERVAL_SECONDS") or 60),
        scheduler_investigations_per_cycle=int(
            os.getenv("SCHEDULER_INVESTIGATIONS_PER_CYCLE") or 3
        ),
        scheduler_messages_per_cycle=int(os.getenv("SCHEDULER_MESSAGES_PER_CYCLE") or 3),
        scheduler_backlog=_env_bool("SCHEDULER_BACKLOG", default=False),
        cors_origins=_env_list("ATTENDFLOW_CORS_ORIGINS")
        or ("http://localhost:5173", "http://127.0.0.1:5173"),
        auto_resolve_enabled=_env_bool("AUTO_RESOLVE_ENABLED", default=True),
        no_reply_escalation_enabled=_env_bool("NO_REPLY_ESCALATION_ENABLED", default=True),
        no_reply_reminder_hours=float(os.getenv("NO_REPLY_REMINDER_HOURS") or 8),
        no_reply_supervisor_hours=float(os.getenv("NO_REPLY_SUPERVISOR_HOURS") or 24),
        no_reply_admin_hours=float(os.getenv("NO_REPLY_ADMIN_HOURS") or 24),
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
