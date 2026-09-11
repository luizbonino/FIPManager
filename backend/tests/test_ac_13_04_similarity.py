"""spec 13-fip-dashboard.md §8.1 tests 24-32: the exact §4.1 similarity
measure (checked against an independent brute-force reference, AC-24),
LSH-vs-exact cluster agreement, assumption A2, the two candidate-generation
guards (popular-key skip, posting cap), the hot-bucket guard, signature
determinism, and pair's 404-not-403 rule."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fipm.dashboard import similarity_views as sv
from fipm.dashboard.populations import parse_population_spec
from fipm.ids import new_user_id
from fipm.models import Fip, FipSignature, FipSignatureBand, User, WorkshopSession

KM_ID = "gofair-fip-mini"
KM_VERSION = "1.0.0"
_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "knowledge-models"
_KM_CONTENT = json.loads((_FIXTURES_DIR / f"{KM_ID}-{KM_VERSION}.json").read_text())
_QUESTIONS = [q for s in _KM_CONTENT["sections"] for q in s["questions"]]
_PRINCIPLE_BY_QID = {q["id"]: q["principle"] for q in _QUESTIONS}


# ---------------------------------------------------------------------------
# Independent brute-force reference for §4.1 -- written directly against
# the raw `answers` shape, calling neither `fipm.similarity` nor
# `fipm.projection`. This is the oracle AC-24 checks the production code
# against.
# ---------------------------------------------------------------------------


def _bruteforce_key_sets(answers: list[dict], *, statuses: str) -> dict[str, set[str]]:
    wanted = {"current"}
    if statuses == "currentPlanned":
        wanted |= {"planned", "planned-development", "planned-replacement"}
    by_q = {a["questionId"]: a for a in answers}
    out: dict[str, set[str]] = {}
    for q in _QUESTIONS:
        qid = q["id"]
        ans = by_q.get(qid)
        keys: set[str] = set()
        if ans:
            if ans.get("notApplicable"):
                keys.add("NA")
            for d in ans.get("declarations") or []:
                status = d.get("status")
                if status not in wanted:
                    continue
                if d.get("ferId"):
                    keys.add(d["ferId"])
                elif d.get("ferFreeText"):
                    normalised = " ".join(d["ferFreeText"].split()).strip().casefold()
                    keys.add(f"text:{normalised}")
                else:
                    keys.add(f"none:{status}")
        out[qid] = keys
    return out


def _bruteforce_overall(
    a_answers, b_answers, *, weighting: str, statuses: str = "current"
) -> float:
    a_sets = _bruteforce_key_sets(a_answers, statuses=statuses)
    b_sets = _bruteforce_key_sets(b_answers, statuses=statuses)
    per_question: dict[str, float] = {}
    for q in _QUESTIONS:
        qid = q["id"]
        sa, sb = a_sets[qid], b_sets[qid]
        if not sa and not sb:
            continue
        per_question[qid] = len(sa & sb) / len(sa | sb)

    if weighting == "question":
        vals = list(per_question.values())
        return sum(vals) / len(vals) if vals else 0.0

    by_principle: dict[str, list[float]] = {}
    for q in _QUESTIONS:
        qid = q["id"]
        if qid in per_question:
            by_principle.setdefault(q["principle"], []).append(per_question[qid])
    principle_means = {p: sum(v) / len(v) for p, v in by_principle.items()}

    if weighting == "principle":
        vals = list(principle_means.values())
        return sum(vals) / len(vals) if vals else 0.0

    by_letter: dict[str, list[float]] = {}
    for p, v in principle_means.items():
        by_letter.setdefault(p[0], []).append(v)
    letter_means = [sum(v) / len(v) for v in by_letter.values()]
    return sum(letter_means) / len(letter_means) if letter_means else 0.0


def _make_fip(db_session, fip_id, answers, *, visibility="public", owner_id=None, session_id=None):
    fip = Fip(
        id=fip_id,
        owner_id=owner_id,
        session_id=session_id,
        edit_token_hash="x" if owner_id is None else None,
        visibility=visibility,
        questionnaire_id=KM_ID,
        questionnaire_version=KM_VERSION,
        title=fip_id,
        community={"name": fip_id},
        related_dmps=[],
        answers=answers,
        language="en",
        license="CC0-1.0",
    )
    db_session.add(fip)
    db_session.commit()
    return fip


def _make_session(db_session, session_id: str) -> None:
    """`Fip.session_id` is a real FK to `workshop_sessions.id` -- a fixture
    session for population-scoping (see `_session_population` below) needs
    a row to point to, even though nothing in these tests ever joins the
    workshop-session flow itself."""
    if db_session.get(WorkshopSession, session_id) is not None:
        return
    db_session.add(
        WorkshopSession(
            id=session_id,
            join_code=session_id[:6].upper().ljust(6, "0"),
            owner_id=None,
            questionnaire_id=KM_ID,
            questionnaire_version=KM_VERSION,
            questionnaire_refs=None,
            default_language="en",
            title=session_id,
            status="open",
        )
    )
    db_session.commit()


def _session_population(session_id: str) -> dict:
    """Every test in this file shares one session-scoped SQLite database
    (per the project's test convention), so a `{"kind": "public"}` or
    `{"kind": "questionnaire", ...}` population would pick up *every other
    test's* FIPs too. Scoping to a unique, per-test `session_id` isolates
    each test's own fixture population -- `Fip.session_id` needs no real
    `WorkshopSession` row for population resolution to filter on it."""
    return parse_population_spec({"include": [{"kind": "session", "id": session_id}]})


def _decl(fer_id=None, free_text=None, status="current"):
    d = {"status": status}
    if fer_id:
        d["ferId"] = fer_id
    if free_text:
        d["ferFreeText"] = free_text
    return d


def _answer(question_id, *, declarations=None, not_applicable=False):
    if not_applicable:
        return {"questionId": question_id, "notApplicable": True}
    return {"questionId": question_id, "declarations": declarations or []}


# ---------------------------------------------------------------------------
# 24. The invariant: neighbours/pair scores match the brute-force reference,
# for all three weightings, for a small fixture population.
# ---------------------------------------------------------------------------


def test_neighbours_and_pair_scores_match_bruteforce_reference(app, db_session, client):
    answers_by_fip = {
        "sim24-a": [
            _answer("F1-metadata", declarations=[_decl(fer_id="https://www.doi.org/")]),
            _answer("F2", declarations=[_decl(fer_id="https://www.handle.net/")]),
            _answer("A2", not_applicable=True),
            _answer("I1-metadata", declarations=[_decl(free_text="Custom vocabulary Alpha")]),
        ],
        "sim24-b": [
            _answer("F1-metadata", declarations=[_decl(fer_id="https://www.doi.org/")]),
            _answer("F2", declarations=[_decl(fer_id="https://orcid.org/")]),
            _answer("A2", not_applicable=True),
            _answer("I1-metadata", declarations=[_decl(free_text="  CUSTOM VOCABULARY alpha  ")]),
        ],
        "sim24-c": [
            _answer("F1-metadata", declarations=[_decl(fer_id="https://ror.org/")]),
            _answer("F3", declarations=[_decl(fer_id="https://www.handle.net/")]),
        ],
    }
    _make_session(db_session, "sim24-sess")
    for fip_id, answers in answers_by_fip.items():
        _make_fip(db_session, fip_id, answers, session_id="sim24-sess")

    ids = list(answers_by_fip)
    for weighting in ("principle", "question", "letter"):
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]
                r = client.get(
                    "/api/dashboard/similarity/pair",
                    params={"a": a, "b": b, "weighting": weighting},
                )
                assert r.status_code == 200, r.text
                expected = _bruteforce_overall(
                    answers_by_fip[a], answers_by_fip[b], weighting=weighting
                )
                assert r.json()["data"]["overall"] == pytest.approx(expected, abs=1e-9), (
                    a,
                    b,
                    weighting,
                )

        # neighbours: candidate generation may change *which* FIPs appear,
        # never the score of one that does.
        for subject in ids:
            r = client.get(
                "/api/dashboard/similarity/neighbours",
                params={
                    "fip": subject,
                    "pop": "session:sim24-sess",
                    "weighting": weighting,
                    "limit": 100,
                },
            )
            assert r.status_code == 200, r.text
            for row in r.json()["data"]["neighbours"]:
                expected = _bruteforce_overall(
                    answers_by_fip[subject], answers_by_fip[row["fipId"]], weighting=weighting
                )
                assert row["similarity"] == pytest.approx(expected, abs=1e-9), (
                    subject,
                    row["fipId"],
                    weighting,
                )


# ---------------------------------------------------------------------------
# 26. Assumption A2.
# ---------------------------------------------------------------------------


def test_assumption_a2_not_applicable_scoring(app, db_session, client):
    a = _make_fip(
        db_session,
        "sim26-a",
        [
            _answer("F3", not_applicable=True),
            _answer("F1-metadata", declarations=[_decl(fer_id="https://www.doi.org/")]),
        ],
    )
    b_both_na = _make_fip(db_session, "sim26-b1", [_answer("F3", not_applicable=True)])
    b_one_sided = _make_fip(
        db_session, "sim26-b2", [_answer("F3", declarations=[_decl(fer_id="https://www.doi.org/")])]
    )

    r = client.get("/api/dashboard/similarity/pair", params={"a": a.id, "b": b_both_na.id})
    per_q = {q["questionId"]: q for q in r.json()["data"]["perQuestion"]}
    assert per_q["F3"]["jaccard"] == pytest.approx(1.0)
    assert per_q["F3"]["included"] is True
    # F1-metadata: a declares, b_both_na has no answer at all (one-sided,
    # not "both blank") -> included, scored 0.0, not excluded.
    assert per_q["F1-metadata"]["included"] is True
    assert per_q["F1-metadata"]["jaccard"] == pytest.approx(0.0)

    # True "both blank" exclusion: neither side answers F2 at all.
    r = client.get("/api/dashboard/similarity/pair", params={"a": a.id, "b": b_both_na.id})
    per_q = {q["questionId"]: q for q in r.json()["data"]["perQuestion"]}
    assert per_q["F2"]["included"] is False
    assert per_q["F2"]["jaccard"] is None

    r = client.get("/api/dashboard/similarity/pair", params={"a": a.id, "b": b_one_sided.id})
    per_q = {q["questionId"]: q for q in r.json()["data"]["perQuestion"]}
    assert per_q["F3"]["jaccard"] == pytest.approx(0.0)
    assert per_q["F3"]["included"] is True


# ---------------------------------------------------------------------------
# 27. weighting=principle differs from weighting=question on an F-heavy
# disagreement fixture, and both are reproducible.
# ---------------------------------------------------------------------------


def test_weighting_principle_differs_from_question(app, db_session, client):
    a = _make_fip(
        db_session,
        "sim27-a",
        [
            _answer("F1-metadata", declarations=[_decl(fer_id="https://www.doi.org/")]),
            _answer("F1-data", declarations=[_decl(fer_id="https://www.doi.org/")]),
            _answer("F2", declarations=[_decl(fer_id="https://www.doi.org/")]),
            _answer("F3", declarations=[_decl(fer_id="https://www.doi.org/")]),
            _answer("F4-metadata", declarations=[_decl(fer_id="https://www.doi.org/")]),
            _answer("F4-data", declarations=[_decl(fer_id="https://www.doi.org/")]),
            _answer("R1.1-metadata", declarations=[_decl(fer_id="https://www.handle.net/")]),
        ],
    )
    b = _make_fip(
        db_session,
        "sim27-b",
        [
            _answer("F1-metadata", declarations=[_decl(fer_id="https://orcid.org/")]),
            _answer("F1-data", declarations=[_decl(fer_id="https://orcid.org/")]),
            _answer("F2", declarations=[_decl(fer_id="https://orcid.org/")]),
            _answer("F3", declarations=[_decl(fer_id="https://orcid.org/")]),
            _answer("F4-metadata", declarations=[_decl(fer_id="https://orcid.org/")]),
            _answer("F4-data", declarations=[_decl(fer_id="https://orcid.org/")]),
            _answer("R1.1-metadata", declarations=[_decl(fer_id="https://www.handle.net/")]),
        ],
    )
    r1 = client.get(
        "/api/dashboard/similarity/pair", params={"a": a.id, "b": b.id, "weighting": "principle"}
    )
    r2 = client.get(
        "/api/dashboard/similarity/pair", params={"a": a.id, "b": b.id, "weighting": "question"}
    )
    principle_score = r1.json()["data"]["overall"]
    question_score = r2.json()["data"]["overall"]
    assert principle_score != pytest.approx(question_score)

    # Reproducible across two calls.
    r1_again = client.get(
        "/api/dashboard/similarity/pair", params={"a": a.id, "b": b.id, "weighting": "principle"}
    )
    assert r1_again.json()["data"]["overall"] == pytest.approx(principle_score)


# ---------------------------------------------------------------------------
# 28. Popular-key guard.
# ---------------------------------------------------------------------------


def test_popular_key_guard_skips_and_finds_true_neighbour(app, db_session, monkeypatch, client):
    from fipm.config import get_settings

    monkeypatch.setattr(get_settings(), "dashboard_df_skip_share", 0.20)
    monkeypatch.setattr(get_settings(), "dashboard_df_min_keys", 3)

    _make_session(db_session, "sim28-sess")
    subject_id = "sim28-subject"
    true_neighbour_id = "sim28-true"
    # 18 filler FIPs (>80% of the eventual 20-ish population) all share the
    # "popular" DOI key with the subject on F2 -- rare enough elsewhere that
    # DF_MIN_KEYS's fallback never kicks in for the *other* candidates, but
    # common enough that the DOI key itself must be skipped.
    # The subject needs *more* than DF_MIN_KEYS(3) rare keys of its own, or
    # the DF_MIN_KEYS fallback ("fewer than 3 keys survive -> take the
    # rarest 3 regardless") would re-admit the popular key by construction
    # regardless of whether the popularity guard itself works.
    rare_answers = [
        _answer("F2", declarations=[_decl(fer_id="https://fer-sim28.example/popular")]),
        _answer("F3", declarations=[_decl(fer_id="https://www.handle.net/")]),
        _answer("F1-metadata", declarations=[_decl(fer_id="https://ror.org/")]),
        _answer("A2", declarations=[_decl(fer_id="https://orcid.org/")]),
    ]
    _make_fip(db_session, subject_id, rare_answers, session_id="sim28-sess")
    _make_fip(db_session, true_neighbour_id, rare_answers, session_id="sim28-sess")
    for i in range(18):
        _make_fip(
            db_session,
            f"sim28-filler-{i:02d}",
            [_answer("F2", declarations=[_decl(fer_id="https://fer-sim28.example/popular")])],
            session_id="sim28-sess",
        )

    r = client.get(
        "/api/dashboard/similarity/neighbours",
        params={"fip": subject_id, "pop": "session:sim28-sess", "limit": 5},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert "https://fer-sim28.example/popular" in data["skippedPopularKeys"]
    assert data["neighbours"][0]["fipId"] == true_neighbour_id
    assert data["neighbours"][0]["similarity"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 29. Posting cap: deterministic, lexicographically-first truncation.
# ---------------------------------------------------------------------------


def test_posting_cap_deterministic_truncation(app, db_session, monkeypatch, client):
    from fipm.config import get_settings

    monkeypatch.setattr(get_settings(), "dashboard_posting_cap", 3)
    monkeypatch.setattr(get_settings(), "dashboard_df_skip_share", 1.0)  # never skip for this test

    _make_session(db_session, "sim29-sess")
    subject_id = "sim29-subject"
    _make_fip(
        db_session,
        subject_id,
        [_answer("F2", declarations=[_decl(fer_id="https://fer-sim29.example/shared")])],
        session_id="sim29-sess",
    )
    other_ids = sorted(f"sim29-other-{i:02d}" for i in range(10))
    for oid in other_ids:
        _make_fip(
            db_session,
            oid,
            [_answer("F2", declarations=[_decl(fer_id="https://fer-sim29.example/shared")])],
            session_id="sim29-sess",
        )

    r = client.get(
        "/api/dashboard/similarity/neighbours",
        params={"fip": subject_id, "pop": "session:sim29-sess", "limit": 20},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["postingTruncated"] is True
    returned_ids = {n["fipId"] for n in data["neighbours"]}
    assert returned_ids == set(other_ids[:3]), returned_ids


# ---------------------------------------------------------------------------
# 30. Hot bucket: 60 identical FIPs collapse into one group, not 1770 pairs.
# ---------------------------------------------------------------------------


def test_hot_bucket_guard(app, db_session, monkeypatch, client):
    from fipm.config import get_settings

    monkeypatch.setattr(get_settings(), "dashboard_lsh_bucket_max", 10)
    monkeypatch.setattr(get_settings(), "dashboard_exact_pairs_max_fips", 5)

    _make_session(db_session, "sim30-sess")
    identical_answers = [
        _answer("F2", declarations=[_decl(fer_id="https://fer-sim30.example/identical")])
    ]
    ids = [f"sim30-hot-{i:03d}" for i in range(60)]
    for fid in ids:
        _make_fip(db_session, fid, identical_answers, session_id="sim30-sess")

    written = sv.refresh_hot_buckets(db_session)
    assert written > 0

    spec = _session_population("sim30-sess")
    data = sv.clusters_view(db_session, spec, None)["data"]
    hot_clusters = [c for c in data["clusters"] if c["id"].startswith("hot:")]
    assert len(hot_clusters) == 1
    assert hot_clusters[0]["size"] == 60


# ---------------------------------------------------------------------------
# 25. LSH vs exact: >=95% cluster-assignment agreement at 300 FIPs.
# ---------------------------------------------------------------------------


def _partition_by_fip(fip_ids, edges):
    components = sv.similarity.cluster_edges(fip_ids, edges)
    by_fip: dict[str, frozenset] = {}
    for members in components.values():
        frozen = frozenset(members)
        for m in members:
            by_fip[m] = frozen
    return by_fip


def test_lsh_vs_exact_cluster_agreement_at_300_fips(app, db_session, monkeypatch):
    from fipm.config import get_settings

    settings = get_settings()
    rng = __import__("random").Random(20260911)
    # One representative question per principle code (12 of gofair-fip-
    # mini's 21) -- more tokens per FIP than a 4-question seed gives the
    # MinHash signature more to agree on, so a single mutation only ever
    # nudges token-Jaccard from 1.0 to ~11/13, comfortably inside the
    # J >= 0.6 "recall ~99%" band of spec §4.2's own detection-probability
    # table rather than sitting on the 0.5-0.6 boundary the spec already
    # documents as approximate by construction.
    seed_questions = [
        "F1-metadata",
        "F2",
        "F3",
        "F4-metadata",
        "A1.1-metadata",
        "A1.2-metadata",
        "A2",
        "I1-metadata",
        "I2-metadata",
        "I3-metadata",
        "R1.1-metadata",
        "R1.2-metadata",
    ]
    seed_fers = [f"https://fer-sim25.example/f{i}" for i in range(30)]
    n_seeds = 15
    seeds = []
    for _ in range(n_seeds):
        chosen = rng.sample(seed_fers, k=len(seed_questions))
        seeds.append(
            [
                _answer(q, declarations=[_decl(fer_id=fer)])
                for q, fer in zip(seed_questions, chosen, strict=True)
            ]
        )

    n = 300
    ids = []
    for i in range(n):
        seed = seeds[i % n_seeds]
        answers = json.loads(json.dumps(seed))  # deep copy
        if rng.random() < 0.3:
            # a small mutation so clusters aren't 100% pairwise-identical
            answers[rng.randrange(len(answers))]["declarations"][0]["ferId"] = rng.choice(seed_fers)
        fip_id = f"sim25-{i:04d}"
        ids.append(fip_id)
        fip = Fip(
            id=fip_id,
            owner_id=None,
            session_id=None,
            edit_token_hash="x",
            visibility="public",
            questionnaire_id=KM_ID,
            questionnaire_version=KM_VERSION,
            title=fip_id,
            community={"name": fip_id},
            related_dmps=[],
            answers=answers,
            language="en",
            license="CC0-1.0",
        )
        db_session.add(fip)
    db_session.commit()

    fip_data = sv.fetch_fip_data(db_session, ids)
    exact_pairs = [(ids[i], ids[j]) for i in range(len(ids)) for j in range(i + 1, len(ids))]
    exact_edges = sv._score_edges(
        fip_data,
        exact_pairs,
        weighting="principle",
        statuses="current",
        min_sim=settings.dashboard_cluster_min_sim,
    )
    lsh_pairs = sv._lsh_candidate_pairs(db_session, ids, settings)
    lsh_edges = sv._score_edges(
        fip_data,
        lsh_pairs,
        weighting="principle",
        statuses="current",
        min_sim=settings.dashboard_cluster_min_sim,
    )
    # every LSH-surfaced edge's score is the exact score (same `score_pair`
    # call as the exact path, just fewer candidate pairs reaching it).
    exact_score_by_pair = {(e.a, e.b): e.score for e in exact_edges}
    exact_score_by_pair.update({(e.b, e.a): e.score for e in exact_edges})
    for e in lsh_edges:
        assert e.score == pytest.approx(exact_score_by_pair[(e.a, e.b)])

    exact_partition = _partition_by_fip(ids, [(e.a, e.b) for e in exact_edges])
    lsh_partition = _partition_by_fip(ids, [(e.a, e.b) for e in lsh_edges])
    agree = sum(1 for fid in ids if exact_partition[fid] == lsh_partition[fid])
    assert agree / len(ids) >= 0.95, agree / len(ids)


# ---------------------------------------------------------------------------
# 31. Signature determinism across reprojections and across processes.
# ---------------------------------------------------------------------------


def test_signature_determinism(app, db_session):
    fip = _make_fip(
        db_session,
        "sim31-fip",
        [_answer("F1-metadata", declarations=[_decl(fer_id="https://www.doi.org/")])],
    )
    sig1 = db_session.get(FipSignature, fip.id)
    bands1 = {
        (b.band_index, b.band_hash)
        for b in db_session.query(FipSignatureBand).filter_by(fip_id=fip.id).all()
    }
    assert sig1 is not None

    from fipm.projection import reproject_fip

    reproject_fip(db_session, fip.id)
    db_session.commit()
    sig2 = db_session.get(FipSignature, fip.id)
    bands2 = {
        (b.band_index, b.band_hash)
        for b in db_session.query(FipSignatureBand).filter_by(fip_id=fip.id).all()
    }
    assert sig2.signature == sig1.signature
    assert bands2 == bands1

    fip.answers = [_answer("F1-metadata", declarations=[_decl(fer_id="https://orcid.org/")])]
    db_session.commit()
    sig3 = db_session.get(FipSignature, fip.id)
    bands3 = {
        (b.band_index, b.band_hash)
        for b in db_session.query(FipSignatureBand).filter_by(fip_id=fip.id).all()
    }
    assert sig3.signature != sig1.signature
    assert bands3 != bands1


# ---------------------------------------------------------------------------
# 32. `…/pair` 404s (not 403) for a FIP the viewer cannot read individually.
# ---------------------------------------------------------------------------


def test_pair_404_not_403_for_unreadable_fip(app, db_session, client):
    owner = User(
        id=new_user_id(),
        email="sim32-owner@example.com",
        password_hash="x",
        display_name="Owner",
        role="user",
        language="en",
    )
    db_session.add(owner)
    db_session.commit()

    private_fip = _make_fip(
        db_session, "sim32-private", [], visibility="private", owner_id=owner.id
    )
    public_fip = _make_fip(db_session, "sim32-public", [])

    r = client.get(
        "/api/dashboard/similarity/pair", params={"a": private_fip.id, "b": public_fip.id}
    )
    assert r.status_code == 404, r.text
    assert "not_found" in r.text

    r = client.get(
        "/api/dashboard/similarity/pair", params={"a": "sim32-does-not-exist", "b": public_fip.id}
    )
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# spec §8.1 test 7's fifth case (brief B's addition to `check-declarations`):
# a signature computed with a different k; --fix repairs it. Brief A's own
# test_ac_13_01_projection.py::test_check_declarations_detects_and_fixes
# covers the other four (missing facets, wrong cell_state, extra
# declaration, stale projection_epoch).
# ---------------------------------------------------------------------------


def test_check_declarations_detects_signature_parameter_mismatch(app, db_session, monkeypatch):
    from fipm.cli import run_check_declarations
    from fipm.config import get_settings

    fip = _make_fip(
        db_session,
        "sim7e-fip",
        [_answer("F2", declarations=[_decl(fer_id="https://www.doi.org/")])],
    )
    assert run_check_declarations(only_ids=[fip.id]) == []

    signature = db_session.get(FipSignature, fip.id)
    signature.k = 64  # a stale parameter, as if FIPM_DASHBOARD_LSH_K changed
    db_session.commit()

    problems = run_check_declarations(only_ids=[fip.id])
    assert any(fip.id in p and "signatures" in p for p in problems), problems

    fixed = run_check_declarations(only_ids=[fip.id], fix=True)
    assert any(fip.id in p for p in fixed)
    assert run_check_declarations(only_ids=[fip.id]) == []

    settings = get_settings()
    db_session.expire_all()  # run_check_declarations wrote via its own session
    signature = db_session.get(FipSignature, fip.id)
    assert signature.k == settings.dashboard_lsh_k
    assert signature.bands == settings.dashboard_lsh_bands
    assert signature.rows_per_band == settings.dashboard_lsh_rows
