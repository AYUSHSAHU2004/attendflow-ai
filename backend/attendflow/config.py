"""Runtime settings, read from environment variables (and .env if present)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
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
    )


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
