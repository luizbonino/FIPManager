"""`python -m fipm <cmd>` entry points: import-data, create-admin, serve,
purge-standalone-fips, backfill-declarations, check-declarations."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime, timedelta

from fipm.auth import hash_password
from fipm.config import get_settings
from fipm.db import SessionLocal, init_db
from fipm.ids import new_user_id
from fipm.importer import run_import
from fipm.logging_setup import configure_logging
from fipm.models import (
    DashboardMeta,
    Fip,
    FipCell,
    FipDeclaration,
    FipFacets,
    FipSignature,
    FipSignatureBand,
    KnowledgeModel,
    NetworkFip,
    User,
)


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

    spec 13-fip-dashboard.md §1.6: `Query.delete(synchronize_session=False)`
    bypasses ORM events entirely (no `Fip` instances are ever loaded, so
    `after_flush`/`before_commit` see nothing to reproject), so this is one
    of the two bulk paths the write hook cannot cover -- `unproject_fip`
    each id explicitly, *before* the bulk delete, in the same transaction.
    """
    init_db()
    from fipm.projection import projection_suspended, unproject_fip

    cutoff = datetime.now(UTC) - timedelta(days=args.older_than_days)
    with SessionLocal() as db:
        query = db.query(Fip).filter(
            Fip.owner_id.is_(None),
            Fip.session_id.is_(None),
            Fip.updated_at < cutoff,
        )
        ids = [row.id for row in query.with_entities(Fip.id).all()]
        count = len(ids)
        if args.dry_run:
            print(
                f"would purge {count} standalone FIP(s) last edited "
                f"before {cutoff.isoformat()} ({args.older_than_days} days)"
            )
        else:
            with projection_suspended():
                for fip_id in ids:
                    unproject_fip(db, fip_id)
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


# ---------------------------------------------------------------------------
# spec 13-fip-dashboard.md §1.7: backfill-declarations, check-declarations.
# ---------------------------------------------------------------------------


def _backfill_candidate_ids(
    db,  # noqa: ANN001
    *,
    only_stale: bool,
    questionnaire: str | None,
    since: str | None,
    fips_from: str | None,
) -> list[str]:
    from fipm.projection import stale_fip_ids

    if fips_from:
        with open(fips_from, encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

    if only_stale:
        return stale_fip_ids(db)

    query = db.query(Fip.id)
    if questionnaire:
        km_id, _, km_version = questionnaire.partition("@")
        query = query.filter(Fip.questionnaire_id == km_id, Fip.questionnaire_version == km_version)
    if since:
        query = query.filter(Fip.updated_at >= since)
    return [row.id for row in query.all()]


def _run_backfill(
    *,
    only_stale: bool = False,
    batch: int = 500,
    progress: bool = False,
    questionnaire: str | None = None,
    since: str | None = None,
    fips_from: str | None = None,
    dry_run: bool = False,
) -> tuple[int, float]:
    """spec §1.7: idempotent (delete-then-insert per FIP), inside
    `projection_suspended()`, committing every `batch` FIPs so a large run
    can be interrupted and resumed. Returns `(count, duration_seconds)`.
    Shared by the CLI command and the §7.2 startup backfill."""
    from fipm.projection import projection_suspended, reproject_fip

    init_db()
    start = time.monotonic()
    with SessionLocal() as db:
        ids = _backfill_candidate_ids(
            db, only_stale=only_stale, questionnaire=questionnaire, since=since, fips_from=fips_from
        )
        if dry_run:
            return len(ids), time.monotonic() - start

        drained_refs: set[str] = set()
        with projection_suspended():
            for i, fip_id in enumerate(ids, start=1):
                fip = db.get(Fip, fip_id)
                if fip is not None:
                    drained_refs.add(f"{fip.questionnaire_id}@{fip.questionnaire_version}")
                reproject_fip(db, fip_id)
                if i % batch == 0:
                    db.commit()
                    if progress:
                        print(f"backfilled {i}/{len(ids)}")
            db.commit()

        if only_stale and drained_refs:
            backlog_row = db.get(DashboardMeta, "reprojection_backlog")
            if backlog_row is not None:
                backlog_row.value = [r for r in backlog_row.value if r not in drained_refs]
                db.commit()

    return len(ids), time.monotonic() - start


def _cmd_backfill_declarations(args: argparse.Namespace) -> int:
    count, duration = _run_backfill(
        only_stale=args.only_stale,
        batch=args.batch,
        progress=args.progress,
        questionnaire=args.questionnaire,
        since=args.since,
        fips_from=args.fips_from,
        dry_run=args.dry_run,
    )
    verb = "would backfill" if args.dry_run else "backfilled"
    rate = count / duration if duration > 0 else float("inf")
    print(f"{verb} {count} FIP(s) in {duration:.2f}s ({rate:.0f} FIPs/s)")
    return 0


def _check_one_fip(db, fip_id: str) -> list[str]:  # noqa: ANN001
    """Recomputes `fip_cells`/`fip_declarations`/`fip_facets` for one FIP via
    `project_answers` (the same function the write hook and the §1.8
    fallback use) and diffs the counts against the stored rows. Returns a
    list of human-readable mismatch descriptions (empty = clean)."""
    from fipm.projection import project_answers

    fip = db.get(Fip, fip_id)
    if fip is None:
        # A legitimately deleted FIP has no fips row *and* no projection
        # rows -- that is the correct, clean state (invariant 2 catches an
        # orphan whose projection rows outlived the fips row, separately).
        # Exempt exactly `source='network'` (spec §1.7 invariant 2, §5.4):
        # a network shadow row never has a `fips` row by design, so an
        # explicit `only_ids=[<network fip_id>]` check (only_ids is the
        # only way a network id ever reaches this per-FIP path -- the
        # normal sampling loop iterates `fips.id` only) must not flag it.
        facets = db.query(FipFacets).filter(FipFacets.fip_id == fip_id).one_or_none()
        if facets is not None and facets.source == "network":
            return []
        orphan_count = (
            (1 if facets is not None else 0)
            + db.query(FipCell).filter(FipCell.fip_id == fip_id).count()
            + db.query(FipDeclaration).filter(FipDeclaration.fip_id == fip_id).count()
        )
        if orphan_count:
            return [f"{fip_id}: projection rows exist for a nonexistent fips.id"]
        return []

    facets = db.get(FipFacets, fip_id)
    if facets is None:
        return [f"{fip_id}: missing fip_facets row"]

    km = db.get(KnowledgeModel, (fip.questionnaire_id, fip.questionnaire_version))
    projected = project_answers(km.content if km else None, fip.answers)

    problems: list[str] = []
    stored_cells = db.query(FipCell).filter(FipCell.fip_id == fip_id).all()
    stored_decls = db.query(FipDeclaration).filter(FipDeclaration.fip_id == fip_id).all()

    if len(stored_cells) != projected.question_count:
        problems.append(
            f"{fip_id}: fip_cells count {len(stored_cells)} != expected {projected.question_count}"
        )
    if len(stored_decls) != projected.declaration_count:
        problems.append(
            f"{fip_id}: fip_declarations count {len(stored_decls)} != "
            f"expected {projected.declaration_count}"
        )

    # Per-row diff -- not just counts: a row that exists but carries a wrong
    # `cell_state` (or a declaration with a wrong `fer_key`/`status`) has
    # the *same* count as the correct projection, so counts alone would
    # miss it (spec §8.1 test 7's "a wrong cell_state" case).
    expected_cells = {c.question_id: c.cell_state for c in projected.cells}
    stored_cell_states = {c.question_id: c.cell_state for c in stored_cells}
    if stored_cell_states != expected_cells:
        problems.append(f"{fip_id}: fip_cells.cell_state mismatch")

    expected_decls = {(d.question_id, d.decl_index): d.fer_key for d in projected.declarations}
    stored_decl_keys = {(d.question_id, d.decl_index): d.fer_key for d in stored_decls}
    if stored_decl_keys != expected_decls:
        problems.append(f"{fip_id}: fip_declarations content mismatch")

    if facets.question_count != projected.question_count:
        problems.append(f"{fip_id}: fip_facets.question_count stale")
    if facets.declaration_count != projected.declaration_count:
        problems.append(f"{fip_id}: fip_facets.declaration_count stale")
    if fip.updated_at != facets.fip_updated_at:
        problems.append(f"{fip_id}: fip_facets.fip_updated_at stale")

    current_epoch_row = db.get(DashboardMeta, "projection_epoch")
    current_epoch = int(current_epoch_row.value) if current_epoch_row is not None else 0
    if facets.projection_epoch != current_epoch:
        problems.append(f"{fip_id}: fip_facets.projection_epoch stale")

    # spec §1.7 invariant 4 + the signature-parameter check (brief B,
    # §4.2): band-row count must equal FIPM_DASHBOARD_LSH_BANDS, and a
    # signature computed under different k/bands/rows_per_band (a settings
    # change since the last reproject) or whose bytes no longer match a
    # fresh recompute is stale, exactly like a stale `cell_state` above.
    from fipm import similarity

    settings = get_settings()
    signature = db.get(FipSignature, fip_id)
    if signature is None:
        problems.append(f"{fip_id}: missing fip_signatures row")
    else:
        if (
            signature.k != settings.dashboard_lsh_k
            or signature.bands != settings.dashboard_lsh_bands
            or signature.rows_per_band != settings.dashboard_lsh_rows
        ):
            problems.append(
                f"{fip_id}: fip_signatures parameter mismatch (stale k/bands/rows_per_band)"
            )
        band_count = db.query(FipSignatureBand).filter(FipSignatureBand.fip_id == fip_id).count()
        if band_count != settings.dashboard_lsh_bands:
            problems.append(
                f"{fip_id}: fip_signature_bands count {band_count} != "
                f"FIPM_DASHBOARD_LSH_BANDS {settings.dashboard_lsh_bands} (invariant 4)"
            )
        expected_signature = similarity.minhash(
            similarity.tokens(projected.cells, projected.declarations),
            k=settings.dashboard_lsh_k,
            seed=settings.dashboard_lsh_seed,
        )
        if signature.signature != expected_signature:
            problems.append(f"{fip_id}: fip_signatures.signature mismatch")
    return problems


def run_check_declarations(
    *,
    sample: int = 1000,
    all_fips: bool = False,
    fix: bool = False,
    only_ids: list[str] | None = None,
) -> list[str]:
    """The testable core of `check-declarations` -- returns the list of
    mismatch descriptions (empty = clean), optionally repairing them first.
    Shared by the CLI command and `test_ac_13_01_projection.py`. `only_ids`,
    test-only, scopes both the per-FIP diff and the invariant scans to a
    specific id set -- the shared test-session database accumulates FIPs
    and epoch bumps from every other test module, so an unscoped `all_fips`
    check run from an individual test would also report *other* tests'
    (correctly) unreprojected FIPs as stale."""
    import random

    from fipm.projection import reproject_fip

    init_db()
    problems: list[str] = []
    with SessionLocal() as db:
        all_ids = only_ids if only_ids is not None else [row.id for row in db.query(Fip.id).all()]
        if only_ids is not None or all_fips or sample >= len(all_ids):
            sample_ids = all_ids
        else:
            sample_ids = random.sample(all_ids, sample)

        for fip_id in sample_ids:
            problems.extend(_check_one_fip(db, fip_id))

        # Whole-table invariant 1: every *existing* FIP has a local facets
        # row -- scoped to `all_ids`'s still-existing subset, since
        # `only_ids` (test-only) may legitimately name an id that was since
        # deleted (deleted-with-no-orphan is the correct, clean state,
        # handled by `_check_one_fip` above, not this invariant).
        existing_ids = (
            {row.id for row in db.query(Fip.id).filter(Fip.id.in_(all_ids)).all()}
            if only_ids is not None
            else set(all_ids)
        )
        facets_rows = db.query(FipFacets.fip_id).filter(FipFacets.source == "local")
        facets_ids = {row.fip_id for row in facets_rows}
        if only_ids is not None:
            facets_ids &= set(only_ids)
        missing_facets = existing_ids - facets_ids
        for fip_id in sorted(missing_facets)[: max(0, 20 - len(problems))]:
            problems.append(f"{fip_id}: missing fip_facets row (invariant 1)")

        # Whole-table invariant 2: no orphaned local fact-table rows.
        orphan_facets = facets_ids - existing_ids
        for fip_id in sorted(orphan_facets)[: max(0, 20 - len(problems))]:
            problems.append(f"{fip_id}: fip_facets row for a nonexistent fips.id (invariant 2)")

        # invariant 2, extended to fip_signatures (brief B, §1.7): a
        # signature row is legitimate for a network shadow id (no `fips`
        # row by design, exempted exactly like `fip_facets.source
        # ='network'` above) or for an id in `existing_ids` -- anything
        # else is an orphan.
        network_ids = {row.fip_id for row in db.query(NetworkFip.fip_id).all()}
        sig_ids = {row.fip_id for row in db.query(FipSignature.fip_id).all()}
        if only_ids is not None:
            sig_ids &= set(only_ids)
        orphan_sigs = sig_ids - existing_ids - network_ids
        for fip_id in sorted(orphan_sigs)[: max(0, 20 - len(problems))]:
            problems.append(f"{fip_id}: fip_signatures row for a nonexistent fips.id (invariant 2)")

        if fix and problems:
            fix_ids = {p.split(":")[0] for p in problems} & existing_ids
            for fip_id in fix_ids:
                reproject_fip(db, fip_id)
            db.commit()

    return problems


def _cmd_check_declarations(args: argparse.Namespace) -> int:
    problems = run_check_declarations(sample=args.sample, all_fips=args.all, fix=args.fix)
    if args.json:
        payload = {"clean": not problems, "problems": problems[:20], "count": len(problems)}
        print(json.dumps(payload))
    else:
        if problems:
            print(f"{len(problems)} problem(s) found (showing up to 20):")
            for p in problems[:20]:
                print(f"  {p}")
        else:
            print("check-declarations: clean")
    return 0 if not problems else 1


# ---------------------------------------------------------------------------
# spec 13-fip-dashboard.md §5.3/§5.4: refresh-dashboard, ingest-network-fips.
# ---------------------------------------------------------------------------


def _cmd_refresh_dashboard(args: argparse.Namespace) -> int:
    """spec §5.3's cron entry point: recomputes and stores the named (or
    every saved `auth_scope='pub'`) population's snapshots, drains expired
    rows, and refreshes `lsh_hot_buckets` (spec §4.4's "maintained by the
    refresh job"). `--json` for cron."""
    from fipm.dashboard import snapshots as snapshots_module
    from fipm.dashboard.similarity_views import (
        clusters_view,
        map_view,
        refresh_hot_buckets,
    )
    from fipm.dashboard.views import adoption_view, coverage_view, evolution_view, gaps_view
    from fipm.models import DashboardPopulation

    init_db()
    views_by_name = {
        "coverage": lambda db, spec, viewer, pop: coverage_view(db, spec, viewer, pop=pop),
        "adoption": lambda db, spec, viewer, pop: adoption_view(db, spec, viewer, pop=pop),
        "gaps": lambda db, spec, viewer, pop: gaps_view(db, spec, viewer, pop=pop),
        "evolution": lambda db, spec, viewer, pop: evolution_view(db, spec, viewer, pop=pop),
        "clusters": lambda db, spec, viewer, pop: clusters_view(db, spec, viewer, pop=pop),
        "map": lambda db, spec, viewer, pop: map_view(db, spec, viewer, pop=pop),
    }
    requested_views = args.views.split(",") if args.views else list(views_by_name)

    results: list[dict[str, object]] = []
    with SessionLocal() as db:
        hot_buckets = refresh_hot_buckets(db)

        if args.all_saved:
            populations = (
                db.query(DashboardPopulation).filter(DashboardPopulation.auth_scope == "pub").all()
            )
            targets = [(row.hash, row.spec) for row in populations]
        elif args.population:
            row = db.get(DashboardPopulation, args.population)
            if row is None:
                print(f"no saved population {args.population!r}")
                return 1
            targets = [(row.hash, row.spec)]
        else:
            print("one of --population or --all-saved is required")
            return 1

        for phash, spec in targets:
            for view in requested_views:
                if view not in views_by_name:
                    results.append({"population": phash, "view": view, "error": "unknown_view"})
                    continue
                try:
                    envelope = snapshots_module.refresh_now(
                        db,
                        view,
                        spec,
                        None,
                        compute=lambda pop, v=view, sp=spec: views_by_name[v](db, sp, None, pop),
                        params={},
                    )
                    results.append(
                        {
                            "population": phash,
                            "view": view,
                            "fipCount": envelope["population"]["fipCount"],
                            "computedAt": envelope["computedAt"],
                        }
                    )
                except Exception as exc:  # noqa: BLE001 - one failed view must not stop the run
                    results.append({"population": phash, "view": view, "error": str(exc)})

        drained = snapshots_module.drain_expired(db)

    payload = {"refreshed": results, "expiredDrained": drained, "hotBucketsRecomputed": hot_buckets}
    if args.json:
        print(json.dumps(payload))
    else:
        print(
            f"refresh-dashboard: {len(results)} view(s) refreshed, {drained} expired "
            f"snapshot(s) drained, {hot_buckets} hot bucket(s)"
        )
        for r in results:
            if "error" in r:
                print(f"  ! {r['population']}/{r['view']}: {r['error']}")
    return 0 if not any("error" in r for r in results) else 1


def _cmd_ingest_network_fips(args: argparse.Namespace) -> int:
    from fipm.network_ingest import ingest_network_fips

    init_db()
    settings = get_settings()
    with SessionLocal() as db:
        report = ingest_network_fips(
            db,
            settings,
            limit=args.limit,
            community_iri=args.community,
            since=args.since,
        )
    if args.json:
        print(json.dumps(report.as_dict()))
    else:
        report.print_report()
    return 0 if not report.errors else 1


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

    backfill_parser = subparsers.add_parser(
        "backfill-declarations",
        help="spec 13 §1.7: (re)populate the dashboard projection for FIPs",
    )
    backfill_parser.add_argument("--batch", type=int, default=500)
    backfill_parser.add_argument("--questionnaire", default=None, help="ID@VERSION")
    backfill_parser.add_argument("--since", default=None, help="ISO8601 updated_at floor")
    backfill_parser.add_argument("--only-stale", action="store_true")
    backfill_parser.add_argument("--fips-from", default=None, help="file of FIP ids, one per line")
    backfill_parser.add_argument("--dry-run", action="store_true")
    backfill_parser.add_argument("--progress", action="store_true")
    backfill_parser.set_defaults(func=_cmd_backfill_declarations)

    check_parser = subparsers.add_parser(
        "check-declarations",
        help="spec 13 §1.7: verify the dashboard projection against fips.answers",
    )
    check_group = check_parser.add_mutually_exclusive_group()
    check_group.add_argument("--sample", type=int, default=1000)
    check_group.add_argument("--all", action="store_true")
    check_parser.add_argument("--fix", action="store_true")
    check_parser.add_argument("--json", action="store_true")
    check_parser.set_defaults(func=_cmd_check_declarations)

    refresh_parser = subparsers.add_parser(
        "refresh-dashboard",
        help="spec 13 §5.3: (re)compute and store dashboard snapshots",
    )
    refresh_group = refresh_parser.add_mutually_exclusive_group(required=True)
    refresh_group.add_argument("--population", default=None, help="a saved population hash")
    refresh_group.add_argument(
        "--all-saved", action="store_true", help="every auth_scope='pub' saved population"
    )
    refresh_parser.add_argument(
        "--views", default=None, help="comma-separated view names (default: all)"
    )
    refresh_parser.add_argument(
        "--force", action="store_true", help="reserved: recompute even if fresh"
    )
    refresh_parser.add_argument("--json", action="store_true")
    refresh_parser.set_defaults(func=_cmd_refresh_dashboard)

    ingest_parser = subparsers.add_parser(
        "ingest-network-fips",
        help="spec 13 §5.4: ingest nanopublication-network FIPs as read-only shadow rows",
    )
    ingest_parser.add_argument("--limit", type=int, default=None)
    ingest_parser.add_argument(
        "--community", default=None, help="one community IRI, instead of all"
    )
    ingest_parser.add_argument(
        "--since", default=None, help="ISO8601: skip communities fetched since"
    )
    ingest_parser.add_argument("--json", action="store_true")
    ingest_parser.set_defaults(func=_cmd_ingest_network_fips)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
