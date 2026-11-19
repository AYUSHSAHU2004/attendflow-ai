#!/bin/sh
set -eu

# This image always uses the deployment checks and shared-password gate.
export ATTENDFLOW_DEPLOYED=true
python - <<'PY'
from alembic import command
from alembic.config import Config

from attendflow.config import get_settings

try:
    settings = get_settings(env_file=None)
except ValueError as error:
    # Only show the setting issue, with no underlying exception or traceback.
    raise SystemExit(f"Deployment settings rejected: {error}") from None

config = Config("alembic.ini")
config.attributes["database_url"] = settings.database_url
try:
    command.upgrade(config, "head")
except Exception as error:
    raise SystemExit(
        f"Database migration failed ({type(error).__name__}). "
        "Check DATABASE_URL, network access, and schema permissions."
    ) from None
PY
exec uvicorn attendflow.api.app:create_app --factory --host 0.0.0.0 \
  --port "${PORT:-10000}" --workers 1 --no-access-log
