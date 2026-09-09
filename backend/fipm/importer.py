"""Load data/ into the DB idempotently. See spec §3.3."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from fipm.auth import hash_password
from fipm.config import Settings, get_settings
from fipm.db import SessionLocal, init_db
from fipm.fer_types import get_fer_types
from fipm.ids import new_user_id
from fipm.km_content import normalize_source, validate_content
from fipm.models import Fer, KnowledgeModel, User

logger = logging.getLogger(__name__)

REQUIRED_KM_KEYS = {
    "id",
    "version",
    "status",
    "license",
    "source",
    "title",
    "description",
    "sections",
}


@dataclass
class Counter:
    created: int = 0
    updated: int = 0
    skipped: int = 0

    def as_dict(self) -> dict[str, int]:
        return {"created": self.created, "updated": self.updated, "skipped": self.skipped}

    def line(self, label: str) -> str:
        return f"{label}: created={self.created} updated={self.updated} skipped={self.skipped}"


@dataclass
class ImportSummary:
    admin: Counter = field(default_factory=Counter)
    knowledge_models: Counter = field(default_factory=Counter)
    fers: Counter = field(default_factory=Counter)
    fer_types_loaded: int = 0

    def print_report(self) -> None:
        print(self.admin.line("admin"))
        print(self.knowledge_models.line("knowledge_models"))
        print(self.fers.line("fers"))
        print(f"fer_types: loaded={self.fer_types_loaded}")


def _validate_knowledge_model(
    doc: dict, settings: Settings, known_fer_ids: set[str] | None
) -> None:
    """Structural top-level keys, then delegate the `content` shape (sections/
    questions/LangMaps) to `fipm.km_content.validate_content` -- spec
    04-knowledge-model-editor.md §3.3: "The importer's
    `_validate_knowledge_model` is replaced by a call to this module so disk
    and API agree." `known_fer_ids` (spec 08-workshop-picklists.md §1.2 rule
    10) is the importer's `seed.json` snapshot, used to resolve
    `suggestedFerIds`/`inlineFers`."""
    missing = REQUIRED_KM_KEYS - doc.keys()
    if missing:
        raise ValueError(f"missing keys: {sorted(missing)}")
    errors = validate_content(doc, settings=settings, known_fer_ids=known_fer_ids)
    if errors:
        raise ValueError(f"invalid content ({len(errors)} error(s)): {errors[:3]}")


def _load_seed_fer_ids(settings: Settings) -> set[str]:
    """spec 08-workshop-picklists.md §1.2 rule 10: the importer's catalogue
    snapshot is `data/fers/seed.json` itself (read directly, not via the DB
    -- `_import_knowledge_models` runs before `_import_fers` in
    `run_import`)."""
    seed_path = Path(settings.data_dir) / "fers" / "seed.json"
    if not seed_path.is_file():
        return set()
    try:
        entries = json.loads(seed_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    return {e["id"] for e in entries if isinstance(e, dict) and e.get("id")}


def _upsert_fer(db: Session, entry: dict, *, source: str, owner_id: str | None) -> bool:
    """spec 08-workshop-picklists.md §1.3: insert `entry` (an `inlineFers`-
    shaped `{id, label, type, homepage}`) into `fers` if its id is not
    already present. An existing row of *any* source is left untouched --
    promotion never overwrites seed, `user`, `user-promoted` or `model`
    content, and is idempotent. Returns True if a row was created, False if
    skipped. Shared by `_import_knowledge_models` (a system model's
    `inlineFers` are promoted the same way at import time) and
    `routers.knowledge_models.publish_knowledge_model`."""
    fer_id = entry["id"]
    if db.get(Fer, fer_id) is not None:
        return False
    label = entry.get("label") or {}
    label_search = "|".join(str(v).lower() for v in label.values())
    db.add(
        Fer(
            id=fer_id,
            label=label,
            label_search=label_search,
            type=entry.get("type"),
            homepage=entry.get("homepage"),
            owner_id=owner_id,
            source=source,
        )
    )
    db.commit()
    return True


def promote_inline_fers(db: Session, content: dict, owner_id: str | None) -> dict[str, int]:
    """spec 08-workshop-picklists.md §1.3: upsert every `content["inlineFers"]`
    entry into `fers` as `source="model"`, `owner_id` = the model's owner
    (None for a system model). Returns `{"created", "skipped"}` for the
    publish response / import summary."""
    created = 0
    skipped = 0
    for entry in content.get("inlineFers") or []:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        if _upsert_fer(db, entry, source="model", owner_id=owner_id):
            created += 1
        else:
            skipped += 1
    return {"created": created, "skipped": skipped}


def _sha256(doc: dict) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode("utf-8")).hexdigest()


def _bootstrap_admin(db: Session, settings: Settings, summary: ImportSummary) -> None:
    if not settings.admin_email or not settings.admin_password:
        return
    email = settings.admin_email.strip().lower()
    user = db.query(User).filter(User.email == email).one_or_none()
    if user is None:
        user = User(
            id=new_user_id(),
            email=email,
            password_hash=hash_password(settings.admin_password),
            display_name="Admin",
            role="admin",
            language=settings.default_language,
        )
        db.add(user)
        db.commit()
        summary.admin.created += 1
        logger.info("created admin user %s", email)
        return
    if user.role != "admin":
        user.role = "admin"
        db.commit()
        summary.admin.updated += 1
    else:
        summary.admin.skipped += 1
    # Password is never overwritten for an existing admin.


def import_knowledge_model_doc(
    db: Session,
    settings: Settings,
    summary: ImportSummary,
    doc: dict,
    *,
    known_fer_ids: set[str] | None = None,
    force: bool = False,
) -> None:
    """Validate and upsert a single already-parsed knowledge-model `doc`
    (plus its `inlineFers` promotion). Factored out of
    `_import_knowledge_models`'s per-file loop so callers -- notably tests
    that only want "the real gofair-fip-mini-1.0.0 model" -- can import
    exactly one document instead of every file currently sitting in
    `data/knowledge-models/` (which, since the CONFOA 2026 workshop import,
    also holds several `status: "draft"` forks with their own `inlineFers`).
    Importing the whole directory for a single-model fixture used to be
    harmless; now it leaks those forks' promoted `source="model"` FER rows
    into whatever DB the caller passed, which is exactly the coupling that
    made tests/test_ac_08_05_anonymous_fers_source_model.py order-dependent
    on tests that happened to run first and import the full real data/ dir.
    """
    if known_fer_ids is None:
        known_fer_ids = _load_seed_fer_ids(settings)
    _validate_knowledge_model(doc, settings, known_fer_ids)

    content_sha256 = _sha256(doc)
    existing = db.get(KnowledgeModel, (doc["id"], doc["version"]))
    if existing is None:
        db.add(
            KnowledgeModel(
                id=doc["id"],
                version=doc["version"],
                owner_id=None,
                visibility="public",
                is_system=True,
                status=doc["status"],
                license=doc["license"],
                source=normalize_source(doc["source"]),
                title=doc["title"],
                description=doc["description"],
                changelog=doc.get("changelog", []),
                content=doc,
                content_sha256=content_sha256,
            )
        )
        db.commit()
        summary.knowledge_models.created += 1
        # spec 08-workshop-picklists.md §1.3: "python -m fipm import-data
        # ... upsert every inlineFers entry into fers as source=model" --
        # a system model is owner_id=None.
        promoted = promote_inline_fers(db, doc, owner_id=None)
        summary.fers.created += promoted["created"]
        summary.fers.skipped += promoted["skipped"]
    elif existing.content_sha256 == content_sha256:
        summary.knowledge_models.skipped += 1
    elif not force:
        logger.warning(
            "knowledge model %s@%s changed on disk; skipping (rerun with --force)",
            doc["id"],
            doc["version"],
        )
        summary.knowledge_models.skipped += 1
    else:
        existing.is_system = True
        existing.status = doc["status"]
        existing.license = doc["license"]
        existing.source = normalize_source(doc["source"])
        existing.title = doc["title"]
        existing.description = doc["description"]
        existing.changelog = doc.get("changelog", [])
        existing.content = doc
        existing.content_sha256 = content_sha256
        db.commit()
        summary.knowledge_models.updated += 1
        promoted = promote_inline_fers(db, doc, owner_id=None)
        summary.fers.created += promoted["created"]
        summary.fers.skipped += promoted["skipped"]


def _import_knowledge_models(
    db: Session, settings: Settings, summary: ImportSummary, force: bool
) -> None:
    km_dir = Path(settings.data_dir) / "knowledge-models"
    if not km_dir.is_dir():
        return
    known_fer_ids = _load_seed_fer_ids(settings)
    for path in sorted(km_dir.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.warning("skipping invalid knowledge model %s: %s", path, exc)
            summary.knowledge_models.skipped += 1
            continue
        try:
            import_knowledge_model_doc(
                db, settings, summary, doc, known_fer_ids=known_fer_ids, force=force
            )
        except ValueError as exc:
            logger.warning("skipping invalid knowledge model %s: %s", path, exc)
            summary.knowledge_models.skipped += 1


def _import_fers(db: Session, settings: Settings, summary: ImportSummary) -> None:
    seed_path = Path(settings.data_dir) / "fers" / "seed.json"
    if not seed_path.is_file():
        return
    try:
        entries = json.loads(seed_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning("skipping invalid FER seed file %s: %s", seed_path, exc)
        return

    for entry in entries:
        fer_id = entry["id"]
        label = entry["label"]
        label_search = "|".join(str(v).lower() for v in label.values())
        homepage = entry.get("homepage")
        fer_type = entry["type"]
        existing = db.get(Fer, fer_id)
        if existing is None:
            db.add(
                Fer(
                    id=fer_id,
                    label=label,
                    label_search=label_search,
                    type=fer_type,
                    homepage=homepage,
                    owner_id=None,
                    source="seed",
                )
            )
            db.commit()
            summary.fers.created += 1
        elif existing.source != "seed":
            summary.fers.skipped += 1
        elif (
            existing.label == label and existing.type == fer_type and existing.homepage == homepage
        ):
            summary.fers.skipped += 1
        else:
            existing.label = label
            existing.label_search = label_search
            existing.type = fer_type
            existing.homepage = homepage
            db.commit()
            summary.fers.updated += 1


def run_import(force: bool = False) -> ImportSummary:
    """Entry point used by both `python -m fipm import-data` and app startup."""
    settings = get_settings()
    init_db()
    summary = ImportSummary()
    with SessionLocal() as db:
        _bootstrap_admin(db, settings, summary)
        _import_knowledge_models(db, settings, summary, force)
        _import_fers(db, settings, summary)
    summary.fer_types_loaded = len(get_fer_types(settings))
    return summary
