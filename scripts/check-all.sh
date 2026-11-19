#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
uv run ruff check .
uv run ruff format --check .
uv run attendflow-validate
uv run attendflow-autonomy --check
REQUIRE_DB=1 uv run pytest

cd frontend
prior_types=$(mktemp)
trap 'rm -f -- "$prior_types"' EXIT
cp src/api.generated.ts "$prior_types"
npm run api:generate
if ! cmp -s "$prior_types" src/api.generated.ts; then
  cp "$prior_types" src/api.generated.ts
  echo 'OpenAPI types are out of date. Run npm run api:generate in frontend/.' >&2
  exit 1
fi
npm run api:check
npm test
npm run typecheck
npm run build
