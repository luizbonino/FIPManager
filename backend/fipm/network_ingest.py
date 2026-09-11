"""spec 13-fip-dashboard.md §5.4: `python -m fipm ingest-network-fips`.

**D8: the dashboard never calls the network.** This module is the *only*
code path that does, and it runs as a cron job (or a one-off before a
workshop), never inside a request. It walks
`fipm.network.get_fip_communities()` then `get_community_fip()` per
community (both already reused verbatim, never reimplemented), and writes
**read-only shadow rows** -- `source='network'`, no `fips` row -- into
`fip_facets`/`fip_cells`/`fip_declarations`/`fip_signatures`/
`fip_signature_bands`, keyed by `network_fips.fip_id`.

The resource IRI a network declaration names is used **as the `ferId`
itself**, never mapped through the local FER catalogue: a local FIP that
also happens to declare the identical `https://...` resource converges on
the same `fer_key` (spec §1.5) with no extra bookkeeping, which is exactly
what makes cross-boundary similarity (test 37) "a two-parameter query
rather than a feature" (§5.4)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from fipm import network as network_module
from fipm.config import Settings
from fipm.models import (
    DashboardMeta,
    FipCell,
    FipDeclaration,
    FipFacets,
    KnowledgeModel,
    NetworkFip,
)
from fipm.projection import (
    bump_fer_key_df,
    delete_signature_rows,
    project_answers,
    write_signature_rows,
)

# The network's declarations are always over the fixed GO FAIR mini
# questionnaire (spec 11 §3.3: "questions is all 21, in gofair-fip-mini
# order") -- there is no per-community knowledge-model choice to make.
NETWORK_KM_ID = "gofair-fip-mini"
NETWORK_KM_VERSION = "1.0.0"


def network_fip_id(community_iri: str) -> str:
    """`'net:' + sha256(community_iri)[:22]` (spec §5.4) -- deliberately not
    a valid `fips.id` shape, so a network shadow row can never alias a real
    FIP and `check-declarations`/population resolution can tell the two
    apart by prefix alone if ever needed."""
    return "net:" + hashlib.sha256(community_iri.encode("utf-8")).hexdigest()[:22]


@dataclass
class IngestReport:
    communities_seen: int = 0
    fips_written: int = 0
    fips_failed: int = 0
    declarations_written: int = 0
    unmapped_dropped: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "communitiesSeen": self.communities_seen,
            "fipsWritten": self.fips_written,
            "fipsFailed": self.fips_failed,
            "declarationsWritten": self.declarations_written,
            "unmappedDropped": self.unmapped_dropped,
            "errors": self.errors[:20],
        }

    def print_report(self) -> None:
        unit = "y" if self.communities_seen == 1 else "ies"
        print(
            f"ingest-network-fips: {self.fips_written} FIP(s) written, "
            f"{self.fips_failed} failed, {self.declarations_written} declaration(s), "
            f"{self.unmapped_dropped} unmapped declaration(s) dropped "
            f"(of {self.communities_seen} communit{unit} seen)"
        )
        for err in self.errors[:20]:
            print(f"  ! {err}")


def _answers_from_payload(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """Maps `get_community_fip`'s response (already run through
    `rdf.question_id_from_individual` + the `fer_types` inversion inside
    `fipm.network`, spec 11 §3.3 -- reused, not reimplemented) into the
    `Fip.answers` shape `project_answers` expects. `unmapped` (spec 11
    §3.3's non-mini/FSR questions) has no `question_id` in our vocabulary
    and is dropped -- its declaration count is returned so the caller's
    report makes the drop visible, per spec §5.4."""
    answers: list[dict[str, Any]] = []
    for question in payload["questions"]:
        question_id = question["questionId"]
        declarations: list[dict[str, Any]] = []
        for decl in question["declarations"]:
            status = decl.get("status")
            if status is None:
                continue
            if status == "none":
                considerations = decl.get("considerations")
                if considerations:
                    declarations.append({"ferFreeText": considerations[:500], "status": "none"})
                continue
            resource = decl.get("resource")
            if resource is None or not resource.get("iri"):
                continue
            declarations.append({"ferId": resource["iri"], "status": status})
        if declarations:
            answers.append({"questionId": question_id, "declarations": declarations})
    unmapped_count = sum(len(entry["declarations"]) for entry in payload.get("unmapped", []))
    return answers, unmapped_count


def _current_epoch(db: Session) -> int:
    row = db.get(DashboardMeta, "projection_epoch")
    return int(row.value) if row is not None else 0


def _write_network_projection(
    db: Session,
    fip_id: str,
    km_content: dict[str, Any] | None,
    answers: list[dict[str, Any]],
    now: datetime,
) -> int:
    """Delete-then-insert, exactly `reproject_fip`'s discipline (spec §1.6)
    but for a shadow row with no `Fip`/`fips` counterpart -- so this cannot
    call `reproject_fip`/`unproject_fip` themselves (both assume a `Fip`
    row) and instead calls the smaller building blocks they're built from.
    `public=True` always: network rows are public nanopublications by
    construction (§5.4). Returns the declaration count written."""
    old_declarations = list(
        db.execute(
            select(FipDeclaration.question_id, FipDeclaration.fer_key, FipDeclaration.status).where(
                FipDeclaration.fip_id == fip_id
            )
        )
    )
    if old_declarations:
        bump_fer_key_df(db, old_declarations, sign=-1, public=True)

    db.execute(delete(FipCell).where(FipCell.fip_id == fip_id))
    db.execute(delete(FipDeclaration).where(FipDeclaration.fip_id == fip_id))
    db.execute(delete(FipFacets).where(FipFacets.fip_id == fip_id))
    delete_signature_rows(db, fip_id)

    projected = project_answers(km_content, answers)
    db.add(
        FipFacets(
            fip_id=fip_id,
            source="network",
            questionnaire_id=NETWORK_KM_ID,
            questionnaire_version=NETWORK_KM_VERSION,
            area_key=f"{NETWORK_KM_ID}@{NETWORK_KM_VERSION}",
            language="en",
            question_count=projected.question_count,
            answered_questions=projected.answered_questions,
            not_applicable_questions=projected.not_applicable_questions,
            declaration_count=projected.declaration_count,
            current_declarations=projected.current_declarations,
            token_count=projected.token_count,
            migrated_from_id=None,
            migrated_from_version=None,
            fip_created_at=now,
            fip_updated_at=now,
            projected_at=now,
            projection_epoch=_current_epoch(db),
        )
    )
    for cell in projected.cells:
        db.add(
            FipCell(
                fip_id=fip_id,
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
        db.add(
            FipDeclaration(
                fip_id=fip_id,
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
    write_signature_rows(db, fip_id, projected.cells, projected.declarations, computed_at=now)
    bump_fer_key_df(db, projected.declarations, sign=1, public=True)
    return projected.declaration_count


def ingest_network_fips(
    db: Session,
    settings: Settings,
    *,
    limit: int | None = None,
    community_iri: str | None = None,
    since: str | None = None,
) -> IngestReport:
    """spec §5.4. `community_iri` scopes to one community (used by tests,
    to avoid walking the full (recorded) community list); `limit` caps how
    many of `get_fip_communities()`'s results are ingested; `since` skips a
    community whose `network_fips.fetched_at` is already `>= since` (a
    coarse, client-side approximation of the 2027 "`--since`-incremental"
    note in §5.4 -- Q0 itself has no server-side date filter)."""
    report = IngestReport()
    km = db.get(KnowledgeModel, (NETWORK_KM_ID, NETWORK_KM_VERSION))
    if km is None:
        report.errors.append(
            f"{NETWORK_KM_ID}@{NETWORK_KM_VERSION} knowledge model not found -- "
            "run `python -m fipm import-data` first"
        )
        return report
    km_content = km.content

    if community_iri:
        communities: list[dict[str, Any]] = [{"iri": community_iri, "label": None}]
    else:
        items, _cached_at, _stale = network_module.get_fip_communities(settings)
        communities = list(items)
        if limit is not None:
            communities = communities[:limit]

    since_dt = None
    if since:
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))

    report.communities_seen = len(communities)
    now = datetime.now(UTC)

    for community in communities:
        iri = community["iri"]
        fip_id = network_fip_id(iri)

        if since_dt is not None:
            existing = db.get(NetworkFip, fip_id)
            if existing is not None and existing.fetched_at >= since_dt:
                continue

        try:
            payload, _cached_at, _stale = network_module.get_community_fip(settings, iri)
        except network_module.NetworkError as exc:
            report.fips_failed += 1
            report.errors.append(f"{iri}: {exc.code}")
            continue

        answers, unmapped_count = _answers_from_payload(payload)
        report.unmapped_dropped += unmapped_count

        declaration_count = _write_network_projection(db, fip_id, km_content, answers, now)
        report.declarations_written += declaration_count

        row = db.get(NetworkFip, fip_id)
        if row is None:
            row = NetworkFip(fip_id=fip_id, community_iri=iri, fetched_at=now)
            db.add(row)
        row.label = community.get("label") or payload["fip"].get("label")
        row.fip_nanopub_iri = payload["fip"].get("nanopubIri")
        row.index_iri = payload["fip"].get("indexIri")
        row.created = payload["fip"].get("created")
        row.fetched_at = now
        row.questionnaire_id = NETWORK_KM_ID
        row.questionnaire_version = NETWORK_KM_VERSION
        db.commit()
        report.fips_written += 1

    return report
