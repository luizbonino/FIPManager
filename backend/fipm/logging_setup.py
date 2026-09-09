"""Process-wide logging configuration (audit finding 12).

Nothing in this app ever called `logging.basicConfig` or attached a
handler, so every `logger.info` call anywhere in the codebase -- including
`fipm.mail`'s console backend, whose "MAIL to=..." record is the *only*
place a self-hosted, `FIPM_MAIL_BACKEND=console` deployment (the default)
sees a verify-email/password-reset link -- was silently dropped by the
root logger's default WARNING level and lack of a handler. `docker logs`
showed nothing.

`configure_logging()` is called once, as early as possible, from both
`fipm.main` (the ASGI app) and `fipm.cli` (the `python -m fipm ...` entry
point), so stdout always carries at least INFO-level records.
"""

from __future__ import annotations

import logging
import sys

from fipm.config import get_settings

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging() -> None:
    """`logging.basicConfig` is itself idempotent (a no-op once the root
    logger already has a handler), so calling this from both entry points
    is safe -- whichever runs first wins."""
    settings = get_settings()
    level = getattr(logging, (settings.log_level or "INFO").upper(), logging.INFO)
    logging.basicConfig(level=level, format=_LOG_FORMAT, stream=sys.stdout)
