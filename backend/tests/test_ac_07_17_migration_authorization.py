"""AC17 (spec 07-mail-and-migration.md §8): a second signed-in user gets 404
on all three migration endpoints for a private FIP and 403 for a `link` FIP;
an anonymous caller with the right `X-Edit-Token` on a session-less
anonymous FIP may migrate, as may the owner and an admin."""

from __future__ import annotations

from _migration_helpers import build_scenario, register

ADMIN_EMAIL = "ac07-17-admin@example.com"
ADMIN_PASSWORD = "admin-correcthorsebattery"


def _make_admin_client(client_factory, db_session):
    """Promote a freshly-registered user to `role="admin"` directly in the
    DB -- simpler and less invasive than the env-var bootstrap path (spec 05
    §1, exercised by test_ac03_admin_bootstrap.py against an isolated
    subprocess DB), which would require mutating the process-wide
    `get_settings()` cache the whole shared test-session DB relies on."""
    from fipm.models import User

    admin = client_factory()
    register(admin, ADMIN_EMAIL, display_name="Admin")
    user = db_session.query(User).filter(User.email == ADMIN_EMAIL).one()
    user.role = "admin"
    db_session.commit()
    # Re-login so the session cookie's user row (fetched fresh per request
    # via db.get(User, ...)) reflects the new role.
    r = admin.post(
        "/api/auth/login", json={"email": ADMIN_EMAIL, "password": "correcthorsebattery"}
    )
    assert r.status_code == 200, r.text
    return admin


def test_second_user_gets_404_for_private_fip_and_403_for_link_fip(client, client_factory):
    private_scenario = build_scenario(client, "mig17priv", visibility="private")
    link_scenario = build_scenario(client, "mig17link", visibility="link")

    other = client_factory()
    register(other, "mig17-other@example.com")

    for path in (
        f"/api/fips/{private_scenario['fip_id']}/migration-targets",
        f"/api/fips/{private_scenario['fip_id']}/migration-preview?to=1.1.0",
    ):
        r = other.get(path)
        assert r.status_code == 404, f"{path}: {r.text}"
    r = other.post(f"/api/fips/{private_scenario['fip_id']}/migrate", json={"to": "1.1.0"})
    assert r.status_code == 404

    for path in (
        f"/api/fips/{link_scenario['fip_id']}/migration-targets",
        f"/api/fips/{link_scenario['fip_id']}/migration-preview?to=1.1.0",
    ):
        r = other.get(path)
        assert r.status_code == 403, f"{path}: {r.text}"
    r = other.post(f"/api/fips/{link_scenario['fip_id']}/migrate", json={"to": "1.1.0"})
    assert r.status_code == 403


def test_owner_and_admin_may_migrate(client, client_factory, db_session):
    owner_scenario = build_scenario(client, "mig17owner")
    owner_migrate = client.post(
        f"/api/fips/{owner_scenario['fip_id']}/migrate", json={"to": "1.1.0"}
    )
    assert owner_migrate.status_code == 200, owner_migrate.text

    admin = _make_admin_client(client_factory, db_session)
    other_scenario = build_scenario(client, "mig17admin")
    admin_migrate = admin.post(
        f"/api/fips/{other_scenario['fip_id']}/migrate", json={"to": "1.1.0"}
    )
    assert admin_migrate.status_code == 200, admin_migrate.text


def test_edit_token_holder_is_authorized_same_as_owner_admin(client, client_factory):
    """The only way to create an anonymous, edit-token-writable FIP in this
    codebase is via a workshop session (`POST /api/fips` with no login and
    no `sessionId` is 400 `session_id_or_login_required` --
    `routers/fips.py::create_fip` never issues an `edit_token_hash` outside
    the session branch). A session FIP is pinned to its session's version
    (AC16), so it cannot *complete* a migrate to a newer version; what this
    asserts instead is that the token holder clears authorization (same as
    an owner or admin -- not 403/404) and reaches the version-specific
    checks, exactly like AC16's `migration-targets`/`migration-preview`
    200s already show for the same token."""
    from test_ac_07_16_migration_session_pin import _build_session_scenario

    scenario = _build_session_scenario(client, client_factory, "mig17token")
    fip_id = scenario["fip_id"]
    headers = {"X-Edit-Token": scenario["edit_token"]}

    # Migrating to the session's own (current) version clears the pin check
    # (spec §4: pinned only when the target *differs* from the session's
    # version) and reaches the ordinary already-on-version check --
    # demonstrating the token authorizes the write, not merely reads.
    r = client.post(f"/api/fips/{fip_id}/migrate", json={"to": "1.0.0"}, headers=headers)
    assert r.status_code == 409
    assert r.json()["detail"] == "already_on_version"

    # No token, no login, not the session owner: authorization itself fails
    # before any version check is reached.
    r_no_token = client.post(f"/api/fips/{fip_id}/migrate", json={"to": "1.0.0"})
    assert r_no_token.status_code == 403
    assert r_no_token.json()["detail"] == "edit_token_required"
