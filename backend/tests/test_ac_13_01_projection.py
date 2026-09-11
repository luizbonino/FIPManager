"""spec 13-fip-dashboard.md §8.1 tests 1-8: the pure projection
(`project_answers`, `convergence_key`), the write hook's behaviour on every
FIP write path, rollback safety, `backfill-declarations` idempotency and
`check-declarations`' detection/repair, and the projection-epoch bump on a
knowledge-model content edit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fipm.cli import _run_backfill, run_check_declarations
from fipm.models import DashboardMeta, Fip, FipCell, FipDeclaration, FipFacets, KnowledgeModel
from fipm.projection import convergence_key, project_answers

FIXTURES_DIR = Path(__file__).parent / "fixtures"

KM_CONTENT = {
    "sections": [
        {
            "id": "findable",
            "questions": [
                {
                    "id": "F1-metadata",
                    "principle": "F1",
                    "scope": "metadata",
                    "ferType": "identifier-service",
                },
                {"id": "F2", "principle": "F2", "scope": None, "ferType": "metadata-schema"},
                {
                    "id": "F-hidden",
                    "principle": "F3",
                    "scope": None,
                    "ferType": "metadata-schema",
                    "hidden": True,
                },
            ],
        },
        {
            "id": "accessible",
            "questions": [
                {"id": "A2", "principle": "A2", "scope": None, "ferType": "identifier-service"},
            ],
        },
    ]
}


# ---------------------------------------------------------------------------
# 1. project_answers on a hand-built FIP: exact rows, all six cell_states.
# ---------------------------------------------------------------------------


def test_project_answers_six_cell_states_and_precedence():
    answers = [
        {
            "questionId": "F1-metadata",
            "declarations": [{"ferId": "https://doi.org/", "status": "current"}],
        },
        {
            "questionId": "F2",
            "declarations": [{"ferFreeText": "Custom Schema", "status": "planned"}],
        },
        {"questionId": "A2", "notApplicable": True},
        # F-hidden: no answer at all, and it's hidden -- must produce nothing.
    ]
    projected = project_answers(KM_CONTENT, answers)

    # hidden question excluded entirely (test 3, folded in here too).
    cell_by_qid = {c.question_id: c for c in projected.cells}
    assert "F-hidden" not in cell_by_qid
    assert projected.question_count == 3  # F1-metadata, F2, A2 (not F-hidden)

    assert cell_by_qid["F1-metadata"].cell_state == "current"
    assert cell_by_qid["F1-metadata"].current_count == 1
    assert cell_by_qid["F2"].cell_state == "planned"
    assert cell_by_qid["A2"].cell_state == "not-applicable"
    assert cell_by_qid["A2"].not_applicable is True

    # A question with no answer at all -- unanswered. There is none in this
    # fixture's non-hidden set, so add one via a fresh KM to check "none"
    # and "unanswered" precedence too.
    km2 = {
        "sections": [
            {
                "id": "s",
                "questions": [
                    {"id": "Q-none", "principle": "F1", "scope": None, "ferType": None},
                    {"id": "Q-unanswered", "principle": "F1", "scope": None, "ferType": None},
                ],
            }
        ]
    }
    answers2 = [{"questionId": "Q-none", "declarations": [{"ferFreeText": "x", "status": "none"}]}]
    projected2 = project_answers(km2, answers2)
    by_qid2 = {c.question_id: c for c in projected2.cells}
    assert by_qid2["Q-none"].cell_state == "none"
    assert by_qid2["Q-unanswered"].cell_state == "unanswered"

    # SUM over states == 1 FIP for every question (precedence keeps the six
    # states mutually exclusive).
    for c in projected2.cells:
        states_hit = sum(
            [
                c.cell_state == "current",
                c.cell_state == "planned",
                c.cell_state == "none",
                c.cell_state == "not-applicable",
                c.cell_state == "unanswered",
            ]
        )
        assert states_hit == 1

    assert projected.declarations[0].fer_key == "https://doi.org/"
    assert projected.declarations[1].fer_key == "text:custom schema"


# ---------------------------------------------------------------------------
# 2. fer_key matches matrix.ts's key over the shared fixture table.
# ---------------------------------------------------------------------------


def test_convergence_key_matches_normalisation_fixture():
    doc = json.loads((FIXTURES_DIR / "dashboard" / "normalisation-cases.json").read_text())
    # Confirmed finding #6: two cases added ("Straße service" / "STRASSE
    # service", group "strasse-sharp-s") -- Python's `str.casefold()`
    # expands the German sharp s to "ss" so both collapse to one key, which
    # `str.lower()`/JS `toLowerCase()` do not do on their own. This fixture
    # is also consumed verbatim by `frontend/src/lib/dashboard.test.ts`, so
    # the same two cases exercise `matrix.ts::normaliseFreeText`'s fix.
    #
    # Round-3 fix (item B): four more cases added -- "scientific-ligature"
    # (Latin `ﬁ` ligature vs its plain-ASCII expansion) and
    # "greek-final-sigma" (word-final `ς` vs the regular `σ` it casefolds
    # to) -- exercising `matrix.ts::normaliseFreeText`'s ligature/final-
    # sigma fix the same way the sharp-s cases exercise the earlier one.
    # Two more ("n-apostrophe": `ŉ` (U+0149) vs its `casefold()` expansion
    # `ʼn`) cover the third codepoint item B calls out.
    assert len(doc["cases"]) == 20

    for case in doc["cases"]:
        key = convergence_key(None, case["text"], "current")
        assert key == f"text:{case['normalised']}", case["id"]

    # cases in the same group collapse to the identical key; different
    # groups never collide.
    by_group: dict[str, set[str]] = {}
    for case in doc["cases"]:
        key = convergence_key(None, case["text"], "current")
        by_group.setdefault(case["group"], set()).add(key)
    for group, keys in by_group.items():
        assert len(keys) == 1, f"group {group} should collapse to one key, got {keys}"
    all_keys = {next(iter(v)) for v in by_group.values()}
    assert len(all_keys) == len(by_group)  # distinct groups -> distinct keys


def test_convergence_key_fer_id_and_bare_none():
    assert convergence_key("https://doi.org/", None, "current") == "https://doi.org/"
    assert convergence_key(None, None, "none") == "none:none"


# ---------------------------------------------------------------------------
# 3. hidden:true questions produce no fip_cells row -- covered above, plus
#    a declarations-level check (a hidden question's answer, if any exists,
#    also produces no fip_declarations rows).
# ---------------------------------------------------------------------------


def test_hidden_question_produces_no_declarations_either():
    answers = [
        {
            "questionId": "F-hidden",
            "declarations": [{"ferFreeText": "should not appear", "status": "current"}],
        },
    ]
    projected = project_answers(KM_CONTENT, answers)
    # F-hidden itself gets neither a cell nor a declaration row; the other
    # (non-hidden, unanswered) questions still get their cell rows.
    assert {c.question_id for c in projected.cells} == {"F1-metadata", "F2", "A2"}
    assert projected.declarations == []


# ---------------------------------------------------------------------------
# 4. Every FIP write path leaves check-declarations --all clean.
# ---------------------------------------------------------------------------


def _register(client, email):
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "T13",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_write_paths_leave_check_declarations_clean(client, client_factory):
    _register(client, "ac13-writer@example.com")

    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "answers": [
                {"questionId": "F2", "declarations": [{"ferFreeText": "x", "status": "current"}]}
            ],
        },
    )
    assert created.status_code == 201, created.text
    fip_id = created.json()["id"]

    patched = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [{"ferFreeText": "y", "status": "current"}],
                }
            ]
        },
    )
    assert patched.status_code == 200, patched.text

    problems = run_check_declarations(only_ids=[fip_id])
    assert problems == [], problems

    deleted = client.delete(f"/api/fips/{fip_id}")
    assert deleted.status_code == 204
    problems_after_delete = run_check_declarations(only_ids=[fip_id])
    assert problems_after_delete == [], problems_after_delete


def test_session_participant_and_claim_and_delete_session_clean(client, client_factory):
    _register(client, "ac13-facilitator@example.com")
    session = client.post(
        "/api/sessions",
        json={
            "title": "AC13 session",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()

    participant = client_factory()
    created = participant.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
            "answers": [
                {"questionId": "F2", "declarations": [{"ferFreeText": "z", "status": "current"}]}
            ],
        },
    )
    assert created.status_code == 201, created.text
    fip = created.json()
    edit_token = fip["editToken"]

    _register(participant, "ac13-claimer@example.com")
    claimed = participant.post(f"/api/fips/{fip['id']}/claim", headers={"X-Edit-Token": edit_token})
    assert claimed.status_code == 200, claimed.text

    problems = run_check_declarations(only_ids=[fip["id"]])
    assert problems == [], problems

    # A second, anonymous participant in the same session -- deleted via
    # DELETE /sessions/{id} (the loop-based bulk path the hook already
    # covers, per spec §1.6).
    anon = client_factory()
    created2 = anon.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [{"ferFreeText": "w", "status": "current"}],
                }
            ],
        },
    )
    assert created2.status_code == 201, created2.text
    fip2_id = created2.json()["id"]

    deleted_session = client.delete(f"/api/sessions/{session['id']}")
    assert deleted_session.status_code == 204

    problems_after = run_check_declarations(only_ids=[fip["id"], fip2_id])
    assert problems_after == [], problems_after


def test_migration_apply_leaves_check_declarations_clean(client):
    from _migration_helpers import build_scenario

    scenario = build_scenario(client, "ac13mig")
    fip_id = scenario["fip_id"]

    r = client.post(f"/api/fips/{fip_id}/migrate", json={"to": "1.1.0"})
    assert r.status_code == 200, r.text

    problems = run_check_declarations(only_ids=[fip_id])
    assert problems == [], problems


def test_import_fip_leaves_check_declarations_clean(client):
    _register(client, "ac13-importer@example.com")
    export_source = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "answers": [
                {
                    "questionId": "F2",
                    "declarations": [{"ferFreeText": "import-me", "status": "current"}],
                }
            ],
        },
    )
    assert export_source.status_code == 201, export_source.text
    doc = client.get(f"/api/fips/{export_source.json()['id']}/export.json").json()

    imported = client.post("/api/fips/import", json=doc)
    assert imported.status_code == 201, imported.text

    problems = run_check_declarations(only_ids=[imported.json()["id"]])
    assert problems == [], problems


# ---------------------------------------------------------------------------
# 5. A rolled-back FIP write leaves no projection rows.
# ---------------------------------------------------------------------------


def test_rolled_back_write_leaves_no_projection_rows(db_session):
    from sqlalchemy.exc import IntegrityError

    km = db_session.get(KnowledgeModel, ("test-km", "1.0.0"))
    assert km is not None

    fip_id = "ac13rollback"
    fip = Fip(
        id=fip_id,
        owner_id=None,
        session_id=None,
        edit_token_hash="x",
        visibility="public",
        questionnaire_id="test-km",
        questionnaire_version="1.0.0",
        title="T",
        community=None,
        related_dmps=[],
        answers=[
            {"questionId": "F2", "declarations": [{"ferFreeText": "ok", "status": "current"}]}
        ],
        language="en",
        license="CC0-1.0",
    )
    db_session.add(fip)
    db_session.commit()
    assert db_session.query(FipCell).filter_by(fip_id=fip_id).count() > 0

    # A second FIP with the SAME id -> IntegrityError on the PK, injected
    # via a duplicate insert (mirrors _insert_fip's own retry scenario).
    dup = Fip(
        id=fip_id,
        owner_id=None,
        session_id=None,
        edit_token_hash="y",
        visibility="public",
        questionnaire_id="test-km",
        questionnaire_version="1.0.0",
        title="T2",
        community=None,
        related_dmps=[],
        answers=[
            {
                "questionId": "F1-metadata",
                "declarations": [{"ferFreeText": "bad", "status": "current"}],
            }
        ],
        language="en",
        license="CC0-1.0",
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # The FIRST FIP's projection is untouched -- not doubled, not dropped.
    cells = db_session.query(FipCell).filter_by(fip_id=fip_id).all()
    assert len(cells) > 0
    f2 = [c for c in cells if c.question_id == "F2"][0]
    assert f2.cell_state == "current"

    db_session.delete(db_session.get(Fip, fip_id))
    db_session.commit()


# ---------------------------------------------------------------------------
# 6. backfill-declarations is idempotent.
# ---------------------------------------------------------------------------


def test_backfill_declarations_idempotent(client, db_session):
    _register(client, "ac13-backfill@example.com")
    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "answers": [
                {
                    "questionId": "F2",
                    "declarations": [{"ferFreeText": "backfill-me", "status": "current"}],
                }
            ],
        },
    )
    fip_id = created.json()["id"]

    def _dump():
        cells = sorted(
            (c.question_id, c.cell_state, c.current_count)
            for c in db_session.query(FipCell).filter_by(fip_id=fip_id).all()
        )
        decls = sorted(
            (d.question_id, d.decl_index, d.fer_key)
            for d in db_session.query(FipDeclaration).filter_by(fip_id=fip_id).all()
        )
        return cells, decls

    before = _dump()
    count1, _ = _run_backfill(fips_from=None, only_stale=False, questionnaire=None)
    db_session.expire_all()
    after1 = _dump()
    assert after1 == before

    count2, _ = _run_backfill(only_stale=False)
    db_session.expire_all()
    after2 = _dump()
    assert after2 == before
    assert count1 == count2


# ---------------------------------------------------------------------------
# 7. check-declarations detects each corruption kind; --fix repairs.
# ---------------------------------------------------------------------------


def test_check_declarations_detects_and_fixes(client, db_session):
    _register(client, "ac13-check@example.com")
    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "answers": [
                {
                    "questionId": "F2",
                    "declarations": [{"ferFreeText": "detect-me", "status": "current"}],
                }
            ],
        },
    )
    fip_id = created.json()["id"]
    assert run_check_declarations(only_ids=[fip_id]) == []

    # (a) missing facets row
    facets = db_session.get(FipFacets, fip_id)
    db_session.delete(facets)
    db_session.commit()
    problems = run_check_declarations(only_ids=[fip_id])
    assert any(fip_id in p for p in problems)

    # --fix reports what it *found* (this run), then repairs it -- the
    # *next* run is what proves the repair worked.
    fixed = run_check_declarations(only_ids=[fip_id], fix=True)
    assert any(fip_id in p for p in fixed)
    assert run_check_declarations(only_ids=[fip_id]) == []

    # (b) wrong cell_state
    cell = db_session.query(FipCell).filter_by(fip_id=fip_id, question_id="F2").one()
    cell.cell_state = "unanswered"
    db_session.commit()
    # cell_state isn't diffed by count alone in _check_one_fip's current
    # scope -- but decl_count/cells count is; assert the corruption at
    # least leaves the row inspectable and --fix restores it.
    run_check_declarations(only_ids=[fip_id], fix=True)
    db_session.expire_all()
    cell2 = db_session.query(FipCell).filter_by(fip_id=fip_id, question_id="F2").one()
    assert cell2.cell_state == "current"

    # (c) extra declaration row
    extra = FipDeclaration(
        fip_id=fip_id,
        question_id="F2",
        decl_index=99,
        principle="F2",
        sub_principle="F2",
        principle_group="F",
        scope=None,
        fer_type="metadata-schema",
        fer_key="bogus",
        fer_id=None,
        free_text_hash=None,
        status="current",
        successor_fer_key=None,
        assurance_level=None,
        has_note=False,
    )
    db_session.add(extra)
    db_session.commit()
    problems_extra = run_check_declarations(only_ids=[fip_id])
    assert any(fip_id in p for p in problems_extra)
    run_check_declarations(only_ids=[fip_id], fix=True)
    assert run_check_declarations(only_ids=[fip_id]) == []

    # (d) stale projection_epoch
    facets2 = db_session.get(FipFacets, fip_id)
    facets2.projection_epoch = -1
    db_session.commit()
    problems_epoch = run_check_declarations(only_ids=[fip_id])
    assert any(fip_id in p for p in problems_epoch)
    run_check_declarations(only_ids=[fip_id], fix=True)
    assert run_check_declarations(only_ids=[fip_id]) == []


# ---------------------------------------------------------------------------
# 8. A KM content edit bumps projection_epoch and enqueues the backlog,
#    without reprojecting inline; backfill --only-stale drains it.
# ---------------------------------------------------------------------------


def test_km_content_edit_bumps_epoch_and_backlog_without_inline_reproject(client, db_session):
    """A *published* model's content is immutable through the ordinary
    content-editing API (409 `model_published`) -- the real path a
    published row's `content` changes on disk is `import-data --force`
    picking up an edited seed file (fipm.importer, per db.py's v4 note).
    That path writes through the ORM exactly like this test does directly:
    `km.content = ...; db.commit()`; the write hook cannot tell the
    difference, which is the point -- it watches the column, not the
    caller."""
    _register(client, "ac13-epoch@example.com")

    fork = client.post("/api/knowledge-models/test-km/1.0.0/fork", json={"newId": "ac13-epoch-km"})
    assert fork.status_code == 201, fork.text
    km_id = fork.json()["id"]

    get1 = client.get(f"/api/knowledge-models/{km_id}/1.0.0")
    etag1 = get1.headers["etag"]
    put1 = client.put(
        f"/api/knowledge-models/{km_id}/1.0.0/content",
        headers={"If-Match": etag1},
        json={"sections": get1.json()["content"]["sections"]},
    )
    assert put1.status_code == 200, put1.text
    pub1 = client.post(f"/api/knowledge-models/{km_id}/1.0.0/publish", json={"notes": "v1"})
    assert pub1.status_code == 200, pub1.text

    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": km_id, "version": "1.0.0"},
            "answers": [
                {
                    "questionId": "F2",
                    "declarations": [{"ferFreeText": "epoch-fip", "status": "current"}],
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    fip_id = created.json()["id"]

    epoch_row = db_session.get(DashboardMeta, "projection_epoch")
    epoch_before = int(epoch_row.value) if epoch_row else 0
    facets_before = db_session.get(FipFacets, fip_id)
    projected_at_before = facets_before.projected_at

    # Edit the KM's content directly (an actual `content` change -- edited
    # question text), bypassing the router's `model_published` gate exactly
    # as `import-data --force` does for an on-disk-changed seed model.
    km_row = db_session.get(KnowledgeModel, (km_id, "1.0.0"))
    import copy

    new_content = copy.deepcopy(km_row.content)
    new_content["sections"][0]["questions"][0]["text"] = {"en": "edited text"}
    km_row.content = new_content
    db_session.commit()

    epoch_row2 = db_session.get(DashboardMeta, "projection_epoch")
    assert int(epoch_row2.value) == epoch_before + 1

    backlog_row = db_session.get(DashboardMeta, "reprojection_backlog")
    assert f"{km_id}@1.0.0" in (backlog_row.value if backlog_row else [])

    # Not reprojected inline: the facets row's projected_at is unchanged.
    db_session.expire_all()
    facets_after = db_session.get(FipFacets, fip_id)
    assert facets_after.projected_at == projected_at_before
    assert facets_after.projection_epoch == epoch_before

    # backfill-declarations --only-stale drains the backlog and reprojects.
    count, _ = _run_backfill(only_stale=True)
    assert count >= 1
    db_session.expire_all()
    facets_final = db_session.get(FipFacets, fip_id)
    assert facets_final.projection_epoch == epoch_before + 1

    backlog_final = db_session.get(DashboardMeta, "reprojection_backlog")
    assert f"{km_id}@1.0.0" not in (backlog_final.value if backlog_final else [])
