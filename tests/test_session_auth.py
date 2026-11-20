"""Session auth against the migrated PostgreSQL schema with the production ASGI app."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_hex

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from attendflow.api.app import create_app
from attendflow.api.auth import COOKIE
from attendflow.cases import service
from attendflow.db.models import AuditLogRow, AuthSessionRow, EmployeeRow
from attendflow.db.seed import seed_demo_once, seed_from_csv
from attendflow.scripts import auth_cli
from tests.conftest import make_api_settings

PASSWORD = "synthetic test passphrase"
ORIGIN = "https://testserver"
PASSWORD_AFTER_RESET = "different synthetic test passphrase"


@pytest.fixture(scope="module")
def demo_db(db_engine):
    settings = make_api_settings(
        db_engine,
        auth_mode="session",
        session_secret=token_hex(32),
        demo_password=PASSWORD,
        cookie_secure=True,
        demo_mode=True,
        demo_reset_enabled=True,
        qa_enabled=False,
    )
    app = create_app(settings, engine=db_engine)
    with app.state.session_factory() as session:
        with session.begin():
            seed_from_csv(session, settings.data_dir, demo_password=PASSWORD)
        service.run_detection(session, app.state.policy, app.state.clock)
    return db_engine, settings


@pytest.fixture
def app(demo_db):
    engine, settings = demo_db
    return create_app(replace(settings, session_secret=token_hex(32)), engine=engine)


def client_for(app, *, socket_ip="127.0.0.1"):
    return TestClient(app, base_url=ORIGIN, client=(socket_ip, 12345))


def login(client, name="amit", password=PASSWORD, *, origin=ORIGIN, headers=None):
    email = name if "@" in name else f"{name}@demo.attendflow.test"
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers={"Origin": origin, **(headers or {})},
    )


def cookie(client):
    return client.cookies.get(COOKIE)


def test_login_cookie_ignores_header_tampering_and_logout_revokes(app):
    client = client_for(app)
    with app.state.session_factory() as session:
        audit_start = session.scalar(select(func.count()).select_from(AuditLogRow))
        employee = session.get(EmployeeRow, "E001")
        assert employee.password_hash.startswith("$argon2")
        assert PASSWORD not in employee.password_hash
    assert client.get("/api/auth/me").status_code == 401
    result = login(client, "  AMIT@Demo.AttendFlow.Test ")
    assert result.status_code == 200
    assert result.json()["employee"] == {"id": "E001", "name": "Amit Verma", "role": "worker"}
    assert result.json()["demo_accounts"] is True
    flags = result.headers["set-cookie"]
    for attribute in ("HttpOnly", "Secure", "SameSite=lax", "Max-Age=28800", "Path=/"):
        assert attribute in flags
    original = cookie(client)
    for actor in ("E201", "invalid-header"):
        assert client.get("/api/auth/me", headers={"X-Actor-Id": actor}).json() == result.json()
        assert client.get("/api/worker/messages", headers={"X-Actor-Id": actor}).status_code == 200
        assert client.get("/api/dashboard", headers={"X-Actor-Id": actor}).status_code == 403
    bad = original[:-1] + ("a" if original[-1] != "a" else "b")
    other = client_for(app)
    assert other.get("/api/auth/me", headers={"Cookie": f"{COOKIE}={bad}"}).status_code == 401
    logout = client.post("/api/auth/logout", headers={"Origin": ORIGIN})
    assert logout.status_code == 200
    assert "Max-Age=0" in logout.headers["set-cookie"]
    assert other.get("/api/auth/me", headers={"Cookie": f"{COOKIE}={original}"}).status_code == 401
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(AuditLogRow)) == audit_start


def test_login_failure_and_origin_host_validation(app, capsys):
    app = create_app(replace(app.state.settings, log_level="INFO"), engine=app.state.engine)
    client = client_for(app)
    assert login(client, origin="https://other.example").status_code == 403
    assert login(client, origin="null").status_code == 403
    invalid = "deliberately wrong password"
    wrong = login(client, password=invalid)
    missing = login(client, "unknown", invalid)
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json() == missing.json()
    assert login(client, origin="http://testserver").status_code == 200
    current_cookie = cookie(client)
    assert client.post("/api/auth/logout").status_code == 403
    assert (
        client.post("/api/auth/logout", headers={"Origin": "https://testserver:444"}).status_code
        == 403
    )
    assert client.post("/api/auth/logout", headers={"Origin": ORIGIN}).status_code == 200
    logged = capsys.readouterr().out
    assert "login_failed" in logged and "login_succeeded" in logged
    assert invalid not in logged and PASSWORD not in logged and current_cookie not in logged


def test_expiry_and_secure_flag_from_config(app):
    settings = replace(app.state.settings, cookie_secure=False)
    app = create_app(settings, engine=app.state.engine)
    client = client_for(app)
    response = login(client)
    assert response.status_code == 200 and "Secure" not in response.headers["set-cookie"]
    token, _ = cookie(client).split(".")
    digest = sha256(token.encode()).hexdigest()
    with app.state.session_factory.begin() as session:
        assert session.get(AuthSessionRow, digest).expires_at > datetime.now(UTC) + timedelta(
            hours=7
        )
        session.execute(
            update(AuthSessionRow)
            .where(AuthSessionRow.token_hash == digest)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("trusted", [False, True])
def test_email_and_ip_lockouts_and_cli_unlock(app, trusted, monkeypatch):
    settings = replace(app.state.settings, trusted_proxy=trusted)
    app = create_app(settings, engine=app.state.engine)
    client = client_for(app)
    forwarded = {"X-Forwarded-For": "192.0.2.9, 192.0.2.10"}
    for index in range(5):
        assert login(client, f"missing{index}", "wrong", headers=forwarded).status_code == 401
    assert login(client, headers=forwarded).status_code == 429
    changed_header = {"X-Forwarded-For": "192.0.2.11"}
    assert login(client, headers=changed_header).status_code == (200 if trusted else 429)
    monkeypatch.setattr(auth_cli, "get_settings", lambda: settings)
    locked_ip = "192.0.2.10" if trusted else "127.0.0.1"
    monkeypatch.setattr("sys.argv", ["auth_cli", "unlock", "--ip", locked_ip])
    auth_cli.main()
    assert login(client, headers=forwarded).status_code == 200

    for index in range(5):
        caller = client_for(app, socket_ip=f"198.51.100.{index + 1}")
        assert login(caller, password="wrong").status_code == 401
    assert login(client, headers=forwarded).status_code == 429
    monkeypatch.setattr("sys.argv", ["auth_cli", "unlock", "--email", "AMIT@demo.attendflow.test"])
    auth_cli.main()
    assert login(client, headers=forwarded).status_code == 200


ALL = {"worker", "supervisor", "payroll_admin"}
REVIEW = ALL - {"worker"}
ADMIN = {"payroll_admin"}
WORKER = {"worker"}


@pytest.mark.parametrize(
    ("role", "email"),
    [(None, None), ("worker", "amit"), ("supervisor", "ravi"), ("payroll_admin", "priya")],
)
def test_endpoint_family_access_matrix(app, role, email):
    client = client_for(app)
    if email:
        assert login(client, email).status_code == 200
    routes = {
        "/api/health": ALL,
        "/api/auth/me": ALL,
        "/api/exceptions": ADMIN,
        "/api/exceptions/P1-E001-2026-04-14": ADMIN,
        "/api/worker/messages": WORKER,
        "/api/worker/history": WORKER,
        "/api/worker/ask/history": WORKER,
        "/api/admin/worker-questions": ADMIN,
        "/api/briefing": REVIEW,
        "/api/supervisor/queue": REVIEW,
        "/api/supervisor/auto-resolved": REVIEW,
        "/api/admin/metrics/auto-resolve": ADMIN,
        "/api/dashboard": REVIEW,
        "/api/payroll": REVIEW,
        "/api/admin/exceptions": ADMIN,
        "/api/settings": ADMIN,
        "/api/settings/history": ADMIN,
        "/api/activity": REVIEW,
        "/api/activity/summary": REVIEW,
        "/api/autonomy": REVIEW,
        "/api/audit-log": ADMIN,
        "/api/tool-calls": ADMIN,
        "/api/admin/scheduler": ADMIN,
        "/api/admin/demo/clock": ADMIN,
    }
    for path, allowed in routes.items():
        expected = 401 if role is None else 200 if role in allowed else 403
        response = client.get(path, headers={"X-Actor-Id": "E201"})
        assert response.status_code == expected, (path, response.text)
    if role in REVIEW:
        assert client.get("/api/dashboard").json()["scope"] == (
            "all" if role == "payroll_admin" else "team"
        )
    if role != "payroll_admin":
        for path in ("/api/seed", "/api/detection/run", "/api/admin/demo/reset"):
            assert client.post(path, headers={"Origin": ORIGIN}).status_code == (
                401 if role is None else 403
            )


def test_supervisor_cannot_open_another_teams_case(app):
    client = client_for(app)
    path = "/api/supervisor/cases/P1-E001-2026-04-14"
    assert login(client, "ravi").status_code == 200
    assert client.get(path).status_code == 200
    assert login(client, "sunita").status_code == 200
    assert client.get(path, headers={"X-Actor-Id": "E101"}).status_code == 403


def test_qa_history_ignores_header_and_stays_worker_scoped(app):
    settings = replace(app.state.settings, qa_enabled=True)
    app = create_app(settings, engine=app.state.engine)
    first, second = client_for(app), client_for(app)
    assert login(first, "amit").status_code == 200
    assert login(second, "neha").status_code == 200
    question = "Who is my supervisor?"
    asked = first.post(
        "/api/worker/ask",
        headers={"Origin": ORIGIN, "X-Actor-Id": "E004"},
        json={"question": question},
    )
    assert asked.status_code == 200 and asked.json()["llm_calls"] == 0
    assert first.get("/api/worker/ask/history").json()["items"][0]["question"] == question
    assert (
        second.get(
            "/api/worker/ask/history",
            headers={"X-Actor-Id": "E001"},
        ).json()["items"]
        == []
    )


def test_deployed_session_frontend_and_docs(app, tmp_path):
    settings = replace(
        app.state.settings,
        demo_password=token_hex(24),
        deployed=True,
        demo_mode=False,
        demo_reset_enabled=False,
        llm_diagnostics=False,
        device_api_key=None,
        cors_origins=(),
        database_url="postgres://test:fixture-value@db.example/test",
    )
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text('<div id="root"></div>')
    deployed = create_app(settings, engine=app.state.engine, frontend_dir=tmp_path)
    client = client_for(deployed)
    assert client.get("/healthz").status_code == 200
    assert client.get("/login").status_code == 200
    redirect = client.get("/dashboard", follow_redirects=False)
    assert redirect.status_code == 303 and redirect.headers["location"] == "/login"
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert "www-authenticate" not in response.headers
    assert response.json()["error"]["details"] == {"demo_accounts": False}
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_seed_is_repeatable_and_db_enforces_case_insensitive_email(app):
    settings = app.state.settings
    client = client_for(app)
    assert login(client, "priya").status_code == 200
    for _ in range(2):
        assert client.post("/api/seed", headers={"Origin": ORIGIN}).status_code == 200
        assert client.get("/api/auth/me").status_code == 200
    with app.state.session_factory.begin() as session:
        initial = session.get(EmployeeRow, "E001").password_hash
        result = seed_demo_once(
            session, settings.data_dir, extra_week=False, demo_password=PASSWORD
        )
        assert result == {"employees": 13, "credentials_provisioned": 0}
        assert initial == session.get(EmployeeRow, "E001").password_hash
    with pytest.raises(IntegrityError), app.state.session_factory.begin() as session:
        session.get(EmployeeRow, "E002").email = "AMIT@DEMO.ATTENDFLOW.TEST"


def test_set_password_revokes_all_employee_sessions(app, monkeypatch):
    first = client_for(app)
    second = client_for(app)
    for client in (first, second):
        assert login(client, "dev").status_code == 200
    monkeypatch.setattr(auth_cli, "get_settings", lambda: app.state.settings)
    monkeypatch.setattr(auth_cli, "getpass", lambda _: PASSWORD_AFTER_RESET)
    monkeypatch.setattr("sys.argv", ["auth_cli", "set-password", "E007"])
    auth_cli.main()
    for client in (first, second):
        assert client.get("/api/auth/me").status_code == 401
    assert login(first, "dev").status_code == 401
    assert login(first, "dev", PASSWORD_AFTER_RESET).status_code == 200


def test_demo_reset_reprovisions_credentials_and_invalidates_old_sessions(app):
    client = client_for(app)
    assert login(client, "priya").status_code == 200
    reset = client.post("/api/admin/demo/reset", headers={"Origin": ORIGIN})
    assert reset.status_code == 200
    assert reset.json()["seed"]["counts"]["employees"] == 13
    assert client.get("/api/auth/me").status_code == 401
    assert login(client, "priya").status_code == 200
    assert login(client, "dev").status_code == 200
    assert login(client, "neha").status_code == 200
