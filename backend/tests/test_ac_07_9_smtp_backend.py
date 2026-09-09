"""AC9 (spec 07-mail-and-migration.md §7): `FIPM_MAIL_BACKEND=smtp` with no
`FIPM_SMTP_HOST` refuses to start (`Settings.check_mail_safety`); against a
stub server one `sendmail` call carries the `FIPM_MAIL_FROM` sender, the
recipient and a `text/plain; charset=utf-8` part; an SMTP error is logged,
the response stays 201/202 (mail is best-effort, spec §1)."""

from __future__ import annotations

import pytest

from fipm.config import Settings, get_settings
from fipm.mail import send_mail

PRIVACY_VERSION = "test-v1"


def test_check_mail_safety_rejects_unknown_backend():
    settings = Settings(mail_backend="carrier-pigeon")
    with pytest.raises(RuntimeError, match="FIPM_MAIL_BACKEND"):
        settings.check_mail_safety()


def test_check_mail_safety_rejects_smtp_without_host():
    settings = Settings(mail_backend="smtp", smtp_host=None)
    with pytest.raises(RuntimeError, match="FIPM_SMTP_HOST"):
        settings.check_mail_safety()


def test_check_mail_safety_accepts_console_default():
    Settings().check_mail_safety()  # must not raise


def test_check_mail_safety_accepts_smtp_with_host():
    Settings(mail_backend="smtp", smtp_host="localhost").check_mail_safety()  # must not raise


def test_check_mail_safety_rejects_unknown_smtp_tls():
    """Audit finding 6: `_send_smtp` treats any non-`"ssl"` value as a plain
    (non-TLS) connection, and only calls `starttls()` for the literal value
    `"starttls"` -- so a typo like `"ststarttls"` would silently send mail
    unencrypted instead of failing loudly."""
    settings = Settings(mail_backend="smtp", smtp_host="localhost", smtp_tls="ststarttls")
    with pytest.raises(RuntimeError, match="FIPM_SMTP_TLS"):
        settings.check_mail_safety()


def test_check_mail_safety_accepts_smtp_tls_none():
    Settings(
        mail_backend="smtp", smtp_host="localhost", smtp_tls="none"
    ).check_mail_safety()  # must not raise


class _StubSMTP:
    """Records the `send_message` call instead of opening a socket -- stands
    in for `smtplib.SMTP` (used as a context manager, same interface)."""

    instances: list[_StubSMTP] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.sent: list = []
        self.started_tls = False
        self.login_args: tuple | None = None
        _StubSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, msg):
        self.sent.append(msg)


def test_smtp_backend_sends_one_message_with_from_to_and_text_part(monkeypatch):
    monkeypatch.setenv("FIPM_MAIL_BACKEND", "smtp")
    monkeypatch.setenv("FIPM_SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("FIPM_MAIL_FROM", "FIP Manager <no-reply@example.org>")
    get_settings.cache_clear()
    _StubSMTP.instances.clear()
    monkeypatch.setattr("fipm.mail.smtplib.SMTP", _StubSMTP)
    try:
        send_mail("someone@example.org", "Test subject", "Test body")
    finally:
        monkeypatch.delenv("FIPM_MAIL_BACKEND", raising=False)
        monkeypatch.delenv("FIPM_SMTP_HOST", raising=False)
        monkeypatch.delenv("FIPM_MAIL_FROM", raising=False)
        get_settings.cache_clear()

    assert len(_StubSMTP.instances) == 1
    stub = _StubSMTP.instances[0]
    assert len(stub.sent) == 1
    msg = stub.sent[0]
    assert msg["From"] == "FIP Manager <no-reply@example.org>"
    assert msg["To"] == "someone@example.org"
    text_part = msg.get_body(preferencelist=("plain",))
    assert text_part is not None
    assert text_part.get_content_type() == "text/plain"
    assert text_part.get_content_charset() == "utf-8"


def test_smtp_error_is_logged_and_registration_still_201(client, caplog, monkeypatch):
    """An SMTP failure during the register-triggered verify-email send must
    never turn the 201 into a 500 (spec §1's best-effort mail rule)."""
    caplog.set_level("ERROR", logger="fipm.mail")
    monkeypatch.setenv("FIPM_MAIL_BACKEND", "smtp")
    monkeypatch.setenv("FIPM_SMTP_HOST", "smtp.example.org")
    get_settings.cache_clear()

    def _boom(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr("fipm.mail.smtplib.SMTP", _boom)
    try:
        r = client.post(
            "/api/auth/register",
            json={
                "email": "ac07-smtp-error@example.com",
                "password": "correcthorsebattery",
                "displayName": "S",
                "privacyAcceptedVersion": PRIVACY_VERSION,
            },
        )
        assert r.status_code == 201, r.text
    finally:
        monkeypatch.delenv("FIPM_MAIL_BACKEND", raising=False)
        monkeypatch.delenv("FIPM_SMTP_HOST", raising=False)
        get_settings.cache_clear()

    error_records = [
        rec
        for rec in caplog.records
        if rec.name == "fipm.mail" and rec.levelname in ("ERROR", "CRITICAL")
    ]
    assert error_records, "expected the swallowed SMTP failure to be logged"
