"""`python -m fipm <cmd>` entry points: import-data, create-admin, serve."""

from __future__ import annotations

import argparse
import sys

from fipm.auth import hash_password
from fipm.config import get_settings
from fipm.db import SessionLocal, init_db
from fipm.ids import new_user_id
from fipm.importer import run_import
from fipm.logging_setup import configure_logging
from fipm.models import User


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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
