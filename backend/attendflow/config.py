"""Runtime settings, read from environment variables (and .env if present)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AS_OF = "2026-04-16T08:00:00"


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
    )
