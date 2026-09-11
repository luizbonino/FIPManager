"""Regression tests for the confirmed spec-13 dashboard review findings
(builder brief: fix items 1-10). Each test is named after the finding it
covers; see the corresponding comment in the fixed source for the full
rationale."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fipm.dashboard import similarity_views as sv
from fipm.dashboard.populations import (
    _readable_individually_expr,
    check_k_anonymity,
    parse_population_spec,
    resolve_population,
)
from fipm.dashboard.snapshots import _trim_to_fit
from fipm.ids import new_user_id
from fipm.models import DashboardSnapshot, Fip, NetworkFip, User, WorkshopSession

KM_ID = "gofair-fip-mini"
KM_VERSION = "1.0.0"


def _make_user(db_session, email, *, role="user"):
    from fipm.auth import hash_password

    user = User(
        id=new_user_id(),
        email=email,
        password_hash=hash_password("correcthorsebattery"),
        display_name=email,
        role=role,
        language="en",
    )
    db_session.add(user)
    db_session.commit()
    return user


def _make_session(db_session, session_id: str, *, owner_id: str | None = None):
    import hashlib

    if db_session.get(WorkshopSession, session_id) is not None:
        return
    join_code = hashlib.sha256(session_id.encode()).hexdigest()[:6].upper()
    db_session.add(
        WorkshopSession(
            id=session_id,
            join_code=join_code,
            owner_id=owner_id,
            questionnaire_id=KM_ID,
            questionnaire_version=KM_VERSION,
            questionnaire_refs=None,
            default_language="en",
            title=session_id,
            status="open",
        )
    )
    db_session.commit()


def _make_fip(
    db_session, fip_id, *, owner_id=None, session_id=None, visibility="public", answers=None
):
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
        answers=answers or [],
        language="en",
        license="CC0-1.0",
    )
    db_session.add(fip)
    db_session.commit()
    return fip


def _answer(question_id, *, fer_id=None, free_text=None, status="current"):
    decl = {"status": status}
    if fer_id:
        decl["ferId"] = fer_id
    if free_text:
        decl["ferFreeText"] = free_text
    return {"questionId": question_id, "declarations": [decl]}


# ---------------------------------------------------------------------------
# 1. LEAK -- cluster id/representative must be drawn from readable members
#    only, and a cluster with no readable member is dropped, not named.
# ---------------------------------------------------------------------------


def test_build_clusters_never_names_an_unreadable_representative():
    fip_data = {
        "priv1": sv.FipData(label="private-fip"),
        "pub1": sv.FipData(label="public-fip"),
    }
    edges = [sv.PairEdge("priv1", "pub1", 0.9, {"F1": 0.9})]

    def readable(fip_id: str) -> bool:
        return fip_id == "pub1"

    clusters = sv._build_clusters(
        ["priv1", "pub1"], edges, fip_data, [], limit=50, readable=readable
    )
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster["id"] == "pub1"
    assert cluster["representative"]["fipId"] == "pub1"
    assert all(m["fipId"] != "priv1" for m in cluster["members"])


def test_build_clusters_drops_cluster_with_no_readable_member():
    fip_data = {"priv1": sv.FipData(label="a"), "priv2": sv.FipData(label="b")}
    edges = [sv.PairEdge("priv1", "priv2", 0.9, {"F1": 0.9})]

    clusters = sv._build_clusters(
        ["priv1", "priv2"], edges, fip_data, [], limit=50, readable=lambda _fid: False
    )
    assert clusters == []


def test_build_clusters_drops_hot_bucket_with_unreadable_representative():
    fip_data = {"priv-rep": sv.FipData(label="rep")}
    clusters = sv._build_clusters(
        ["priv-rep"], [], fip_data, [("priv-rep", 42)], limit=50, readable=lambda _fid: False
    )
    assert clusters == []


# ---------------------------------------------------------------------------
# 2. `_readable_individually_expr` must grant readability to a FIP in a
#    session the viewer owns -- Alice/Bob's exact CONFOA workshop scenario.
# ---------------------------------------------------------------------------


def test_owned_session_member_is_readable_individually_and_k_anonymity_holds(app, db_session):
    alice = _make_user(db_session, "rf13-alice@example.com")
    _make_session(db_session, "rf13-alice-sess", owner_id=alice.id)
    # Alice's own 3 FIPs plus Bob's one *private* FIP in her session --
    # exactly the "facilitator's small workshop session" case spec §2.4
    # says must keep working.
    for i in range(3):
        _make_fip(
            db_session, f"rf13-alice-fip-{i}", owner_id=alice.id, session_id="rf13-alice-sess"
        )
    _make_fip(
        db_session,
        "rf13-bob-private-fip",
        owner_id=None,
        session_id="rf13-alice-sess",
        visibility="private",
    )

    spec = parse_population_spec({"include": [{"kind": "session", "id": "rf13-alice-sess"}]})
    pop = resolve_population(db_session, spec, alice)
    assert pop.count == 4
    member = next(m for m in pop.members if m.fip_id == "rf13-bob-private-fip")
    assert member.readable_individually is True
    assert pop.k_hidden == 0

    # Before the fix this raised 403 population_too_small on Alice's own
    # 4-FIP session -- must not, regardless of FIPM_DASHBOARD_MIN_POPULATION.
    check_k_anonymity(pop)  # raises on failure


def test_readable_individually_still_false_for_a_stranger_and_a_private_fip_elsewhere(
    app, db_session
):
    """Round-3 fix (item E.1): the original version of this test only put
    ONE fip in the session -- an empty-for-the-stranger population -- so it
    passed even if `_readable_individually_expr`/the security predicate
    always granted access (there was simply nothing else to compare
    against). Rewritten so the population is genuinely non-empty for the
    stranger: Alice's session also holds a *public* FIP, which the
    stranger's `resolve_population` call must surface as a normal, readable
    member, while Bob's private FIP in the same session must still be the
    one row excluded -- exercising the per-row security predicate against a
    population that actually has other members, not just its emptiness."""
    alice = _make_user(db_session, "rf13-alice2@example.com")
    stranger = _make_user(db_session, "rf13-stranger@example.com")
    _make_session(db_session, "rf13-alice2-sess", owner_id=alice.id)
    _make_fip(
        db_session,
        "rf13-bob-private-fip-2",
        session_id="rf13-alice2-sess",
        visibility="private",
    )
    _make_fip(
        db_session,
        "rf13-public-fip-in-alice2-sess",
        session_id="rf13-alice2-sess",
        visibility="public",
    )
    spec = parse_population_spec({"include": [{"kind": "session", "id": "rf13-alice2-sess"}]})
    # A stranger doesn't own the session -- population resolution's own
    # security predicate excludes the private FIP entirely for them, while
    # the public sibling in the very same session remains a normal, named
    # member.
    pop = resolve_population(db_session, spec, stranger)
    assert "rf13-bob-private-fip-2" not in pop.fip_ids
    assert pop.count == 1
    public_member = next(
        m for m in pop.members if m.fip_id == "rf13-public-fip-in-alice2-sess"
    )
    assert public_member.readable_individually is True

    # The above still never observes `readable_individually` return `False`
    # -- `resolve_population`'s own security predicate excludes an
    # unreadable row from `pop.members` entirely, on this codebase's
    # current design, so no end-to-end call through `resolve_population`
    # can ever surface a `False` member (confirmed while fixing this
    # test: the SQL security predicate and `_readable_individually_expr`
    # currently accept exactly the same rows). Drive the predicate itself,
    # directly, on Bob's row shape, so the test still fails loud if
    # `_readable_individually_expr` were replaced with `lambda *_: True`:
    is_readable_stranger = _readable_individually_expr(stranger)
    assert is_readable_stranger("private", None, False) is False
    assert is_readable_stranger("public", None, False) is True
    assert _readable_individually_expr(alice)("private", None, True) is True  # owned session


# ---------------------------------------------------------------------------
# 3. The live envelope's `scope` must be the real `auth_scope_for(...)`,
#    not a locally re-derived "pub"/"u" -- round-trips a saved population's
#    hash and never collides two different viewers' ETags.
# ---------------------------------------------------------------------------


def test_coverage_hash_round_trips_through_saved_population(app, db_session, client):
    from fipm.auth import COOKIE_NAME, create_auth_session
    from fipm.config import get_settings

    owner = _make_user(db_session, "rf13-owner3@example.com")
    _make_session(db_session, "rf13-owner3-sess", owner_id=owner.id)
    _make_fip(db_session, "rf13-owner3-fip", owner_id=owner.id, session_id="rf13-owner3-sess")

    _, token = create_auth_session(db_session, owner, get_settings())
    client.cookies.set(COOKIE_NAME, token)

    save = client.post(
        "/api/dashboard/populations",
        json={"spec": {"include": [{"kind": "session", "id": "rf13-owner3-sess"}]}},
    )
    assert save.status_code == 201, save.text
    saved_hash = save.json()["hash"]

    r = client.get(f"/api/dashboard/coverage?population={saved_hash}")
    assert r.status_code == 200, r.text
    body = r.json()
    # Before the fix, `_envelope` recomputed its own "pub"/"u" scope, which
    # for a `u:<id>`-scoped save produces a *different* hash than
    # `POST /populations` stored -- the round-trip would then mismatch.
    assert body["population"]["hash"] == saved_hash
    assert body["population"]["authScope"] == f"u:{owner.id}"
    client.cookies.clear()


def test_coverage_etag_differs_between_two_signed_in_viewers_of_the_same_inline_spec(
    app, db_session, client
):
    from fipm.auth import COOKIE_NAME, create_auth_session
    from fipm.config import get_settings

    u1 = _make_user(db_session, "rf13-u1@example.com")
    u2 = _make_user(db_session, "rf13-u2@example.com")
    inline_spec = {"include": [{"kind": "mine"}]}
    import base64
    import json as jsonlib

    pop_param = base64.urlsafe_b64encode(jsonlib.dumps(inline_spec).encode()).decode().rstrip("=")

    _, token1 = create_auth_session(db_session, u1, get_settings())
    client.cookies.set(COOKIE_NAME, token1)
    r1 = client.get(f"/api/dashboard/coverage?pop={pop_param}")
    etag1 = r1.json()["etag"]
    hash1 = r1.json()["population"]["hash"]
    client.cookies.clear()

    _, token2 = create_auth_session(db_session, u2, get_settings())
    client.cookies.set(COOKIE_NAME, token2)
    r2 = client.get(f"/api/dashboard/coverage?pop={pop_param}")
    etag2 = r2.json()["etag"]
    hash2 = r2.json()["population"]["hash"]
    client.cookies.clear()

    # Before the fix both viewers hashed to the same literal "u" scope --
    # a `"mine"` spec for two different users must never collide.
    assert hash1 != hash2
    assert etag1 != etag2


# ---------------------------------------------------------------------------
# 4. similarity `_minimal_envelope`'s ETag must depend on the real scope
#    and on actual source freshness, not merely the calendar date.
# ---------------------------------------------------------------------------


def test_neighbours_etag_changes_when_underlying_declaration_changes(app, db_session):
    _make_session(db_session, "rf13-neigh-sess")
    _make_fip(
        db_session,
        "rf13-neigh-subject",
        session_id="rf13-neigh-sess",
        answers=[_answer("F2", fer_id="https://www.doi.org/")],
    )
    _make_fip(
        db_session,
        "rf13-neigh-other",
        session_id="rf13-neigh-sess",
        answers=[_answer("F2", fer_id="https://www.doi.org/")],
    )
    spec = parse_population_spec({"include": [{"kind": "session", "id": "rf13-neigh-sess"}]})

    envelope1 = sv.neighbours_view(db_session, spec, None, fip_id="rf13-neigh-subject")
    etag1 = envelope1["etag"]

    # Same day, same population spec, same literal scope as before the fix
    # ("x") -- only the underlying data changed. The old date-only ETag
    # would not move; the fixed one (keyed on `max_updated_at`) must.
    fip = db_session.get(Fip, "rf13-neigh-other")
    fip.answers = [_answer("F2", fer_id="https://orcid.org/")]
    db_session.commit()

    envelope2 = sv.neighbours_view(db_session, spec, None, fip_id="rf13-neigh-subject")
    etag2 = envelope2["etag"]
    assert etag1 != etag2


def test_minimal_envelope_scope_reflected_and_etag_differs_by_population_key():
    """Round-3 fix (item E.2): `_minimal_envelope` can never literally emit
    the substring `"-x-"` (`build_etag`'s format string has no such
    placeholder), so `"-x-" not in envelope["etag"]` was vacuous -- it would
    pass even if `scope` were silently ignored altogether. `scope` itself
    never feeds `build_etag` directly: every real caller already bakes a
    scope difference into `key` via `population_hash(canonicalise_spec(spec),
    scope)` *before* calling this function (exercised end-to-end by
    `test_coverage_etag_differs_between_two_signed_in_viewers_...` above,
    which is where a real scope-driven ETag divergence actually lives).
    What this function itself owns -- and what is actually worth pinning
    here -- is (1) `authScope` in the returned envelope is the real value
    passed in, not a re-derived placeholder, and (2) two calls whose `key`
    differs (what two different scopes resolve to, upstream) always
    produce genuinely different ETags."""
    envelope_a = sv._minimal_envelope("pair", "key-a", 2, {}, scope="u:someone")
    envelope_b = sv._minimal_envelope("pair", "key-b", 2, {}, scope="u:someone-else")
    assert envelope_a["population"]["authScope"] == "u:someone"
    assert envelope_b["population"]["authScope"] == "u:someone-else"
    assert envelope_a["etag"] != envelope_b["etag"]


# ---------------------------------------------------------------------------
# 5. POST /refresh must hash the same default params a GET uses, and must
#    use a cells-based (not FIP-count) sync/async cost decision.
# ---------------------------------------------------------------------------


def test_refresh_writes_the_snapshot_the_default_get_reads(app, db_session, client):
    from fipm.auth import COOKIE_NAME, create_auth_session
    from fipm.config import get_settings
    from fipm.dashboard.populations import auth_scope_for, canonicalise_spec, population_hash
    from fipm.dashboard.snapshots import params_hash
    from fipm.models import DashboardPopulation
    from fipm.routers.dashboard import _REFRESH_DEFAULT_PARAMS

    owner = _make_user(db_session, "rf13-refresh-owner@example.com")
    _make_session(db_session, "rf13-refresh-sess", owner_id=owner.id)
    _make_fip(
        db_session,
        "rf13-refresh-fip",
        owner_id=owner.id,
        session_id="rf13-refresh-sess",
        answers=[_answer("F2", fer_id="https://www.doi.org/")],
    )

    spec = parse_population_spec({"include": [{"kind": "session", "id": "rf13-refresh-sess"}]})
    scope = auth_scope_for(spec, owner)
    phash = population_hash(canonicalise_spec(spec), scope)
    db_session.add(
        DashboardPopulation(
            hash=phash, owner_id=owner.id, label="rf13", spec=spec, auth_scope=scope
        )
    )
    db_session.commit()

    _, token = create_auth_session(db_session, owner, get_settings())
    client.cookies.set(COOKIE_NAME, token)
    r = client.post(
        "/api/dashboard/refresh", json={"population": phash, "views": ["coverage"]}
    )
    assert r.status_code == 200, r.text

    # Before the fix this row was keyed on `params_hash({})`, which no GET
    # request (each building its own non-empty params dict) ever looks up.
    row = db_session.get(
        DashboardSnapshot,
        (phash, "coverage", params_hash(_REFRESH_DEFAULT_PARAMS["coverage"])),
    )
    assert row is not None
    assert row.status == "fresh"
    client.cookies.clear()


def test_refresh_sync_decision_uses_cells_not_raw_fip_count(app, db_session, client, monkeypatch):
    from fipm.auth import COOKIE_NAME, create_auth_session
    from fipm.config import get_settings
    from fipm.dashboard.populations import auth_scope_for, canonicalise_spec, population_hash
    from fipm.models import DashboardPopulation

    settings = get_settings()
    # Small enough that 3 FIPs (pop.count=3) would pass the *old*, buggy
    # `pop.count <= dashboard_sync_max_cells` check, but 3 * 21 estimated
    # cells (63) does not -- exactly the confirmed off-by-a-factor-of-21 bug.
    monkeypatch.setattr(settings, "dashboard_sync_max_cells", 50)

    owner = _make_user(db_session, "rf13-async-owner@example.com")
    _make_session(db_session, "rf13-async-sess", owner_id=owner.id)
    for i in range(3):
        _make_fip(
            db_session, f"rf13-async-fip-{i}", owner_id=owner.id, session_id="rf13-async-sess"
        )

    spec = parse_population_spec({"include": [{"kind": "session", "id": "rf13-async-sess"}]})
    scope = auth_scope_for(spec, owner)
    phash = population_hash(canonicalise_spec(spec), scope)
    db_session.add(
        DashboardPopulation(
            hash=phash, owner_id=owner.id, label="rf13async", spec=spec, auth_scope=scope
        )
    )
    db_session.commit()

    _, token = create_auth_session(db_session, owner, get_settings())
    client.cookies.set(COOKIE_NAME, token)
    r = client.post(
        "/api/dashboard/refresh", json={"population": phash, "views": ["coverage"]}
    )
    # Before the fix: pop.count (3) <= 50 -> "done" (sync) unconditionally,
    # the async/202 branch unreachable. After: estimated_cells (63) > 50.
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "computing"
    client.cookies.clear()


# ---------------------------------------------------------------------------
# 7. hot-bucket `size` must be scoped to the requesting population, and
#    `meanSimilarityEstimate` must never be a fabricated constant.
# ---------------------------------------------------------------------------


def test_hot_bucket_size_is_scoped_to_the_population_not_global(app, db_session, monkeypatch):
    from fipm.config import get_settings

    monkeypatch.setattr(get_settings(), "dashboard_lsh_bucket_max", 5)
    # `clusters_view` only ever consults `lsh_hot_buckets` on the LSH
    # (above-threshold) branch -- force the 3-FIP small population onto
    # that branch too, or hot-bucket handling never runs at all.
    monkeypatch.setattr(get_settings(), "dashboard_exact_pairs_max_fips", 2)

    identical_answers = [_answer("F2", fer_id="https://fer-rf13.example/identical")]
    _make_session(db_session, "rf13-hot-small-sess")
    _make_session(db_session, "rf13-hot-big-sess")
    # `refresh_hot_buckets` picks `MIN(fip_id)` globally as the
    # representative -- name the small session's ids so that one of them
    # wins that global min, or the representative would fall outside the
    # small population and `_scoped_hot_groups` would (correctly) surface
    # nothing at all, which is not what this test is checking.
    small_ids = [f"rf13-hot-aaa-small-{i}" for i in range(3)]
    big_ids = [f"rf13-hot-zzz-big-{i}" for i in range(20)]
    for fid in small_ids:
        _make_fip(db_session, fid, session_id="rf13-hot-small-sess", answers=identical_answers)
    for fid in big_ids:
        _make_fip(db_session, fid, session_id="rf13-hot-big-sess", answers=identical_answers)

    written = sv.refresh_hot_buckets(db_session)
    assert written > 0

    small_spec = parse_population_spec(
        {"include": [{"kind": "session", "id": "rf13-hot-small-sess"}]}
    )
    data = sv.clusters_view(db_session, small_spec, None)["data"]
    hot = [c for c in data["clusters"] if c["id"].startswith("hot:")]
    assert len(hot) == 1
    # 23 FIPs share one identical-signature bucket globally; scoped to the
    # 3-FIP session, the reported size must be 3, never the global 23.
    assert hot[0]["size"] == 3


def test_map_hot_buckets_never_report_a_fabricated_mean_similarity(app, db_session, monkeypatch):
    from fipm.config import get_settings

    monkeypatch.setattr(get_settings(), "dashboard_lsh_bucket_max", 5)
    identical_answers = [_answer("F2", fer_id="https://fer-rf13b.example/identical")]
    _make_session(db_session, "rf13-hot-map-sess")
    ids = [f"rf13-hot-map-{i}" for i in range(10)]
    for fid in ids:
        _make_fip(db_session, fid, session_id="rf13-hot-map-sess", answers=identical_answers)
    written = sv.refresh_hot_buckets(db_session)
    assert written > 0

    spec = parse_population_spec({"include": [{"kind": "session", "id": "rf13-hot-map-sess"}]})
    data = sv.map_view(db_session, spec, None)["data"]
    assert data["hotBuckets"], "expected at least one hot bucket in the response"
    for bucket in data["hotBuckets"]:
        assert "meanSimilarityEstimate" not in bucket
        assert bucket["size"] == 10


# ---------------------------------------------------------------------------
# 8. typeahead: empty `q` lists the population (updated_at DESC), and the
#    response carries total/truncated.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Round-3 fix (item C): a hot-bucket refresh must invalidate the
# clusters/map ETag even though it touches neither a member's `updated_at`
# nor `projection_epoch` -- both `_minimal_envelope` callers now fold
# `hot_bucket_rows`' own `computed_at` into the freshness stamp passed to
# `build_etag`, so a refresh always changes the ETag on the next request.
# ---------------------------------------------------------------------------


def test_clusters_etag_changes_after_hot_bucket_refresh(app, db_session, monkeypatch):
    from fipm.config import get_settings

    monkeypatch.setattr(get_settings(), "dashboard_lsh_bucket_max", 5)
    monkeypatch.setattr(get_settings(), "dashboard_exact_pairs_max_fips", 2)

    identical_answers = [_answer("F2", fer_id="https://fer-rf13c.example/identical")]
    _make_session(db_session, "rf13-etag-hot-sess")
    ids = [f"rf13-etag-hot-{i}" for i in range(10)]
    for fid in ids:
        _make_fip(db_session, fid, session_id="rf13-etag-hot-sess", answers=identical_answers)

    spec = parse_population_spec({"include": [{"kind": "session", "id": "rf13-etag-hot-sess"}]})

    # Before any refresh, `lsh_hot_buckets` is empty -- clusters_view's own
    # exact-pairs path still returns a normal cluster, with an ETag that
    # reflects no hot-bucket state at all.
    etag_before = sv.clusters_view(db_session, spec, None)["etag"]

    written = sv.refresh_hot_buckets(db_session)
    assert written > 0

    # Nothing about the FIPs themselves changed (no `updated_at` bump, no
    # new projection epoch) -- only `lsh_hot_buckets` was rewritten. The
    # old bug served this request a stale, pre-refresh 304 body; the ETag
    # must differ now.
    etag_after = sv.clusters_view(db_session, spec, None)["etag"]
    assert etag_before != etag_after


def test_map_etag_changes_after_hot_bucket_refresh(app, db_session, monkeypatch):
    from fipm.config import get_settings

    monkeypatch.setattr(get_settings(), "dashboard_lsh_bucket_max", 5)

    identical_answers = [_answer("F2", fer_id="https://fer-rf13d.example/identical")]
    _make_session(db_session, "rf13-etag-hot-map-sess")
    ids = [f"rf13-etag-hot-map-{i}" for i in range(10)]
    for fid in ids:
        _make_fip(db_session, fid, session_id="rf13-etag-hot-map-sess", answers=identical_answers)

    spec = parse_population_spec(
        {"include": [{"kind": "session", "id": "rf13-etag-hot-map-sess"}]}
    )

    etag_before = sv.map_view(db_session, spec, None)["etag"]
    written = sv.refresh_hot_buckets(db_session)
    assert written > 0
    etag_after = sv.map_view(db_session, spec, None)["etag"]
    assert etag_before != etag_after


def test_typeahead_empty_query_lists_population_in_updated_at_desc(app, db_session):
    _make_session(db_session, "rf13-typeahead-sess")
    older = _make_fip(db_session, "rf13-typeahead-older", session_id="rf13-typeahead-sess")
    newer = _make_fip(db_session, "rf13-typeahead-newer", session_id="rf13-typeahead-sess")
    older.updated_at = datetime.now(UTC) - timedelta(hours=1)
    newer.updated_at = datetime.now(UTC)
    db_session.commit()

    spec = parse_population_spec({"include": [{"kind": "session", "id": "rf13-typeahead-sess"}]})
    result = sv.typeahead_view(db_session, spec, None, q="")
    assert isinstance(result, dict)
    assert result["total"] == 2
    assert result["truncated"] is False
    ids_in_order = [item["fipId"] for item in result["items"]]
    assert ids_in_order == ["rf13-typeahead-newer", "rf13-typeahead-older"]


# ---------------------------------------------------------------------------
# Round-3 fix (item A): network FIPs must be genuinely findable -- not just
# ordered last -- once local+network candidates are merged in one SQL
# `UNION ALL` rather than concatenated as two Python lists, and the merged
# statement must carry its own `LIMIT` so an empty `q` never materialises
# the whole population.
# ---------------------------------------------------------------------------


def test_typeahead_finds_network_fip_behind_220_local_fips(app, db_session):
    _make_session(db_session, "rf13-typeahead-net-sess")
    for i in range(220):
        _make_fip(
            db_session, f"rf13-typeahead-net-local-{i:03d}", session_id="rf13-typeahead-net-sess"
        )

    net = NetworkFip(
        fip_id="net:rf13-typeahead-target",
        community_iri="http://example.org/rf13-typeahead-community",
        label="Unmistakable Network FIP Title",
        fetched_at=datetime.now(UTC),
    )
    db_session.add(net)
    db_session.commit()

    spec = parse_population_spec(
        {"include": [{"kind": "session", "id": "rf13-typeahead-net-sess"}, {"kind": "network"}]}
    )
    # An old attempt capped `offset` at 200 and concatenated local rows
    # before network rows, so with 220+ readable local FIPs the network
    # FIP always sat past reach regardless of `q`. An exact-title match
    # must find it even though offset is capped well below 220.
    result = sv.typeahead_view(db_session, spec, None, q="Unmistakable Network")
    ids = [item["fipId"] for item in result["items"]]
    assert net.fip_id in ids


def test_typeahead_empty_query_does_not_scale_with_population_size(app, db_session):
    from sqlalchemy import event

    _make_session(db_session, "rf13-typeahead-scale-sess")
    for i in range(220):
        _make_fip(
            db_session,
            f"rf13-typeahead-scale-local-{i:03d}",
            session_id="rf13-typeahead-scale-sess",
        )

    spec = parse_population_spec(
        {"include": [{"kind": "session", "id": "rf13-typeahead-scale-sess"}]}
    )

    engine = db_session.get_bind()
    seen: list[str] = []

    def _cb(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(engine, "after_cursor_execute", _cb)
    try:
        result = sv.typeahead_view(db_session, spec, None, q="")
    finally:
        event.remove(engine, "after_cursor_execute", _cb)

    # `resolve_population`'s own membership statement, plus exactly two
    # more here -- the `COUNT(*)` and the bounded page query -- regardless
    # of source count (local+network is still one `UNION ALL`, not one
    # statement per source). No per-row Python materialisation of the
    # 220-row candidate set into an unbounded list.
    assert len(seen) == 3
    assert result["total"] == 220
    assert len(result["items"]) == 20
    assert result["truncated"] is True
    # The page statement itself must carry a SQL LIMIT -- not just a slice
    # applied to an already-fetched Python list.
    assert any("LIMIT" in s.upper() for s in seen)


def test_typeahead_escapes_ilike_wildcards(app, db_session):
    _make_session(db_session, "rf13-typeahead-esc-sess")
    fip = _make_fip(db_session, "rf13-typeahead-esc-fip", session_id="rf13-typeahead-esc-sess")
    fip.title = "a_b"
    other = _make_fip(db_session, "rf13-typeahead-esc-other", session_id="rf13-typeahead-esc-sess")
    other.title = "aXb"
    db_session.commit()

    spec = parse_population_spec(
        {"include": [{"kind": "session", "id": "rf13-typeahead-esc-sess"}]}
    )
    result = sv.typeahead_view(db_session, spec, None, q="a_b")
    labels = {item["label"] for item in result["items"]}
    # An unescaped "_" is a single-char SQL wildcard and would also match
    # "aXb" -- it must not, once escaped.
    assert labels == {"a_b"}


# ---------------------------------------------------------------------------
# 9. POST /api/dashboard/populations must rate-limit anonymous callers.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Round-3 fix (item D): a malformed saved-population row must fail the
# same clean way `pop=` does (400 `invalid_population`), not with an
# unhandled `KeyError` (500) the first time some downstream reader
# indexes into the unparsed `row.spec`.
# ---------------------------------------------------------------------------


def test_resolve_spec_rejects_malformed_saved_population_cleanly(app, db_session, client):
    from fipm.models import DashboardPopulation

    # A row missing the `include` key entirely -- structurally invalid,
    # simulating a pre-schema-change or otherwise corrupted saved spec.
    # `row.spec` used to be returned as-is by `_resolve_spec`'s
    # `population=` branch, so the first downstream `spec["include"]`
    # lookup raised `KeyError` -> unhandled 500.
    db_session.add(
        DashboardPopulation(
            hash="rf13-malformed-pop-hash",
            owner_id=None,
            label="rf13-malformed",
            spec={"totally": "not-a-population-spec"},
            auth_scope="pub",
        )
    )
    db_session.commit()

    r = client.get("/api/dashboard/coverage", params={"population": "rf13-malformed-pop-hash"})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "invalid_population"


def test_anonymous_population_save_is_rate_limited(app, client):

    for _ in range(30):
        r = client.post(
            "/api/dashboard/populations", json={"spec": {"include": [{"kind": "public"}]}}
        )
        assert r.status_code == 201, r.text
    r = client.post(
        "/api/dashboard/populations", json={"spec": {"include": [{"kind": "public"}]}}
    )
    assert r.status_code == 429, r.text
    assert "Retry-After" in r.headers


def test_signed_in_population_save_is_not_rate_limited_by_the_anon_bucket(
    app, db_session, client
):
    from fipm.auth import COOKIE_NAME, create_auth_session
    from fipm.config import get_settings

    user = _make_user(db_session, "rf13-signedin-saver@example.com")
    _, token = create_auth_session(db_session, user, get_settings())
    client.cookies.set(COOKIE_NAME, token)
    for _ in range(31):
        r = client.post(
            "/api/dashboard/populations", json={"spec": {"include": [{"kind": "public"}]}}
        )
        assert r.status_code == 201, r.text
    client.cookies.clear()


# ---------------------------------------------------------------------------
# 10. adoption's ETag must not collide on a truncated raw params string, and
#     `_trim_to_fit` must not claim `truncated=True` when nothing was cut.
# ---------------------------------------------------------------------------


def test_trim_to_fit_reports_untruncated_when_payload_already_fits():
    data = {"rows": [1, 2, 3]}
    trimmed, truncated = _trim_to_fit(data, max_bytes=10_000)
    assert trimmed == data
    assert truncated is False


def test_trim_to_fit_reports_truncated_only_when_it_actually_cut_something():
    data = {"rows": list(range(1000))}
    payload_bytes = len(__import__("json").dumps(data).encode())
    trimmed, truncated = _trim_to_fit(data, max_bytes=payload_bytes // 2)
    assert truncated is True
    assert len(trimmed["rows"]) < len(data["rows"])


def test_adoption_etag_distinguishes_params_sharing_a_long_common_prefix(app, db_session):
    _make_session(db_session, "rf13-etag-adoption-sess")
    _make_fip(
        db_session,
        "rf13-etag-adoption-fip",
        session_id="rf13-etag-adoption-sess",
        answers=[_answer("F2", fer_id="https://www.doi.org/")],
    )
    spec = parse_population_spec(
        {"include": [{"kind": "session", "id": "rf13-etag-adoption-sess"}]}
    )
    from fipm.dashboard.views import adoption_view

    envelope1 = adoption_view(db_session, spec, None, limit=50, offset=0)
    envelope2 = adoption_view(db_session, spec, None, limit=51, offset=0)
    # Both params keys are "fercurrentany50"+"0"/"fercurrentany51"+"0" --
    # identical in their first 8 characters ("fercurre"), which is exactly
    # what the old `params_key[:8]` truncation would collide on.
    assert envelope1["etag"] != envelope2["etag"]


# ---------------------------------------------------------------------------
# Round-3 fix (item F): coverage gaps -- `pair`/`clusters`/`map` ETags had
# no regression test at all (only `neighbours` did, above); a stale ETag
# here means a client's `If-None-Match` gets served a 304 with pre-change
# data, exactly finding #4's original bug, just for the other three views.
# ---------------------------------------------------------------------------


def test_pair_etag_changes_when_underlying_declaration_changes(app, db_session):
    _make_session(db_session, "rf13-pair-etag-sess")
    _make_fip(
        db_session,
        "rf13-pair-etag-a",
        session_id="rf13-pair-etag-sess",
        answers=[_answer("F2", fer_id="https://www.doi.org/")],
    )
    _make_fip(
        db_session,
        "rf13-pair-etag-b",
        session_id="rf13-pair-etag-sess",
        answers=[_answer("F2", fer_id="https://www.doi.org/")],
    )
    envelope1 = sv.pair_view(db_session, None, a="rf13-pair-etag-a", b="rf13-pair-etag-b")
    etag1 = envelope1["etag"]

    fip_b = db_session.get(Fip, "rf13-pair-etag-b")
    fip_b.answers = [_answer("F2", fer_id="https://orcid.org/")]
    db_session.commit()
    # No `db_session.expire_all()` here: `a` (untouched) stays the tz-aware
    # in-memory instance from the identity map while `b` (just committed)
    # reloads as a tz-naive value on SQLite's `DateTime(timezone=True)` --
    # this is the real path a live request takes, and it must not raise
    # `TypeError` (see `_entity_updated_at`'s `_aware()` normalisation, and
    # `test_pair_view_naive_aware_mismatch_does_not_crash` below).

    envelope2 = sv.pair_view(db_session, None, a="rf13-pair-etag-a", b="rf13-pair-etag-b")
    etag2 = envelope2["etag"]
    assert etag1 != etag2


def test_pair_view_naive_aware_mismatch_does_not_crash(app, db_session):
    """A same-session commit to one of the two FIPs leaves that FIP's
    `updated_at` reloaded as tz-naive (SQLite's `DateTime(timezone=True)`
    convention) while the untouched FIP's is still the tz-aware in-memory
    value from `db.get()`'s identity map. `pair_view`'s freshness stamp
    (`_entity_updated_at`, used for its ETag) must normalise both to a
    single convention before comparing them, rather than raising
    `TypeError: can't compare offset-naive and offset-aware datetimes` --
    deliberately does NOT call `db_session.expire_all()`, which would mask
    the bug by making both sides reload naive."""
    _make_session(db_session, "rf13-pair-naive-aware-sess")
    _make_fip(
        db_session,
        "rf13-pair-naive-aware-a",
        session_id="rf13-pair-naive-aware-sess",
        answers=[_answer("F2", fer_id="https://www.doi.org/")],
    )
    _make_fip(
        db_session,
        "rf13-pair-naive-aware-b",
        session_id="rf13-pair-naive-aware-sess",
        answers=[_answer("F2", fer_id="https://www.doi.org/")],
    )
    sv.pair_view(db_session, None, a="rf13-pair-naive-aware-a", b="rf13-pair-naive-aware-b")

    fip_b = db_session.get(Fip, "rf13-pair-naive-aware-b")
    fip_b.answers = [_answer("F2", fer_id="https://orcid.org/")]
    db_session.commit()

    # Must not raise TypeError.
    sv.pair_view(db_session, None, a="rf13-pair-naive-aware-a", b="rf13-pair-naive-aware-b")


def test_clusters_etag_changes_when_underlying_declaration_changes(app, db_session):
    _make_session(db_session, "rf13-clusters-etag-sess")
    _make_fip(
        db_session,
        "rf13-clusters-etag-a",
        session_id="rf13-clusters-etag-sess",
        answers=[_answer("F2", fer_id="https://www.doi.org/")],
    )
    _make_fip(
        db_session,
        "rf13-clusters-etag-b",
        session_id="rf13-clusters-etag-sess",
        answers=[_answer("F2", fer_id="https://www.doi.org/")],
    )
    spec = parse_population_spec(
        {"include": [{"kind": "session", "id": "rf13-clusters-etag-sess"}]}
    )
    etag1 = sv.clusters_view(db_session, spec, None)["etag"]

    fip_b = db_session.get(Fip, "rf13-clusters-etag-b")
    fip_b.answers = [_answer("F2", fer_id="https://orcid.org/")]
    db_session.commit()

    etag2 = sv.clusters_view(db_session, spec, None)["etag"]
    assert etag1 != etag2


def test_map_etag_changes_when_underlying_declaration_changes(app, db_session):
    _make_session(db_session, "rf13-map-etag-sess")
    _make_fip(
        db_session,
        "rf13-map-etag-a",
        session_id="rf13-map-etag-sess",
        answers=[_answer("F2", fer_id="https://www.doi.org/")],
    )
    _make_fip(
        db_session,
        "rf13-map-etag-b",
        session_id="rf13-map-etag-sess",
        answers=[_answer("F2", fer_id="https://www.doi.org/")],
    )
    spec = parse_population_spec({"include": [{"kind": "session", "id": "rf13-map-etag-sess"}]})
    etag1 = sv.map_view(db_session, spec, None)["etag"]

    fip_b = db_session.get(Fip, "rf13-map-etag-b")
    fip_b.answers = [_answer("F2", fer_id="https://orcid.org/")]
    db_session.commit()

    etag2 = sv.map_view(db_session, spec, None)["etag"]
    assert etag1 != etag2


def test_map_top_clusters_reflects_the_same_connected_components_as_clusters_view(
    app, db_session
):
    """`map_view`'s `topClusters` had no coverage of its own -- only the
    `_build_clusters` unit and `clusters_view`'s own field were exercised.
    Same declarations, same population -> `map`'s `topClusters` and
    `clusters`'s `clusters` must name the same members (both are built
    from the identical thresholded connected-components computation)."""
    _make_session(db_session, "rf13-map-topclusters-sess")
    shared = [_answer("F2", fer_id="https://www.doi.org/")]
    ids = [f"rf13-map-topclusters-{i}" for i in range(3)]
    for fid in ids:
        _make_fip(db_session, fid, session_id="rf13-map-topclusters-sess", answers=shared)

    spec = parse_population_spec(
        {"include": [{"kind": "session", "id": "rf13-map-topclusters-sess"}]}
    )
    clusters_data = sv.clusters_view(db_session, spec, None)["data"]
    map_data = sv.map_view(db_session, spec, None)["data"]

    cluster_member_sets = {
        frozenset(m["fipId"] for m in c["members"]) for c in clusters_data["clusters"]
    }
    top_cluster_member_sets = {
        frozenset(m["fipId"] for m in c["members"]) for c in map_data["topClusters"]
    }
    assert cluster_member_sets == top_cluster_member_sets
    assert frozenset(ids) in top_cluster_member_sets


# ---------------------------------------------------------------------------
# Round-3 fix (item F, continued): the "etag changes on edit" tests above
# exercise `sv.pair_view`/`clusters_view`/`map_view` directly, bypassing the
# router's own `_respond`/If-None-Match handling entirely -- the actual
# client-facing caching contract (same request twice -> same ETag; a
# stale-matching `If-None-Match` -> 304) had no coverage at all for these
# three endpoints, only for `coverage` (test_ac_13_03_views.py).
# ---------------------------------------------------------------------------


def test_pair_endpoint_etag_round_trips_and_304s(app, db_session, client):
    _make_fip(
        db_session,
        "rf13-pair-http-a",
        visibility="public",
        answers=[_answer("F2", fer_id="https://www.doi.org/")],
    )
    _make_fip(
        db_session,
        "rf13-pair-http-b",
        visibility="public",
        answers=[_answer("F2", fer_id="https://www.doi.org/")],
    )
    url = "/api/dashboard/similarity/pair?a=rf13-pair-http-a&b=rf13-pair-http-b"
    r1 = client.get(url)
    assert r1.status_code == 200, r1.text
    etag1 = r1.headers["etag"]

    r2 = client.get(url)
    assert r2.status_code == 200
    assert r2.headers["etag"] == etag1

    r3 = client.get(url, headers={"If-None-Match": etag1})
    assert r3.status_code == 304


def test_clusters_endpoint_etag_round_trips_and_304s(app, db_session, client):
    # `pop=public` would span every public FIP the whole (session-scoped)
    # test database has accumulated by this point in the run -- easily
    # past `dashboard_exact_pairs_max_fips`, tipping this into the async
    # snapshot tier (202 `computing`) rather than the live 200 this test
    # means to exercise. A session-scoped population keeps this test's
    # population exactly the 2 FIPs it creates, regardless of run order.
    _make_session(db_session, "rf13-clusters-http-sess")
    shared = [_answer("F2", fer_id="https://www.doi.org/")]
    _make_fip(
        db_session, "rf13-clusters-http-a", session_id="rf13-clusters-http-sess", answers=shared
    )
    _make_fip(
        db_session, "rf13-clusters-http-b", session_id="rf13-clusters-http-sess", answers=shared
    )

    url = "/api/dashboard/similarity/clusters?pop=session:rf13-clusters-http-sess"
    r1 = client.get(url)
    assert r1.status_code == 200, r1.text
    etag1 = r1.headers["etag"]

    r2 = client.get(url)
    assert r2.status_code == 200
    assert r2.headers["etag"] == etag1

    r3 = client.get(url, headers={"If-None-Match": etag1})
    assert r3.status_code == 304


def test_map_endpoint_etag_round_trips_and_304s(app, db_session, client):
    # Same reasoning as the clusters test above: a session-scoped
    # population, not `pop=public`, so this test's population size stays
    # exactly 2 regardless of how many public FIPs earlier tests created.
    _make_session(db_session, "rf13-map-http-sess")
    shared = [_answer("F2", fer_id="https://www.doi.org/")]
    _make_fip(db_session, "rf13-map-http-a", session_id="rf13-map-http-sess", answers=shared)
    _make_fip(db_session, "rf13-map-http-b", session_id="rf13-map-http-sess", answers=shared)

    url = "/api/dashboard/similarity/map?pop=session:rf13-map-http-sess"
    r1 = client.get(url)
    assert r1.status_code == 200, r1.text
    etag1 = r1.headers["etag"]

    r2 = client.get(url)
    assert r2.status_code == 200
    assert r2.headers["etag"] == etag1

    r3 = client.get(url, headers={"If-None-Match": etag1})
    assert r3.status_code == 304
