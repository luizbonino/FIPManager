"""`python -m fipm <cmd>` entry points: import-data, create-admin, serve,
purge-standalone-fips."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta

from fipm.auth import hash_password
from fipm.config import get_settings
from fipm.db import SessionLocal, init_db
from fipm.ids import new_user_id
from fipm.importer import run_import
from fipm.logging_setup import configure_logging
from fipm.models import Fip, User


def _cmd_import_data(args: argparse.Namespace) -> int:
    summary = run_import(force=args.force)
    summary.print_report()
    return 0


def _cmd_create_admin(args: argparse.Namespace) -> int:
    init_db()
    email = args.email.strip().lower()
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).one_or_none()
        settings = get_settings()
        if user is None:
            user = User(
                id=new_user_id(),
                email=email,
                password_hash=hash_password(args.password),
                display_name=args.email,
                role="admin",
                language=settings.default_language,
            )
            db.add(user)
            db.commit()
            print(f"created admin {email}")
        else:
            user.role = "admin"
            db.commit()
            print(f"updated {email} to admin (password unchanged)")
    return 0


def _cmd_purge_standalone_fips(args: argparse.Namespace) -> int:
    """spec 09-standalone-fips.md retention runbook: the privacy notice
    promises deletion 12 months after last edit for a standalone FIP
    (owner_id AND session_id both NULL -- a session FIP stays reachable
    through its session's room/facilitator and is never purged here, same
    distinction as `routers/admin.py`'s `/admin/stats`). No scheduler is
    shipped; an operator runs this monthly.

    Deletes the same way `DELETE /api/fips/{id}` (`routers/fips.py::
    delete_fip`) does -- a plain row delete, no extra FK cleanup: the only
    FK referencing `fips.id` is `Feedback.fip_id`, declared
    `ondelete="SET NULL"` (fipm.models) and enforced by SQLite itself
    (`PRAGMA foreign_keys=ON`, fipm.db), so previously collected feedback
    survives with `fip_id` cleared to NULL, not cascaded away.
    """
    init_db()
    cutoff = datetime.now(UTC) - timedelta(days=args.older_than_days)
    with SessionLocal() as db:
        query = db.query(Fip).filter(
            Fip.owner_id.is_(None),
            Fip.session_id.is_(None),
            Fip.updated_at < cutoff,
        )
        count = query.count()
        if args.dry_run:
            print(
                f"would purge {count} standalone FIP(s) last edited "
                f"before {cutoff.isoformat()} ({args.older_than_days} days)"
            )
        else:
            query.delete(synchronize_session=False)
            db.commit()
            print(
                f"purged {count} standalone FIP(s) last edited "
                f"before {cutoff.isoformat()} ({args.older_than_days} days)"
            )
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("fipm.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def main(argv: list[str] | None = None) -> int:
    # Audit finding 12: every subcommand (not just `serve`, which pulls it
    # in indirectly by importing fipm.main) needs logging configured before
    # it runs anything that logs -- `import-data` and `create-admin` in
    # particular don't otherwise touch fipm.main at all.
    configure_logging()
    parser = argparse.ArgumentParser(prog="python -m fipm")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import-data", help="Load data/ into the DB idempotently")
    import_parser.add_argument(
        "--force", action="store_true", help="Overwrite changed knowledge models"
    )
    import_parser.set_defaults(func=_cmd_import_data)

    admin_parser = subparsers.add_parser("create-admin", help="Create or promote an admin user")
    admin_parser.add_argument("--email", required=True)
    admin_parser.add_argument("--password", required=True)
    admin_parser.set_defaults(func=_cmd_create_admin)

    serve_parser = subparsers.add_parser("serve", help="Run the API with uvicorn")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--reload", action="store_true")
    serve_parser.set_defaults(func=_cmd_serve)

    purge_parser = subparsers.add_parser(
        "purge-standalone-fips",
        help="Delete standalone FIPs (no owner, no session) not edited in --older-than-days",
    )
    purge_parser.add_argument(
        "--older-than-days",
        type=int,
        default=365,
        help="Delete FIPs whose updated_at is older than this many days (default 365)",
    )
    purge_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the count that would be deleted, delete nothing",
    )
    purge_parser.set_defaults(func=_cmd_purge_standalone_fips)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
