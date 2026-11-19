FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src ./src
RUN npm run build && ls dist/assets/*.js >/dev/null \
    && ! grep -Eq 'URLSearchParams|Neha|http://localhost:8000' dist/assets/*.js

FROM python:3.12-slim-bookworm AS app
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 ATTENDFLOW_DEPLOYED=true PORT=10000
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/attendflow ./backend/attendflow
RUN uv sync --locked --no-dev
COPY alembic.ini ./
COPY data/*.csv data/policy.json data/policy.md ./data/
COPY --from=frontend /build/dist ./frontend/dist
COPY scripts/start-deployed.sh ./scripts/start-deployed.sh
RUN useradd --system --no-create-home --uid 10001 attendflow
USER 10001
EXPOSE 10000
CMD ["sh", "./scripts/start-deployed.sh"]
