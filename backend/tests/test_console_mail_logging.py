"""Audit finding 12: nothing in this app ever called
`logging.basicConfig`/attached a handler, so every `logger.info` call --
including the console mail backend's only record of a verify-email/
password-reset link -- was silently dropped by the root logger's default
WARNING level and lack of a handler; a self-hosted `FIPM_MAIL_BACKEND=
console` deployment (the default) would see nothing at all in `docker
logs`. Two independent fixes: `fipm.logging_setup.configure_logging`
(called from both `fipm.main` and `fipm.cli`, so every entry point gets a
handler) actually wires logging up, and `fipm.mail._send_console` also now
prints the message straight to stdout -- a second, logging-config-
independent path to the same output, so the link survives even in an
environment where something else resets logging config after import."""

from __future__ import annotations

import logging
import sys

from fipm.config import get_settings
from fipm.logging_setup import configure_logging
from fipm.mail import send_mail


def test_console_backend_prints_the_message_to_stdout(monkeypatch, capsys):
    monkeypatch.setenv("FIPM_MAIL_BACKEND", "console")
    get_settings.cache_clear()
    try:
        send_mail("someone@example.org", "A test subject", "Body with /verify?token=abc123")
    finally:
        monkeypatch.delenv("FIPM_MAIL_BACKEND", raising=False)
        get_settings.cache_clear()

    captured = capsys.readouterr()
    assert "[MAIL] to=someone@example.org" in captured.out
    assert "/verify?token=abc123" in captured.out


def test_console_backend_also_logs_at_info_with_mail_prefix(caplog):
    caplog.set_level("INFO", logger="fipm.mail")
    send_mail("someone-else@example.org", "Another subject", "Body with /reset-password?token=xyz")

    mail_records = [r for r in caplog.records if r.name == "fipm.mail"]
    assert len(mail_records) == 1
    message = mail_records[0].getMessage()
    assert "[MAIL] to=someone-else@example.org" in message
    assert "/reset-password?token=xyz" in message


def test_configure_logging_calls_basic_config_with_info_level_and_stdout(monkeypatch):
    """Asserted against a mocked `logging.basicConfig` rather than the real
    root logger's live state: pytest's own log-capturing plugin resets the
    root logger's level around every test independently of anything the
    application does, which would make an assertion against the real
    global state pass or fail depending on unrelated test order rather
    than on what `configure_logging` actually did."""
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: calls.append(kwargs))

    configure_logging()

    assert len(calls) == 1
    assert calls[0]["level"] == logging.INFO
    assert calls[0]["stream"] is sys.stdout
    assert "%(message)s" in calls[0]["format"]


def test_register_endpoint_prints_verify_link_to_stdout(client, capsys):
    """End-to-end: the actual `docker logs`-visible symptom -- registering
    with the default console backend must leave the verify link somewhere
    in stdout, not only in an in-process log record a test's `caplog` can
    see but an operator's terminal cannot."""
    capsys.readouterr()  # drain anything buffered before this test
    r = client.post(
        "/api/auth/register",
        json={
            "email": "ac-finding12-stdout@example.com",
            "password": "correcthorsebattery",
            "displayName": "Stdout",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert r.status_code == 201, r.text

    captured = capsys.readouterr()
    assert "/verify?token=" in captured.out
