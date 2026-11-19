import shutil
from pathlib import Path

import pytest

from attendflow.config import REPO_ROOT
from attendflow.data import Dataset, load_dataset

DATA_DIR = REPO_ROOT / "data"


@pytest.fixture(scope="session")
def dataset() -> Dataset:
    return load_dataset(DATA_DIR)


@pytest.fixture
def data_copy(tmp_path: Path) -> Path:
    """A throwaway copy of data/ that a test can break on purpose."""
    dst = tmp_path / "data"
    shutil.copytree(DATA_DIR, dst)
    return dst


def replace_in_file(path: Path, old: str, new: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path.name}"
    path.write_text(text.replace(old, new, count), encoding="utf-8")


# ---------------------------------------------------------------- database (API tests)
# API tests run on a real PostgreSQL test database (TEST_DATABASE_URL). If it cannot be
# reached they are skipped with a message, unless REQUIRE_DB=1 (CI), where that fails.

DEFAULT_TEST_DB = "postgresql+psycopg://attendflow:attendflow@localhost:5433/attendflow_test"


class UnsafeTestDatabaseError(Exception):
    pass


def check_test_database_name(name: str | None) -> None:
    """Tests wipe their database, so they only run on one whose name ends in '_test'.
    This stops a mistyped TEST_DATABASE_URL from erasing the dev (or any real) database."""
    if not name or not name.endswith("_test"):
        raise UnsafeTestDatabaseError(
            f"refusing to run tests on database {name!r}: the tests wipe it, so its name "
            "must end in '_test' (check TEST_DATABASE_URL)"
        )


@pytest.fixture(scope="session")
def db_engine():
    import os

    from alembic import command
    from alembic.config import Config
    from dotenv import load_dotenv
    from sqlalchemy import text

    from attendflow.db.session import make_engine

    load_dotenv(REPO_ROOT / ".env", override=False)
    url = os.getenv("TEST_DATABASE_URL") or DEFAULT_TEST_DB
    engine = make_engine(url)
    shown = engine.url.render_as_string(hide_password=True)
    try:
        # Checked before connecting (the URL), and never skipped: a wrong URL must fail loudly.
        check_test_database_name(engine.url.database)
    except UnsafeTestDatabaseError as exc:
        engine.dispose()
        pytest.fail(f"{exc} [{shown}]")
    try:
        with engine.connect() as conn:
            server_db = conn.execute(text("SELECT current_database()")).scalar_one()
    except Exception as exc:  # noqa: BLE001
        engine.dispose()
        msg = f"test database unreachable ({shown}): start it with `docker compose up -d db`"
        if os.getenv("REQUIRE_DB") == "1":
            pytest.fail(f"{msg}\n{exc}")
        pytest.skip(msg)
    try:
        # Checked again on the server, in case the URL's name is not the one actually used.
        check_test_database_name(server_db)
    except UnsafeTestDatabaseError as exc:
        engine.dispose()
        pytest.fail(f"{exc} [{shown}]")

    # Fresh schema from the real migrations, so the migrations are tested too.
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def api_settings(db_engine):
    from dataclasses import replace

    from attendflow.config import get_settings

    return replace(
        get_settings(env_file=None),
        data_dir=DATA_DIR,
        database_url=db_engine.url.render_as_string(hide_password=False),
        enable_seed=True,
        log_format="text",
        log_level="WARNING",
    )


@pytest.fixture
def client(db_engine, api_settings):
    """An API client on an empty test database."""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from attendflow.api.app import create_app
    from attendflow.db.seed import truncate_all

    with Session(db_engine) as s, s.begin():
        truncate_all(s)
    app = create_app(api_settings, engine=db_engine)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def demo(client):
    """An API client with the demo data seeded and detection run once."""
    assert client.post("/api/seed").status_code == 200
    assert client.post("/api/detection/run").status_code == 200
    return client
