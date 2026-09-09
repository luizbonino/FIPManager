"""Facilitator-editable draft knowledge models (CONFOA 2026 workshop fix):
the importer's `_validate_knowledge_model`/`import_knowledge_model_doc`
sets `is_system = (doc status == "published")`, so a shipped
`status: "draft"` file (the CONFOA 2026 workshop forks) imports as
`is_system=False, owner_id=None` -- an "unowned draft" awaiting facilitator
review, distinct from both a built-in system model (`is_system=True`) and a
user's own draft (`owner_id` set). Covers: import sets is_system correctly;
an admin can list/edit/publish an unowned draft and claims it on first
write; a non-admin gets 403 forbidden (not the system-model 403); re-import
never overwrites a claimed, edited draft; re-import syncs an unclaimed
draft whose file changed; a genuinely published system model is unaffected.
"""

from __future__ import annotations

from fipm.config import get_settings
from fipm.db import SessionLocal
from fipm.importer import ImportSummary, import_knowledge_model_doc
from fipm.km_content import content_sha256
from fipm.models import KnowledgeModel, User

PRIVACY_VERSION = "test-v1"


def _register(client, email: str, display_name: str = "U") -> str:
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": display_name,
            "privacyAcceptedVersion": PRIVACY_VERSION,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _promote_to_admin(email: str) -> None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).one()
        user.role = "admin"
        db.commit()


def _draft_doc(km_id: str, *, title: str = "Draft model", status: str = "draft") -> dict:
    return {
        "id": km_id,
        "version": "1.0.0",
        "status": status,
        "license": "CC0-1.0",
        "source": "Test workshop",
        "title": {"en": title},
        "description": {"en": f"{title} description"},
        "changelog": [],
        "sections": [],
    }


def _import_doc(db_session, doc: dict, *, force: bool = False) -> ImportSummary:
    summary = ImportSummary()
    import_knowledge_model_doc(db_session, get_settings(), summary, doc, force=force)
    return summary


def _make_unowned_draft(db_session, km_id: str) -> KnowledgeModel:
    """Directly insert an unowned-draft row (is_system=False, owner_id=None,
    status=draft) -- the shape the importer now produces for a shipped
    `status: "draft"` file -- without going through the importer, for tests
    that only care about the router's authorization/listing behaviour."""
    doc = _draft_doc(km_id)
    km = KnowledgeModel(
        id=km_id,
        version="1.0.0",
        owner_id=None,
        visibility="public",
        status="draft",
        is_system=False,
        license=doc["license"],
        source=doc["source"],
        title=doc["title"],
        description=doc["description"],
        changelog=[],
        content=doc,
        content_sha256=content_sha256(doc),
    )
    db_session.add(km)
    db_session.commit()
    return km


# ---------------------------------------------------------------------------
# Importer: is_system derived from doc status
# ---------------------------------------------------------------------------


def test_draft_doc_imports_as_unowned_non_system(db_session):
    doc = _draft_doc("unowned-draft-import-km")
    summary = _import_doc(db_session, doc)
    assert summary.knowledge_models.created == 1

    row = db_session.get(KnowledgeModel, ("unowned-draft-import-km", "1.0.0"))
    assert row is not None
    assert row.is_system is False
    assert row.owner_id is None
    assert row.status == "draft"


def test_published_doc_still_imports_as_system(db_session):
    doc = _draft_doc("published-import-km", status="published")
    summary = _import_doc(db_session, doc)
    assert summary.knowledge_models.created == 1

    row = db_session.get(KnowledgeModel, ("published-import-km", "1.0.0"))
    assert row.is_system is True
    assert row.owner_id is None


def test_reimport_updates_unclaimed_draft_whose_file_changed(db_session):
    doc = _draft_doc("unclaimed-draft-sync-km", title="Original title")
    _import_doc(db_session, doc)

    changed = _draft_doc("unclaimed-draft-sync-km", title="Updated title")
    # No --force: an unclaimed draft is synced unconditionally.
    summary = _import_doc(db_session, changed, force=False)
    assert summary.knowledge_models.updated == 1
    assert summary.knowledge_models.skipped == 0

    row = db_session.get(KnowledgeModel, ("unclaimed-draft-sync-km", "1.0.0"))
    assert row.title == {"en": "Updated title"}
    assert row.owner_id is None
    assert row.is_system is False


def test_reimport_never_overwrites_a_claimed_edited_draft(client, db_session):
    facilitator_id = _register(client, "unowned-draft-claim-protect@example.com")

    doc = _draft_doc("claimed-draft-protect-km", title="Original title")
    _import_doc(db_session, doc)

    row = db_session.get(KnowledgeModel, ("claimed-draft-protect-km", "1.0.0"))
    row.owner_id = facilitator_id
    edited_content = dict(row.content)
    edited_content["title"] = {"en": "Facilitator-edited title"}
    row.title = {"en": "Facilitator-edited title"}
    row.content = edited_content
    row.content_sha256 = content_sha256(edited_content)
    db_session.commit()

    changed_on_disk = _draft_doc("claimed-draft-protect-km", title="Disk title changed again")
    # Even with --force, a claimed draft's edits must survive re-import.
    summary = _import_doc(db_session, changed_on_disk, force=True)
    assert summary.knowledge_models.skipped == 1
    assert summary.knowledge_models.updated == 0

    db_session.expire_all()
    row = db_session.get(KnowledgeModel, ("claimed-draft-protect-km", "1.0.0"))
    assert row.title == {"en": "Facilitator-edited title"}
    assert row.owner_id == facilitator_id


# ---------------------------------------------------------------------------
# Router: authorization + listing
# ---------------------------------------------------------------------------


def test_admin_lists_and_claims_unowned_draft_via_patch(client, db_session):
    _make_unowned_draft(db_session, "unowned-draft-patch-km")

    admin_email = "unowned-draft-admin-patch@example.com"
    admin_id = _register(client, admin_email)
    _promote_to_admin(admin_email)

    listing = client.get("/api/knowledge-models")
    assert listing.status_code == 200, listing.text
    item = next(i for i in listing.json()["items"] if i["id"] == "unowned-draft-patch-km")
    assert item["isUnownedDraft"] is True
    assert item["isSystem"] is False
    assert item["ownerId"] is None

    patched = client.patch(
        "/api/knowledge-models/unowned-draft-patch-km/1.0.0",
        json={"title": {"en": "Reviewed title"}},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["ownerId"] == admin_id

    db_session.expire_all()
    row = db_session.get(KnowledgeModel, ("unowned-draft-patch-km", "1.0.0"))
    assert row.owner_id == admin_id
    assert row.is_system is False


def test_admin_claims_unowned_draft_via_put_content_and_can_publish(client, db_session):
    _make_unowned_draft(db_session, "unowned-draft-publish-km")

    admin_email = "unowned-draft-admin-publish@example.com"
    admin_id = _register(client, admin_email)
    _promote_to_admin(admin_email)

    # publish (below) requires at least one non-hidden question.
    sections = [
        {
            "id": "findable",
            "title": {"en": "Findable"},
            "questions": [
                {
                    "id": "F2",
                    "principle": "F2",
                    "scope": None,
                    "text": {"en": "Which metadata schema do you use?"},
                    "help": None,
                    "ferType": "metadata-schema",
                    "required": True,
                    "allowMultiple": False,
                }
            ],
        }
    ]
    etag = client.get("/api/knowledge-models/unowned-draft-publish-km/1.0.0").headers["etag"]
    put = client.put(
        "/api/knowledge-models/unowned-draft-publish-km/1.0.0/content",
        headers={"If-Match": etag},
        json={"sections": sections},
    )
    assert put.status_code == 200, put.text
    assert put.json()["ownerId"] == admin_id

    published = client.post(
        "/api/knowledge-models/unowned-draft-publish-km/1.0.0/publish",
        json={"notes": "reviewed by facilitator"},
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"
    assert published.json()["ownerId"] == admin_id

    db_session.expire_all()
    row = db_session.get(KnowledgeModel, ("unowned-draft-publish-km", "1.0.0"))
    assert row.owner_id == admin_id
    assert row.is_system is False
    assert row.status == "published"


def test_non_admin_gets_403_forbidden_on_unowned_draft_write(client, db_session):
    _make_unowned_draft(db_session, "unowned-draft-nonadmin-km")
    _register(client, "unowned-draft-nonadmin@example.com")

    # Still readable (visibility=public) even though it's an unowned draft.
    get_resp = client.get("/api/knowledge-models/unowned-draft-nonadmin-km/1.0.0")
    assert get_resp.status_code == 200

    # Excluded from the default (non-admin) listing: neither published+public
    # nor owned by this caller.
    listing = client.get("/api/knowledge-models")
    ids = [i["id"] for i in listing.json()["items"]]
    assert "unowned-draft-nonadmin-km" not in ids

    patch = client.patch(
        "/api/knowledge-models/unowned-draft-nonadmin-km/1.0.0",
        json={"title": {"en": "Hijack attempt"}},
    )
    assert patch.status_code == 403
    assert patch.json()["detail"] == "forbidden"

    etag = get_resp.headers["etag"]
    put = client.put(
        "/api/knowledge-models/unowned-draft-nonadmin-km/1.0.0/content",
        headers={"If-Match": etag},
        json={"sections": []},
    )
    assert put.status_code == 403
    assert put.json()["detail"] == "forbidden"

    publish = client.post(
        "/api/knowledge-models/unowned-draft-nonadmin-km/1.0.0/publish", json={"notes": "x"}
    )
    assert publish.status_code == 403
    assert publish.json()["detail"] == "forbidden"

    delete = client.request("DELETE", "/api/knowledge-models/unowned-draft-nonadmin-km/1.0.0")
    assert delete.status_code == 403
    assert delete.json()["detail"] == "forbidden"

    db_session.expire_all()
    row = db_session.get(KnowledgeModel, ("unowned-draft-nonadmin-km", "1.0.0"))
    assert row.owner_id is None


def test_admin_still_cannot_edit_a_true_system_model_in_place(client):
    admin_email = "system-model-admin-blocked@example.com"
    _register(client, admin_email)
    _promote_to_admin(admin_email)

    patch = client.patch("/api/knowledge-models/test-km/1.0.0", json={"title": {"en": "Hijack"}})
    assert patch.status_code == 403
    assert patch.json()["detail"] == "system_model_readonly"

    delete = client.request("DELETE", "/api/knowledge-models/test-km/1.0.0")
    assert delete.status_code == 403
    assert delete.json()["detail"] == "system_model_readonly"

    # Admin may still PATCH visibility only, per spec 04 §7 A2 (unchanged).
    visibility = client.patch("/api/knowledge-models/test-km/1.0.0", json={"visibility": "public"})
    assert visibility.status_code == 200

    listing = client.get("/api/knowledge-models")
    item = next(i for i in listing.json()["items"] if i["id"] == "test-km")
    assert item["isSystem"] is True
    assert item["isUnownedDraft"] is False
