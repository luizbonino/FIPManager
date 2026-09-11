"""spec 13-fip-dashboard.md §8.1 tests 9-13: population resolution and
authorization -- visibility combinations, per-viewer population hashing,
k-anonymity, differencing, and "never name an unreadable FIP"."""

from __future__ import annotations

from datetime import UTC, datetime

from fipm.auth import hash_password
from fipm.dashboard import DashboardError
from fipm.dashboard.populations import (
    ResolvedPopulation,
    auth_scope_for,
    canonicalise_spec,
    check_k_anonymity,
    parse_population_spec,
    population_hash,
    resolve_population,
)
from fipm.dashboard.views import adoption_view, coverage_view, evolution_view, gaps_view
from fipm.ids import new_user_id
from fipm.models import Fip, User


def _make_user(db_session, email, *, role="user"):
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


def _make_fip(db_session, fip_id, *, owner_id=None, session_id=None, visibility="public"):
    fip = Fip(
        id=fip_id,
        owner_id=owner_id,
        session_id=session_id,
        edit_token_hash="x" if owner_id is None else None,
        visibility=visibility,
        questionnaire_id="test-km",
        questionnaire_version="1.0.0",
        title="T",
        community=None,
        related_dmps=[],
        answers=[],
        language="en",
        license="CC0-1.0",
    )
    db_session.add(fip)
    db_session.commit()
    return fip


# ---------------------------------------------------------------------------
# 9. Six viewer/visibility combinations.
# ---------------------------------------------------------------------------


def test_private_fip_only_in_owner_and_admin_populations(app, db_session):
    owner = _make_user(db_session, "ac13pop-owner@example.com")
    other = _make_user(db_session, "ac13pop-other@example.com")
    admin = _make_user(db_session, "ac13pop-admin@example.com", role="admin")
    _make_fip(db_session, "priv-fip-01", owner_id=owner.id, visibility="private")

    spec = parse_population_spec({"include": [{"kind": "mine"}]})
    assert "priv-fip-01" in resolve_population(db_session, spec, owner).fip_ids
    assert "priv-fip-01" not in resolve_population(db_session, spec, other).fip_ids

    admin_spec = parse_population_spec(
        {"include": [{"kind": "questionnaire", "id": "test-km", "version": "1.0.0"}]}
    )
    assert "priv-fip-01" in resolve_population(db_session, admin_spec, admin).fip_ids
    assert "priv-fip-01" not in resolve_population(db_session, admin_spec, other).fip_ids
    assert "priv-fip-01" not in resolve_population(db_session, admin_spec, None).fip_ids


def test_link_fip_excluded_from_public_and_network_but_visible_to_owner_and_session_owner(
    client, db_session
):
    # Session ownership is resolved from the auth cookie, so the facilitator
    # must be signed in through `client` (register via the HTTP API), not
    # just an ORM-level `User` row.
    r = client.post(
        "/api/auth/register",
        json={
            "email": "ac13pop-fac2@example.com",
            "password": "correcthorsebattery",
            "displayName": "Fac2",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert r.status_code == 201, r.text
    fac2_id = r.json()["id"]
    session2 = client.post(
        "/api/sessions",
        json={
            "title": "AC13 pop session 2",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()

    _make_fip(
        db_session, "link-fip-01", owner_id=None, session_id=session2["id"], visibility="link"
    )

    fac2 = db_session.get(User, fac2_id)

    pub_spec = parse_population_spec({"include": [{"kind": "public"}]})
    assert "link-fip-01" not in resolve_population(db_session, pub_spec, None).fip_ids
    assert "link-fip-01" not in resolve_population(db_session, pub_spec, fac2).fip_ids

    session_spec = parse_population_spec({"include": [{"kind": "session", "id": session2["id"]}]})
    assert "link-fip-01" in resolve_population(db_session, session_spec, fac2).fip_ids
    stranger = _make_user(db_session, "ac13pop-stranger@example.com")
    assert "link-fip-01" not in resolve_population(db_session, session_spec, stranger).fip_ids


def test_anonymous_session_fip_reaches_session_owner_only(client, db_session):
    r = client.post(
        "/api/auth/register",
        json={
            "email": "ac13pop-fac3@example.com",
            "password": "correcthorsebattery",
            "displayName": "Fac3",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert r.status_code == 201, r.text
    fac3_id = r.json()["id"]
    session3 = client.post(
        "/api/sessions",
        json={
            "title": "AC13 pop session 3",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()
    _make_fip(
        db_session,
        "anon-session-fip-01",
        owner_id=None,
        session_id=session3["id"],
        visibility="link",
    )

    fac3 = db_session.get(User, fac3_id)
    session_spec = parse_population_spec({"include": [{"kind": "session", "id": session3["id"]}]})
    assert "anon-session-fip-01" in resolve_population(db_session, session_spec, fac3).fip_ids

    stranger = _make_user(db_session, "ac13pop-stranger2@example.com")
    assert (
        "anon-session-fip-01" not in resolve_population(db_session, session_spec, stranger).fip_ids
    )
    assert "anon-session-fip-01" not in resolve_population(db_session, session_spec, None).fip_ids


def test_public_fip_enters_any_population(app, db_session):
    _make_fip(db_session, "pub-fip-ac13", visibility="public")
    spec = parse_population_spec({"include": [{"kind": "public"}]})
    assert "pub-fip-ac13" in resolve_population(db_session, spec, None).fip_ids
    stranger = _make_user(db_session, "ac13pop-anyone@example.com")
    assert "pub-fip-ac13" in resolve_population(db_session, spec, stranger).fip_ids


# ---------------------------------------------------------------------------
# 10. Two viewers, same spec, different population_hash; never share a
#     snapshot row (brief A has no snapshot table -- asserted here as
#     "the hash differs", which is what makes cross-viewer snapshot sharing
#     structurally impossible once brief B adds the snapshot table keyed by
#     this same hash).
# ---------------------------------------------------------------------------


def test_same_spec_different_viewers_different_hash(app, db_session):
    a = _make_user(db_session, "ac13pop-viewer-a@example.com")
    b = _make_user(db_session, "ac13pop-viewer-b@example.com")
    spec = parse_population_spec({"include": [{"kind": "mine"}]})
    canonical = canonicalise_spec(spec)
    scope_a = auth_scope_for(spec, a)
    scope_b = auth_scope_for(spec, b)
    assert scope_a != scope_b
    assert population_hash(canonical, scope_a) != population_hash(canonical, scope_b)


# ---------------------------------------------------------------------------
# 11. population_too_small.
# ---------------------------------------------------------------------------


def test_k_anonymity_binds_only_when_k_hidden_positive():
    now = datetime.now(UTC)

    def member(fip_id, readable):
        from fipm.dashboard.populations import PopulationMember

        return PopulationMember(
            fip_id=fip_id,
            updated_at=now,
            visibility="private",
            owner_id=None,
            session_id=None,
            readable_individually=readable,
            facets_fip_updated_at=now,
            facets_projection_epoch=0,
        )

    # 3 FIPs, all hidden from the viewer (k_hidden=3 > 0), below the
    # threshold (default 5) -- must 403.
    hidden_pop = ResolvedPopulation(members=[member(f"h{i}", False) for i in range(3)])
    try:
        check_k_anonymity(hidden_pop)
        raise AssertionError("expected population_too_small")
    except DashboardError as exc:
        assert exc.status_code == 403
        assert exc.body["detail"] == "population_too_small"
        assert "count" not in exc.body  # never echoed

    # 3 FIPs, all readable by the viewer (k_hidden=0) -- the facilitator's
    # own small session -- never binds.
    own_pop = ResolvedPopulation(members=[member(f"o{i}", True) for i in range(3)])
    check_k_anonymity(own_pop)  # must not raise

    # Empty population -- 200/zeros, not a 403 either.
    empty_pop = ResolvedPopulation(members=[])
    check_k_anonymity(empty_pop)  # must not raise


def test_facilitator_small_session_population_does_not_403(client):
    r = client.post(
        "/api/auth/register",
        json={
            "email": "ac13pop-smallfac@example.com",
            "password": "correcthorsebattery",
            "displayName": "SmallFac",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert r.status_code == 201, r.text
    session = client.post(
        "/api/sessions",
        json={
            "title": "small session",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()
    for _ in range(3):
        created = client.post(
            "/api/fips",
            json={
                "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
                "sessionId": session["id"],
                "joinCode": session["joinCode"],
                "answers": [],
            },
        )
        assert created.status_code == 201, created.text

    resp = client.get(f"/api/dashboard/coverage?pop=session:{session['id']}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["population"]["fipCount"] == 3


def test_empty_population_is_200_with_zeros(client):
    resp = client.get("/api/dashboard/coverage?pop=session:does-not-exist-anywhere")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["population"]["fipCount"] == 0
    assert body["data"]["totals"] == {"fips": 0, "cells": 0}


# ---------------------------------------------------------------------------
# 12. Differencing: public MINUS (public and area=X) counted after
#     exclusion, same threshold.
# ---------------------------------------------------------------------------


def test_differencing_counts_after_exclusion(app, db_session):
    # A dedicated session (unique id) rather than the shared `test-km`
    # questionnaire is what makes the "after exclusion" count exact in a
    # database shared with every other test module -- other tests' public
    # FIPs never carry *this* session_id.
    session_id = "ac13pop-diff-session"
    from fipm.models import WorkshopSession

    db_session.add(
        WorkshopSession(
            id=session_id,
            join_code="DIFF01",
            owner_id=None,
            questionnaire_id="test-km",
            questionnaire_version="1.0.0",
            default_language="en",
            title="diff session",
            status="open",
        )
    )
    db_session.commit()

    for i in range(4):
        _make_fip(db_session, f"diff-pub-{i}", visibility="public")
    for i in range(3):
        _make_fip(
            db_session, f"diff-pub-in-session-{i}", visibility="public", session_id=session_id
        )

    spec_all = parse_population_spec({"include": [{"kind": "public"}]})
    spec_diff = parse_population_spec(
        {
            "include": [{"kind": "public"}],
            "exclude": [{"kind": "session", "id": session_id}],
        }
    )
    pop_all = resolve_population(db_session, spec_all, None)
    pop_diff = resolve_population(db_session, spec_diff, None)
    assert pop_all.count >= 7
    assert pop_diff.count == pop_all.count - 3  # exactly the 3 in-session FIPs excluded


# ---------------------------------------------------------------------------
# 13. No aggregate response body names an unreadable FIP -- true by
#     construction for brief A's four views (coverage/adoption/gaps/
#     evolution never emit a per-FIP id), asserted directly here.
# ---------------------------------------------------------------------------


def test_no_view_response_names_a_fip_id(app, db_session):
    owner = _make_user(db_session, "ac13pop-secret-owner@example.com")
    secret_id = "super-secret-fip-id-ac13"
    _make_fip(db_session, secret_id, owner_id=owner.id, visibility="private")
    _make_fip(db_session, "public-companion-ac13", visibility="public")

    spec = parse_population_spec(
        {"include": [{"kind": "questionnaire", "id": "test-km", "version": "1.0.0"}]}
    )
    for view_fn in (coverage_view, adoption_view, gaps_view, evolution_view):
        envelope = view_fn(db_session, spec, owner)
        assert secret_id not in str(envelope)
