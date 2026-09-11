"""Independent verification (not from the builder/reviewer round) that the
cluster-leak fix holds at the actual HTTP surface, not just at the
`_build_clusters` unit level covered by
tests/test_review_fixes_13_dashboard.py::test_build_clusters_never_names_an_unreadable_representative.

Scenario from the review: a facilitator (Alice) owns a session containing
her own public FIPs plus one participant FIP that is `visibility="private"`.

Important correction made while verifying: per
tests/test_review_fixes_13_dashboard.py::test_owned_session_member_is_readable_individually_and_k_anonymity_holds
(spec 2.4), the *session owner herself* is deliberately allowed to see that
private FIP individually -- her seeing its id/title in her own dashboard is
correct behaviour, not a leak. The genuine leak scenario is a *different*
viewer (a stranger with no relationship to the session) requesting the same
session's population: `resolve_population`'s security predicate must
exclude the private FIP from the population entirely for them, so it can
never be named -- in `id`, `representative`, or `members` -- from:
  * GET /api/dashboard/similarity/clusters (JSON)
  * GET /api/dashboard/similarity/clusters.csv
  * GET /api/dashboard/similarity/map (topClusters)

An anonymous (no cookie) viewer is checked too.
"""

from __future__ import annotations

import csv
import hashlib
import io

from fipm.auth import COOKIE_NAME, create_auth_session
from fipm.config import get_settings
from fipm.ids import new_user_id
from fipm.models import Fip, User, WorkshopSession

KM_ID = "gofair-fip-mini"
KM_VERSION = "1.0.0"

# Answers shared by Alice's own FIPs and the private participant FIP, so
# they land in the same near-identical similarity cluster (well above the
# default dashboard_cluster_min_sim=0.6).
_SHARED_ANSWERS = [
    {
        "questionId": "F1",
        "declarations": [{"status": "current", "ferId": "https://w3id.org/example/fer/doi"}],
    },
    {
        "questionId": "F2",
        "declarations": [{"status": "current", "ferId": "https://w3id.org/example/fer/schemaorg"}],
    },
]

PRIVATE_ID = "leak-check-bob-private-fip"
PRIVATE_LABEL = "Bob's Secret Draft FIP"


def _make_user(db_session, email):
    from fipm.auth import hash_password

    user = User(
        id=new_user_id(),
        email=email,
        password_hash=hash_password("correcthorsebattery"),
        display_name=email,
        role="user",
        language="en",
    )
    db_session.add(user)
    db_session.commit()
    return user


def _make_session(db_session, session_id, *, owner_id=None):
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
    db_session, fip_id, *, owner_id=None, session_id=None, visibility="public", title=None
):
    fip = Fip(
        id=fip_id,
        owner_id=owner_id,
        session_id=session_id,
        edit_token_hash="x" if owner_id is None else None,
        visibility=visibility,
        questionnaire_id=KM_ID,
        questionnaire_version=KM_VERSION,
        title=title or fip_id,
        community={"name": title or fip_id},
        related_dmps=[],
        answers=_SHARED_ANSWERS,
        language="en",
        license="CC0-1.0",
    )
    db_session.add(fip)
    db_session.commit()
    return fip


def _setup(db_session, suffix):
    alice = _make_user(db_session, f"leak-check-alice-{suffix}@example.com")
    stranger = _make_user(db_session, f"leak-check-stranger-{suffix}@example.com")
    session_id = f"leak-check-sess-{suffix}"
    _make_session(db_session, session_id, owner_id=alice.id)
    for i in range(3):
        _make_fip(
            db_session,
            f"leak-check-alice-fip-{suffix}-{i}",
            owner_id=alice.id,
            session_id=session_id,
            title=f"Alice public FIP {i}",
        )
    private_id = f"{PRIVATE_ID}-{suffix}"
    _make_fip(
        db_session,
        private_id,
        session_id=session_id,
        visibility="private",
        title=PRIVATE_LABEL,
    )
    return alice, stranger, session_id, private_id


def _login(client, db_session, user):
    _, token = create_auth_session(db_session, user, get_settings())
    client.cookies.set(COOKIE_NAME, token)


def _assert_no_leak_in_clusters(clusters, private_id):
    assert clusters, "expected at least one cluster to assert against"
    for c in clusters:
        assert c["id"] != private_id
        assert c["representative"]["fipId"] != private_id
        assert PRIVATE_LABEL not in c["representative"]["label"]
        for m in c["members"]:
            assert m["fipId"] != private_id
            assert PRIVATE_LABEL not in m["label"]


def test_clusters_endpoint_never_emits_the_private_fip_to_a_stranger(app, db_session, client):
    alice, stranger, session_id, private_id = _setup(db_session, "clusters")
    _login(client, db_session, stranger)

    r = client.get(f"/api/dashboard/similarity/clusters?pop=session:{session_id}")
    assert r.status_code == 200, r.text
    clusters = r.json()["data"]["clusters"]
    _assert_no_leak_in_clusters(clusters, private_id)
    client.cookies.clear()


def test_clusters_endpoint_never_emits_the_private_fip_to_an_anonymous_viewer(
    app, db_session, client
):
    _alice, _stranger, session_id, private_id = _setup(db_session, "anon")

    r = client.get(f"/api/dashboard/similarity/clusters?pop=session:{session_id}")
    assert r.status_code == 200, r.text
    clusters = r.json()["data"]["clusters"]
    _assert_no_leak_in_clusters(clusters, private_id)


def test_clusters_csv_never_emits_the_private_fip_to_a_stranger(app, db_session, client):
    alice, stranger, session_id, private_id = _setup(db_session, "csv")
    _login(client, db_session, stranger)

    r = client.get(f"/api/dashboard/similarity/clusters.csv?pop=session:{session_id}")
    assert r.status_code == 200, r.text
    assert private_id not in r.text
    assert PRIVATE_LABEL not in r.text
    rows = list(csv.reader(io.StringIO(r.text)))
    assert len(rows) > 1, "expected header + at least one data row"
    client.cookies.clear()


def test_map_top_clusters_never_emits_the_private_fip_to_a_stranger(app, db_session, client):
    alice, stranger, session_id, private_id = _setup(db_session, "map")
    _login(client, db_session, stranger)

    r = client.get(f"/api/dashboard/similarity/map?pop=session:{session_id}")
    assert r.status_code == 200, r.text
    top_clusters = r.json()["data"]["topClusters"]
    _assert_no_leak_in_clusters(top_clusters, private_id)
    client.cookies.clear()


def test_the_facilitator_herself_legitimately_sees_the_private_fip(app, db_session, client):
    """Control case, spec 2.4: this is the one deliberate exception -- the
    session owner IS authorized to see a private participant FIP in her own
    session individually, so it correctly appears as a cluster member (and
    may be the representative) for her, unlike the stranger/anonymous cases
    above."""
    alice, _stranger, session_id, private_id = _setup(db_session, "owner-control")
    _login(client, db_session, alice)

    r = client.get(f"/api/dashboard/similarity/clusters?pop=session:{session_id}")
    assert r.status_code == 200, r.text
    clusters = r.json()["data"]["clusters"]
    all_member_ids = {m["fipId"] for c in clusters for m in c["members"]}
    assert private_id in all_member_ids
    client.cookies.clear()
