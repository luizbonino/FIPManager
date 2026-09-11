"""spec 13-fip-dashboard.md §8.2: `generate_fips.py --n N --seed S --out DB`
builds a realistic FIP population directly into a fresh SQLite database,
standard library only, for `test_scale_13_dashboard.py`. Not collected by
pytest (no `test_` prefix).

Brief B adds the two parts of the spec's recipe brief A's own generator
left out (documented there as "brief B's job", since they exist only to
exercise MinHash/LSH candidate generation): `N_CLUSTER_SEEDS` cluster
seeds (40% of FIPs are a 3-field mutation of one seed, so clusters
genuinely exist and LSH recall is measurable) and one `HOT_BUCKET_SIZE`-FIP
group of bit-identical declarations (the hot-bucket case, §4.4). It also
writes `fip_signatures`/`fip_signature_bands` directly (bypassing the ORM
write hook, same reasoning as `_write_projection_row`'s existing cells/
declarations/facets) and refreshes `lsh_hot_buckets` once at the end, so
the generated database is immediately usable by `neighbours`/`clusters`/
`map`, not just the four brief-A views.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import insert

BACKEND_DIR = Path(__file__).resolve().parents[2]
REAL_KM_PATH = BACKEND_DIR.parent / "data" / "knowledge-models" / "gofair-fip-mini-1.0.0.json"
FIXTURE_KM_PATH = (
    BACKEND_DIR / "tests" / "fixtures" / "knowledge-models" / "gofair-fip-mini-1.0.0.json"
)

N_SEED_FERS = 138
FREE_TEXT_POOL_SIZE = 300
N_SESSIONS = 50
N_QUESTIONNAIRE_VERSIONS = 5
N_BUCKETS = 4  # every FIP lands in bucket i % N_BUCKETS -- gives an exact N/4 sub-population
N_CLUSTER_SEEDS = 30
CLUSTER_SEED_SHARE = 0.40
HOT_BUCKET_QUESTION_IDS = ("F1-metadata", "F2", "F3", "A2")


def _km_content() -> dict[str, Any]:
    path = REAL_KM_PATH if REAL_KM_PATH.is_file() else FIXTURE_KM_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def _zipf_weights(n: int, s: float = 1.1) -> list[float]:
    return [1.0 / (rank**s) for rank in range(1, n + 1)]


def _free_text_pool(rng: random.Random) -> list[str]:
    """`FREE_TEXT_POOL_SIZE` phrases with deliberate near-duplicates (case,
    whitespace, accents) so the convergence key (§1.5) earns its keep."""
    bases = [f"Custom resource variant {i}" for i in range(FREE_TEXT_POOL_SIZE // 3)]
    pool: list[str] = []
    for base in bases:
        pool.append(base)
        pool.append(base.upper())
        pool.append(f"  {base}  ")
    rng.shuffle(pool)
    return pool[:FREE_TEXT_POOL_SIZE]


def generate(
    db_path: str, n: int, seed: int = 20260911, *, progress: bool = False
) -> dict[str, float]:
    """Writes `n` FIPs (plus their questionnaire refs, sessions and
    projection) into a fresh database at `db_path`. Returns
    `{"generate_seconds": ..., "project_seconds": ..., "fips_per_second": ...}`.

    **Must run in a fresh interpreter process** (invoked via `main()`, which
    `test_scale_13_dashboard.py` runs with `subprocess.run([sys.executable,
    __file__, ...])`) -- `fipm.db` binds its engine to `FIPM_DB_PATH` at
    *import* time, so this function sets the env var before its first
    `import fipm.db` rather than trying to rebind an already-imported
    engine, which would leave stray connections open against whatever
    database the calling process's `fipm.db` was first imported against."""
    import os

    os.environ["FIPM_DB_PATH"] = db_path
    os.environ.setdefault("FIPM_DATA_DIR", str(BACKEND_DIR / "tests" / "fixtures"))
    os.environ.setdefault("FIPM_STATIC_DIR", str(BACKEND_DIR / "tests" / "fixtures" / "no-static"))
    os.environ.setdefault("FIPM_BASE_URL", "http://scaletest")
    os.environ.setdefault("FIPM_SECRET_KEY", "scale-test-secret")

    import fipm.db as db_module
    from fipm.models import Fip, KnowledgeModel, WorkshopSession
    from fipm.projection import project_answers, projection_suspended

    db_module.init_db()

    rng = random.Random(seed)
    km_content = _km_content()
    question_ids = [q["id"] for s in km_content["sections"] for q in s["questions"]]
    fer_pool = [f"https://fer-scale-test.example/fer-{i:04d}" for i in range(N_SEED_FERS)]
    fer_weights = _zipf_weights(N_SEED_FERS)
    free_text_pool = _free_text_pool(rng)

    # §8.2's cluster seeds: N_CLUSTER_SEEDS fixed declaration sets over a
    # handful of questions, each drawing from the same `fer_pool` so
    # cross-seed collisions are possible (realistic) but rare (each seed's
    # own combination is what makes it a seed).
    cluster_seed_question_ids = question_ids[: min(6, len(question_ids))]
    cluster_seeds = [
        [
            {
                "questionId": qid,
                "declarations": [{"ferId": rng.choice(fer_pool), "status": "current"}],
            }
            for qid in cluster_seed_question_ids
        ]
        for _ in range(N_CLUSTER_SEEDS)
    ]

    # The hot-bucket case: HOT_BUCKET_SIZE FIPs (bounded so a small `n`
    # doesn't make this the entire population) share one bit-identical
    # declaration set.
    hot_bucket_size = min(200, max(0, n // 3))
    hot_bucket_answers = [
        {
            "questionId": qid,
            "declarations": [
                {"ferId": f"https://fer-scale-test.example/hot-{qid}", "status": "current"}
            ],
        }
        for qid in HOT_BUCKET_QUESTION_IDS
        if qid in question_ids
    ]

    t0 = time.monotonic()
    with db_module.SessionLocal() as s:
        km_rows = []
        for v in range(N_QUESTIONNAIRE_VERSIONS):
            version = f"1.{v}.0"
            km_rows.append(
                {
                    "id": "gofair-fip-mini",
                    "version": version,
                    "owner_id": None,
                    "visibility": "public",
                    "status": "published",
                    "license": "CC0-1.0",
                    "source": "scale-test",
                    "is_system": True,
                    "title": {"en": f"Scale test KM v{version}"},
                    "description": {"en": "scale test"},
                    "changelog": [],
                    "content": km_content,
                    "content_sha256": f"scale-{version}",
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            )
        s.execute(insert(KnowledgeModel), km_rows)

        session_rows = [
            {
                "id": f"scale-session-{i:04d}",
                "join_code": f"S{i:05d}",
                "owner_id": None,
                "questionnaire_id": "gofair-fip-mini",
                "questionnaire_version": "1.0.0",
                "questionnaire_refs": None,
                "default_language": "en",
                "title": f"scale session {i}",
                "status": "open",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
            for i in range(N_SESSIONS)
        ]
        s.execute(insert(WorkshopSession), session_rows)
        s.commit()

        now = datetime.now(UTC)
        fip_rows = []
        for i in range(n):
            if i < hot_bucket_size:
                # Bit-identical: no per-question randomness at all.
                answers = json.loads(json.dumps(hot_bucket_answers))
                visibility_roll = rng.random()
                visibility = (
                    "public"
                    if visibility_roll < 0.7
                    else ("link" if visibility_roll < 0.9 else "private")
                )
                bucket = i % N_BUCKETS
                km_version = f"1.{i % N_QUESTIONNAIRE_VERSIONS}.0"
                fip_rows.append(
                    {
                        "id": f"scalefip{i:07d}",
                        "owner_id": None,
                        "session_id": f"scale-session-{i % N_SESSIONS:04d}",
                        "edit_token_hash": "x",
                        "visibility": visibility,
                        "questionnaire_id": "gofair-fip-mini",
                        "questionnaire_version": km_version,
                        "title": f"Scale FIP {i}",
                        "community": {"name": f"Scale community {i}", "bucket": bucket},
                        "related_dmps": [],
                        "answers": answers,
                        "language": "en",
                        "license": "CC0-1.0",
                        "created_at": now - timedelta(days=rng.randint(0, 365)),
                        "updated_at": now - timedelta(days=rng.randint(0, 30)),
                    }
                )
                continue
            if rng.random() < CLUSTER_SEED_SHARE:
                seed = cluster_seeds[i % N_CLUSTER_SEEDS]
                answers = json.loads(json.dumps(seed))
                # spec §8.2: "a mutation (3 random changes) of one seed".
                for _ in range(3):
                    target = rng.choice(answers)
                    target["declarations"][0]["ferId"] = rng.choices(
                        fer_pool, weights=fer_weights, k=1
                    )[0]
                visibility_roll = rng.random()
                visibility = (
                    "public"
                    if visibility_roll < 0.7
                    else ("link" if visibility_roll < 0.9 else "private")
                )
                bucket = i % N_BUCKETS
                km_version = f"1.{i % N_QUESTIONNAIRE_VERSIONS}.0"
                fip_rows.append(
                    {
                        "id": f"scalefip{i:07d}",
                        "owner_id": None,
                        "session_id": f"scale-session-{i % N_SESSIONS:04d}",
                        "edit_token_hash": "x",
                        "visibility": visibility,
                        "questionnaire_id": "gofair-fip-mini",
                        "questionnaire_version": km_version,
                        "title": f"Scale FIP {i}",
                        "community": {"name": f"Scale community {i}", "bucket": bucket},
                        "related_dmps": [],
                        "answers": answers,
                        "language": "en",
                        "license": "CC0-1.0",
                        "created_at": now - timedelta(days=rng.randint(0, 365)),
                        "updated_at": now - timedelta(days=rng.randint(0, 30)),
                    }
                )
                continue
            answers = []
            for qid in question_ids:
                roll = rng.random()
                if roll < 0.25:
                    continue  # unanswered
                if roll < 0.30:
                    answers.append({"questionId": qid, "notApplicable": True})
                    continue
                if roll < 0.38:  # planned* (~8%)
                    status = rng.choice(["planned", "planned-development", "planned-replacement"])
                elif roll < 0.41:  # none (~3%)
                    status = "none"
                else:
                    status = "current"

                if rng.random() < 0.12:
                    text = rng.choice(free_text_pool)
                    decl: dict[str, Any] = {"ferFreeText": text, "status": status}
                else:
                    fer_id = rng.choices(fer_pool, weights=fer_weights, k=1)[0]
                    decl = {"ferId": fer_id, "status": status}
                answers.append({"questionId": qid, "declarations": [decl]})

            visibility_roll = rng.random()
            visibility = (
                "public"
                if visibility_roll < 0.7
                else ("link" if visibility_roll < 0.9 else "private")
            )
            bucket = i % N_BUCKETS
            km_version = f"1.{i % N_QUESTIONNAIRE_VERSIONS}.0"
            fip_rows.append(
                {
                    "id": f"scalefip{i:07d}",
                    "owner_id": None,
                    "session_id": f"scale-session-{i % N_SESSIONS:04d}",
                    "edit_token_hash": "x",
                    "visibility": visibility,
                    "questionnaire_id": "gofair-fip-mini",
                    "questionnaire_version": km_version,
                    "title": f"Scale FIP {i}",
                    "community": {"name": f"Scale community {i}", "bucket": bucket},
                    "related_dmps": [],
                    "answers": answers,
                    "language": "en",
                    "license": "CC0-1.0",
                    "created_at": now - timedelta(days=rng.randint(0, 365)),
                    "updated_at": now - timedelta(days=rng.randint(0, 30)),
                }
            )
        for start in range(0, len(fip_rows), 1000):
            s.execute(insert(Fip), fip_rows[start : start + 1000])
            s.commit()
            if progress:
                print(f"inserted {min(start + 1000, len(fip_rows))}/{len(fip_rows)}")
    generate_seconds = time.monotonic() - t0

    t1 = time.monotonic()
    with db_module.SessionLocal() as s:
        with projection_suspended():
            for idx, fip_id in enumerate([r["id"] for r in fip_rows], start=1):
                fip = s.get(Fip, fip_id)
                km = s.get(KnowledgeModel, (fip.questionnaire_id, fip.questionnaire_version))
                projected = project_answers(km.content if km else None, fip.answers)
                _write_projection_row(s, fip, projected)
                if idx % 500 == 0:
                    s.commit()
                    if progress:
                        print(f"projected {idx}/{n}")
            s.commit()

        from fipm.dashboard.similarity_views import refresh_hot_buckets

        hot_buckets_written = refresh_hot_buckets(s)
        if progress:
            print(f"hot buckets: {hot_buckets_written}")
    project_seconds = time.monotonic() - t1

    return {
        "generate_seconds": generate_seconds,
        "project_seconds": project_seconds,
        "fips_per_second_generate": n / generate_seconds if generate_seconds else float("inf"),
        "fips_per_second_project": n / project_seconds if project_seconds else float("inf"),
        "hot_bucket_fips": hot_bucket_size,
        "hot_buckets_written": hot_buckets_written,
    }


def _write_projection_row(s, fip, projected) -> None:  # noqa: ANN001
    """Writes one FIP's projection rows directly (the `reproject_fip` body,
    inlined here so this module has no import-order dependency on
    `fipm.db`'s module-level engine having already been repointed)."""
    from fipm.models import DashboardMeta, FipCell, FipDeclaration, FipFacets

    epoch_row = s.get(DashboardMeta, "projection_epoch")
    epoch = int(epoch_row.value) if epoch_row else 0
    now = datetime.now(UTC)
    s.add(
        FipFacets(
            fip_id=fip.id,
            source="local",
            questionnaire_id=fip.questionnaire_id,
            questionnaire_version=fip.questionnaire_version,
            area_key=f"{fip.questionnaire_id}@{fip.questionnaire_version}",
            language=fip.language,
            question_count=projected.question_count,
            answered_questions=projected.answered_questions,
            not_applicable_questions=projected.not_applicable_questions,
            declaration_count=projected.declaration_count,
            current_declarations=projected.current_declarations,
            token_count=projected.token_count,
            migrated_from_id=None,
            migrated_from_version=None,
            fip_created_at=fip.created_at,
            fip_updated_at=fip.updated_at,
            projected_at=now,
            projection_epoch=epoch,
        )
    )
    for cell in projected.cells:
        s.add(
            FipCell(
                fip_id=fip.id,
                question_id=cell.question_id,
                question_index=cell.question_index,
                principle=cell.principle,
                sub_principle=cell.sub_principle,
                principle_group=cell.principle_group,
                principle_known=cell.principle_known,
                scope=cell.scope,
                fer_type=cell.fer_type,
                cell_state=cell.cell_state,
                decl_count=cell.decl_count,
                current_count=cell.current_count,
                planned_count=cell.planned_count,
                none_count=cell.none_count,
                not_applicable=cell.not_applicable,
            )
        )
    for decl in projected.declarations:
        s.add(
            FipDeclaration(
                fip_id=fip.id,
                question_id=decl.question_id,
                decl_index=decl.decl_index,
                principle=decl.principle,
                sub_principle=decl.sub_principle,
                principle_group=decl.principle_group,
                scope=decl.scope,
                fer_type=decl.fer_type,
                fer_key=decl.fer_key,
                fer_id=decl.fer_id,
                free_text_hash=decl.free_text_hash,
                status=decl.status,
                successor_fer_key=decl.successor_fer_key,
                assurance_level=None,
                has_note=decl.has_note,
            )
        )

    # Brief B: signatures/bands (§4.2) and fer_key_df (§4.3), via the same
    # public helpers `reproject_fip` itself calls -- so a scale-generated
    # database's signatures are byte-identical to what the real write path
    # would have produced for the same declarations.
    from fipm.projection import bump_fer_key_df, write_signature_rows

    write_signature_rows(s, fip.id, projected.cells, projected.declarations, computed_at=now)
    bump_fer_key_df(s, projected.declarations, sign=1, public=(fip.visibility == "public"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260911)
    parser.add_argument("--out", required=True)
    parser.add_argument("--progress", action="store_true")
    args = parser.parse_args()
    stats = generate(args.out, args.n, args.seed, progress=args.progress)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
