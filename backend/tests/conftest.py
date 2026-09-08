"""Shared pytest fixtures.

A single temp-file SQLite DB is used for the whole test session (per the
task brief). All FIPM_ env vars are set in pytest_configure, before any
`fipm.*` module is imported, since fipm.config.get_settings() is cached.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_BASE_URL = "http://testserver"


def pytest_configure(config: pytest.Config) -> None:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # let SQLite create the file fresh on first connect

    os.environ["FIPM_DB_PATH"] = path
    os.environ["FIPM_DATA_DIR"] = str(FIXTURES_DIR)
    os.environ["FIPM_STATIC_DIR"] = str(FIXTURES_DIR / "no-such-static-dir")
    os.environ["FIPM_BASE_URL"] = TEST_BASE_URL
    os.environ["FIPM_SECRET_KEY"] = "test-secret-key-not-for-prod"
    os.environ["FIPM_COOKIE_SECURE"] = "false"
    os.environ["FIPM_ENV"] = "development"
    os.environ["FIPM_REGISTRATION_OPEN"] = "true"
    os.environ["FIPM_ID_PREFIX"] = ""
    os.environ.pop("FIPM_ADMIN_EMAIL", None)
    os.environ.pop("FIPM_ADMIN_PASSWORD", None)


@pytest.fixture(scope="session")
def settings():
    from fipm.config import get_settings

    return get_settings()


@pytest.fixture(scope="session")
def app(settings):
    from fipm.importer import run_import

    run_import()
    from fipm.main import app as fastapi_app

    return fastapi_app


@pytest.fixture()
def client_factory(app, settings):
    from starlette.testclient import TestClient

    clients: list[TestClient] = []

    def _make() -> TestClient:
        c = TestClient(app, headers={"origin": settings.base_url})
        c.__enter__()
        clients.append(c)
        return c

    yield _make

    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture()
def client(client_factory):
    """A TestClient that always sends a same-origin Origin header (CSRF-safe)."""
    return client_factory()


@pytest.fixture()
def raw_client(app):
    """A TestClient with no default headers, for CSRF-specific tests."""
    from starlette.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Each test starts with a clean in-process rate limiter (see fipm.auth);
    otherwise the 5/hour register and 10/15min login limits bleed across the
    many tests that share this process/IP."""
    from fipm.auth import reset_rate_limits

    reset_rate_limits()
    yield


@pytest.fixture()
def db_session():
    from fipm.db import SessionLocal

    with SessionLocal() as db:
        yield db
