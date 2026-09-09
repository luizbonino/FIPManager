"""Mail backend and templating (spec 07-mail-and-migration.md §1).

`send_mail` builds an `EmailMessage` and dispatches it via the configured
backend (`console`, the default, logs one INFO record on `fipm.mail`; `smtp`
uses `smtplib`). `render_mail` reads `data/i18n/mail/{lang}/{template}.txt`
(first line `Subject: ...`, blank line, body; `str.format(**ctx)`
placeholders) with the same pt-PT<->pt-BR / es->en language fallback chain
`fipm.privacy` uses for the privacy notice.

`queue_mail` is the call-site helper: every send happens inside a FastAPI
`BackgroundTasks` callback wrapped in try/except, so a mail failure never
turns a 201/202 response into a 500 and the caller learns nothing about
whether the address exists from response timing (spec §1 last paragraph).
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from functools import lru_cache
from pathlib import Path

from fastapi import BackgroundTasks

from fipm.config import Settings, get_settings

logger = logging.getLogger("fipm.mail")

# pt-PT <-> pt-BR, es -> en, and anything else (including "en" itself and an
# unknown lang) -> en only. Mirrors fipm.privacy._LANG_FALLBACK_CHAIN /
# exporters.resolve_lang's fallback chain (spec 02 §5.5).
_LANG_FALLBACK_CHAIN: dict[str, tuple[str, ...]] = {
    "pt-PT": ("pt-PT", "pt-BR", "en"),
    "pt-BR": ("pt-BR", "pt-PT", "en"),
    "es": ("es", "en"),
    "en": ("en",),
}


class MailTemplateMissing(RuntimeError):
    """Raised when neither the requested language nor `en` has the template
    on disk -- spec §1: "absence is a test failure, not a runtime surprise"."""


@lru_cache
def _load_template(data_dir: str, lang: str, template: str) -> tuple[str, str] | None:
    """(subject, body) for `<data_dir>/i18n/mail/<lang>/<template>.txt`, or
    None if the file is missing. Cached per (data_dir, lang, template): mail
    templates are static between deploys, like fipm.privacy._load."""
    path = Path(data_dir) / "i18n" / "mail" / lang / f"{template}.txt"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    first_line, _, rest = text.partition("\n")
    if not first_line.startswith("Subject:"):
        raise MailTemplateMissing(f"{path} does not start with 'Subject: '")
    subject = first_line[len("Subject:") :].strip()
    body = rest.lstrip("\n")
    return subject, body


def render_mail(template: str, lang: str, ctx: dict[str, str]) -> tuple[str, str]:
    """(subject, text) for `template` in `lang` (falling back through the
    pt-PT/pt-BR/es/en chain), with `ctx`'s keys (`displayName`, `link`,
    `appName`, `baseUrl`, `expiresHours`, ...) filled in via `str.format`.
    An optional sibling `{template}.html` is not loaded here -- callers that
    want it read `_load_template`'s html variant directly (v2 ships text
    only; no template currently has an .html sibling)."""
    settings = get_settings()
    chain = _LANG_FALLBACK_CHAIN.get(lang, _LANG_FALLBACK_CHAIN["en"])
    for candidate in chain:
        loaded = _load_template(settings.data_dir, candidate, template)
        if loaded is not None:
            subject, body = loaded
            return subject.format(**ctx), body.format(**ctx)
    raise MailTemplateMissing(
        f"no mail template {template!r} found for lang {lang!r} or its fallback chain "
        f"(data_dir={settings.data_dir!r})"
    )


def _build_message(
    settings: Settings, to: str, subject: str, text: str, html: str | None
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if html is not None:
        msg.add_alternative(html, subtype="html")
    return msg


def _send_console(settings: Settings, to: str, subject: str, text: str) -> None:
    indented = "\n".join(f"    {line}" for line in text.splitlines())
    logger.info("MAIL to=%s subject=%s\n%s", to, subject, indented)


def _send_smtp(settings: Settings, msg: EmailMessage) -> None:
    if not settings.smtp_host:
        raise RuntimeError("FIPM_SMTP_HOST is required when FIPM_MAIL_BACKEND=smtp")
    if settings.smtp_tls == "ssl":
        client_cls = smtplib.SMTP_SSL
    else:
        client_cls = smtplib.SMTP
    with client_cls(
        settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout
    ) as client:
        if settings.smtp_tls == "starttls":
            client.starttls()
        if settings.smtp_user:
            client.login(settings.smtp_user, settings.smtp_password or "")
        client.send_message(msg)


def send_mail(to: str, subject: str, text: str, html: str | None = None) -> None:
    """Dispatch one mail per `settings.mail_backend`. Callers that must not
    let a failure affect the HTTP response should go through `queue_mail`
    instead, which runs this inside a background task's try/except."""
    settings = get_settings()
    if settings.mail_backend == "console":
        _send_console(settings, to, subject, text)
        return
    if settings.mail_backend == "smtp":
        msg = _build_message(settings, to, subject, text, html)
        _send_smtp(settings, msg)
        return
    raise RuntimeError(f"unknown FIPM_MAIL_BACKEND {settings.mail_backend!r}")


def _send_mail_swallowing_errors(to: str, subject: str, text: str, html: str | None) -> None:
    try:
        send_mail(to, subject, text, html)
    except Exception:
        # spec §1: mail must never turn a 201/202 into a 500; the caller
        # must not learn from timing whether a mailbox exists.
        logger.exception("failed to send mail to=%s subject=%s", to, subject)


def queue_mail(
    background_tasks: BackgroundTasks, to: str, subject: str, text: str, html: str | None = None
) -> None:
    """Queue `send_mail` as a FastAPI background task, wrapped in
    try/except (spec §1's "every send runs in a BackgroundTasks callback
    wrapped in try/except Exception that logs and swallows")."""
    background_tasks.add_task(_send_mail_swallowing_errors, to, subject, text, html)


def warn_if_console_in_production(settings: Settings) -> None:
    """Called once at startup (spec §1): one WARNING when FIPM_ENV=production
    and the backend is still `console`."""
    if settings.env == "production" and settings.mail_backend == "console":
        logger.warning(
            "account mail only reaches the log; anyone with log access can read the links"
        )
