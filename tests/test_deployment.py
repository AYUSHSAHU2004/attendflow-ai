"""Private deploy safety checks that do not require access to hosted services."""

import base64
import logging
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from attendflow.agent.jobs import InvestigationJobs
from attendflow.api import routes
from attendflow.api.app import create_app
from attendflow.api.deployment import log_secrets
from attendflow.api.logging_setup import JsonFormatter, RedactingFormatter
from attendflow.config import get_settings
from attendflow.scheduler import runner

PASSWORD = "F15c2aa44a925eb5297280555b5c3e1bbe498b6a"
DATABASE = "postgres://demo:private-db-value@db.example/demo?sslmode=require"


@pytest.fixture
def locked(monkeypatch):
    monkeypatch.setenv("ATTENDFLOW_DEPLOYED", "true")
    monkeypatch.setenv("ATTENDFLOW_DEMO_PASSWORD", PASSWORD)
    monkeypatch.setenv("ATTENDFLOW_SESSION_SECRET", "fixture-session-secret-" + "x" * 32)
    monkeypatch.setenv("ATTENDFLOW_AUTH_MODE", "header")
    monkeypatch.setenv("DATABASE_URL", DATABASE)
    for key in (
        "ATTENDFLOW_CORS_ORIGINS",
        "ATTENDFLOW_DEMO_MODE",
        "ATTENDFLOW_DEMO_EXTRA_WEEK",
        "ATTENDFLOW_DEMO_RESET_ENABLED",
        "ATTENDFLOW_ENABLE_SEED",
        "DEVICE_API_KEY",
        "LLM_API_KEY",
        "LLM_API_KEY_FILE",
        "LLM_DIAGNOSTICS",
        "LOG_LEVEL",
        "SCHEDULER_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)
    return get_settings(env_file=None)


@pytest.fixture
def frontend(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index.js").write_text("window.demoReady=true", encoding="utf-8")
    (tmp_path / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
def test_normalizes_managed_postgres_urls(locked, scheme):
    url = f"{scheme}://demo:percent%40value@db.example/demo?sslmode=require"
    assert replace(locked, database_url=url).database_url == (
        "postgresql+psycopg://demo:percent%40value@db.example/demo?sslmode=require"
    )


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"session_secret": None}, "ATTENDFLOW_SESSION_SECRET"),
        ({"session_secret": "short"}, "ATTENDFLOW_SESSION_SECRET"),
        ({"demo_password": None}, "ATTENDFLOW_DEMO_PASSWORD"),
        ({"demo_password": "secret"}, "ATTENDFLOW_DEMO_PASSWORD"),
        ({"device_api_key": ""}, "DEVICE_API_KEY"),
        ({"device_api_key": "test-device-key"}, "DEVICE_API_KEY"),
        ({"device_api_key": PASSWORD}, "DEVICE_API_KEY"),
        ({"llm_diagnostics": True}, "LLM_DIAGNOSTICS"),
        ({"log_level": "DEBUG"}, "non-debug logging"),
        ({"cors_origins": ("*",)}, "ATTENDFLOW_CORS_ORIGINS"),
        ({"cors_origins": ("https://*.example",)}, "ATTENDFLOW_CORS_ORIGINS"),
        (
            {"database_url": "postgresql://attendflow:attendflow@localhost/attendflow"},
            "DATABASE_URL",
        ),
        ({"database_url": "private-malformed-connection"}, "DATABASE_URL"),
        ({"demo_reset_enabled": True}, "ATTENDFLOW_DEMO_RESET_ENABLED"),
        ({"demo_extra_week": True}, "ATTENDFLOW_DEMO_EXTRA_WEEK"),
        (
            {"llm_api_key": "private-llm-key", "llm_base_url": "https://other.example"},
            "Groq API",
        ),
    ],
)
def test_unsafe_deployment_settings_are_refused(locked, change, error):
    with pytest.raises(ValueError, match=error) as exc:
        replace(locked, **change)
    assert "private-" not in str(exc.value)
    assert PASSWORD not in str(exc.value)


def test_reads_the_model_key_from_a_runtime_secret_file(locked, tmp_path, monkeypatch):
    secret = tmp_path / "groq-key"
    secret.write_text("private-llm-key\n", encoding="utf-8")
    monkeypatch.setenv("LLM_API_KEY_FILE", str(secret))
    settings = get_settings(env_file=None)
    assert settings.llm_api_key == "private-llm-key"
    assert "private-llm-key" not in repr(settings)
    monkeypatch.setenv("LLM_API_KEY", "another-secret")
    with pytest.raises(ValueError, match="Set only one"):
        get_settings(env_file=None)


def test_locked_deployment_starts_and_gates_pages_assets_and_api(locked, frontend, monkeypatch):
    assert not locked.enable_seed and not locked.demo_mode
    assert not locked.demo_reset_enabled and not locked.demo_extra_week
    assert not locked.device_api_key and not locked.llm_diagnostics
    monkeypatch.setattr(InvestigationJobs, "recover", lambda self, **kwargs: None)
    app = create_app(locked, engine=create_engine("sqlite://"), frontend_dir=frontend)
    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200 and health.json() == {"status": "ok"}
        for path in ("/", "/assets/index.js", "/dashboard", "/api/health", "/docs"):
            response = client.get(path)
            assert response.status_code == 401
            assert response.headers["www-authenticate"].startswith("Basic ")
        assert client.get("/", auth=("demo", "wrong")).status_code == 401
        client.auth = ("demo", PASSWORD)
        for path in ("/", "/dashboard", "/supervisor/payroll", "/assets/index.js", "/api/health"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
        assert client.get("/dev").status_code == 404
        assert client.get("/api/nonexistent").status_code == 404
        assert client.post("/api/seed").json()["error"]["code"] == "seed_disabled"
        assert client.post("/api/admin/demo/reset").status_code == 404
        assert client.post("/api/admin/demo/punch").status_code == 404
        assert client.get("/api/admin/demo/clock").status_code == 404
        assert (
            client.post("/api/seed", headers={"Origin": "https://other.example"}).status_code == 403
        )


def test_healthz_reports_failure_without_database_details(locked, frontend):
    app = create_app(locked, engine=create_engine("sqlite://"), frontend_dir=frontend)

    def no_connection():
        raise OperationalError("SELECT 1", None, ValueError("private-db-error"))

    app.state.session_factory = no_connection
    response = TestClient(app).get("/healthz")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_guided_demo_exposes_only_enabled_routes_behind_gate(locked, frontend):
    settings = replace(locked, demo_mode=True, demo_reset_enabled=True, demo_extra_week=True)
    app = create_app(settings, engine=create_engine("sqlite://"), frontend_dir=frontend)
    client = TestClient(app)
    for path in ("/api/admin/demo/reset", "/api/admin/demo/punch", "/api/admin/demo/clock"):
        assert client.post(path).status_code == 401
        assert path in app.openapi()["paths"]
    assert not settings.enable_seed and not settings.device_api_key
    safe_guided = replace(settings, demo_reset_enabled=False, demo_extra_week=False)
    app = create_app(safe_guided, engine=create_engine("sqlite://"), frontend_dir=frontend)
    assert "/api/admin/demo/reset" not in app.openapi()["paths"]
    assert "/api/admin/demo/punch" in app.openapi()["paths"]


def test_private_secrets_are_redacted_from_logs(locked):
    settings = replace(locked, llm_api_key="private-llm-key")
    formatter = RedactingFormatter(JsonFormatter(), log_secrets(settings))
    authorization = base64.b64encode(f"demo:{PASSWORD}".encode()).decode()
    record = logging.LogRecord(
        "attendflow",
        logging.ERROR,
        __file__,
        1,
        "Failure %s %s %s %s",
        (settings.llm_api_key, authorization, settings.demo_password, "private-db-value"),
        None,
    )
    record.request_id = None
    line = formatter.format(record)
    assert line.count("[redacted]") == 4
    assert "private-" not in line and authorization not in line and PASSWORD not in line


def test_model_free_manual_cycle_keeps_normal_budgets(locked, frontend, monkeypatch):
    app = create_app(locked, engine=create_engine("sqlite://"), frontend_dir=frontend)
    original = app.state.scheduler.deps
    seen = []

    def capture(deps, trigger):
        seen.append((deps.settings, trigger))
        return None  # the route reports 409, so no stored cycle response is needed

    monkeypatch.setattr(runner, "run_cycle", capture)
    monkeypatch.setattr(routes, "_require_admin", lambda *args: None)
    client = TestClient(app)
    client.auth = ("demo", PASSWORD)
    assert (
        client.post(
            "/api/admin/scheduler/run-now?model_free=true", headers={"X-Actor-Id": "E201"}
        ).status_code
        == 409
    )
    [(settings, trigger)] = seen
    assert trigger == "run_now"
    assert settings.scheduler_investigations_per_cycle == settings.scheduler_messages_per_cycle == 0
    assert app.state.scheduler.deps is original
    assert original.settings.scheduler_investigations_per_cycle > 0
    assert original.settings.scheduler_messages_per_cycle > 0
