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


@pytest.fixture(autouse=True)
def _reset_network_cache():
    """Each test starts with a clean fipm.network cache (spec
    11-nanopub-network.md §3.4) -- otherwise a cache entry recorded by one
    test's fixture would be served to a later test that never called
    _post_sparql/_get_grlc at all."""
    from fipm.network import reset_network_cache

    reset_network_cache()
    yield


@pytest.fixture(autouse=True)
def _guard_network_calls(monkeypatch):
    """spec 11-nanopub-network.md §6: "no test performs a live network
    request" -- fipm.network._post_sparql/_get_grlc default to raising a
    clear error unless a test explicitly monkeypatches them with a
    fixture-serving replacement, so a test that forgets to patch one fails
    loudly with this message rather than attempting (and, on a machine with
    no network, hanging on) a real HTTP request."""

    def _unpatched(*args, **kwargs):
        raise AssertionError(
            "no fixture registered for this fipm.network call -- monkeypatch "
            "fipm.network._post_sparql / _get_grlc before making this request"
        )

    monkeypatch.setattr("fipm.network._post_sparql", _unpatched)
    monkeypatch.setattr("fipm.network._get_grlc", _unpatched)
    yield


@pytest.fixture()
def db_session():
    from fipm.db import SessionLocal

    with SessionLocal() as db:
        yield db
