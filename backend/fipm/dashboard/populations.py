"""spec 13-fip-dashboard.md §2: population spec parsing, canonicalisation,
`auth_scope`/`population_hash`, and the §2.2 resolver -- **the** place the
security predicate lives. Population resolution never reads a fact table
(`fip_cells`/`fip_declarations`/`fip_facets`) for authorization (D2): it
runs once, here, against the authoritative `fips` table, and every view
consumes only the `fip_id` list this module hands back."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import String, and_, false, literal, or_, select, true, union_all
from sqlalchemy.orm import Session, aliased

from fipm.config import get_settings
from fipm.dashboard import DashboardError
from fipm.models import DashboardMeta, Fip, FipFacets, NetworkFip, User, WorkshopSession

TERM_KINDS = frozenset({"session", "public", "network", "questionnaire", "area", "mine"})
MAX_TERMS = 20


def _invalid(reason: str = "invalid_population") -> DashboardError:
    return DashboardError(400, {"detail": reason})


def _parse_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _invalid() from exc


# ---------------------------------------------------------------------------
# §2.1 -- parsing and canonicalisation
# ---------------------------------------------------------------------------


def _validate_term(term: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(term, dict):
        raise _invalid()
    kind = term.get("kind")
    if kind not in TERM_KINDS:
        raise _invalid()
    out: dict[str, Any] = {"kind": kind}
    if kind == "session":
        if not isinstance(term.get("id"), str) or not term["id"]:
            raise _invalid()
        out["id"] = term["id"]
    elif kind == "questionnaire":
        if not isinstance(term.get("id"), str) or not isinstance(term.get("version"), str):
            raise _invalid()
        out["id"] = term["id"]
        out["version"] = term["version"]
    elif kind == "area":
        for key in ("sessionId", "id", "version"):
            if not isinstance(term.get(key), str) or not term[key]:
                raise _invalid()
        out["sessionId"] = term["sessionId"]
        out["id"] = term["id"]
        out["version"] = term["version"]
    # "public", "network", "mine" carry no extra fields.
    return out


def _validate_term_list(raw: Any, *, required: bool) -> list[dict[str, Any]]:
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise _invalid()
    if required and not (1 <= len(raw) <= MAX_TERMS):
        raise _invalid()
    if not required and len(raw) > MAX_TERMS:
        raise _invalid()
    return [_validate_term(t) for t in raw]


def parse_population_spec(raw: dict[str, Any]) -> dict[str, Any]:
    """400 `invalid_population` for anything structurally wrong -- an
    unknown `kind` is never silently ignored (spec §2.1)."""
    if not isinstance(raw, dict):
        raise _invalid()
    include = _validate_term_list(raw.get("include"), required=True)
    exclude = _validate_term_list(raw.get("exclude"), required=False)
    updated_after = raw.get("updatedAfter")
    updated_before = raw.get("updatedBefore")
    if updated_after is not None and not isinstance(updated_after, str):
        raise _invalid()
    if updated_before is not None and not isinstance(updated_before, str):
        raise _invalid()
    return {
        "version": 1,
        "include": include,
        "exclude": exclude,
        "updatedAfter": updated_after,
        "updatedBefore": updated_before,
    }


def _term_sort_key(term: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        term.get("kind", ""),
        term.get("id", ""),
        term.get("version", ""),
        term.get("sessionId", ""),
    )


def _canonical_term_list(terms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = [{k: v for k, v in t.items() if v is not None} for t in terms]
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for t in sorted(cleaned, key=_term_sort_key):
        key = json.dumps(t, sort_keys=True, separators=(",", ":"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(t)
    return deduped


def canonicalise_spec(spec: dict[str, Any]) -> str:
    """spec §2.1: sort each term list, drop duplicates, drop nulls,
    `json.dumps(..., sort_keys=True, separators=(",", ":"))`."""
    canonical: dict[str, Any] = {
        "version": spec.get("version", 1),
        "include": _canonical_term_list(spec.get("include") or []),
    }
    excluded = _canonical_term_list(spec.get("exclude") or [])
    if excluded:
        canonical["exclude"] = excluded
    if spec.get("updatedAfter"):
        canonical["updatedAfter"] = spec["updatedAfter"]
    if spec.get("updatedBefore"):
        canonical["updatedBefore"] = spec["updatedBefore"]
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"))


def auth_scope_for(spec: dict[str, Any], viewer: User | None) -> str:
    """spec §2.3. **Deviation, recorded in the brief-A report:** the spec's
    literal three-way enum collapses an admin viewer's non-public-only
    queries into one shared `'admin'` bucket "when the resolved set differs
    from the pub set" -- but a `questionnaire` term's resolved set already
    differs per viewer identity (not just admin-vs-not, since a
    `questionnaire` term carries no visibility restriction of its own, see
    §2.2), and two *different* admins (or two admins reusing the literal
    `'admin'` tag) would then collide on one `dashboard_snapshots` row for
    different actual result sets. This implementation is strictly finer:
    every term kind other than `public`/`network` maps to `'u:<viewer_id>'`
    -- the *requesting* viewer's own id, admin or not -- which can never
    collide between two viewers with different rights (test AC-10's
    property) at the cost of not sharing one cached snapshot across all
    admins. `'admin'` (the literal string) is never emitted."""
    terms = (spec.get("include") or []) + (spec.get("exclude") or [])
    pub_only = all(t.get("kind") in ("public", "network") for t in terms)
    if pub_only:
        return "pub"
    if viewer is not None:
        return f"u:{viewer.id}"
    return "anon"


def population_hash(canonical: str, scope: str) -> str:
    return hashlib.sha256(f"{canonical}|{scope}".encode()).hexdigest()[:32]


def current_projection_epoch(db: Session) -> int:
    """`dashboard_meta['projection_epoch']`, read outside a population
    resolution -- used by the always-live similarity endpoints (`pair`) whose
    ETag still needs to invalidate on a knowledge-model edit even though they
    never call `resolve_population`."""
    row = db.get(DashboardMeta, "projection_epoch")
    return int(row.value or 0) if row is not None else 0


def decode_inline_pop(value: str) -> dict[str, Any]:
    """`?pop=<urlsafe-base64 of the canonical JSON>`, capped at 2 KB (§2.1)."""
    if len(value) > 2048:
        raise _invalid()
    padded = value + "=" * (-len(value) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001 - any decode failure is just an invalid pop
        raise _invalid() from exc


def shorthand_spec(value: str) -> dict[str, Any] | None:
    """The three server-expanded shorthands (§2.1): `session:<id>`,
    `public`, `network`. Returns `None` if `value` isn't one of them."""
    if value == "public":
        return {"include": [{"kind": "public"}]}
    if value == "network":
        return {"include": [{"kind": "network"}]}
    if value.startswith("session:") and len(value) > len("session:"):
        return {"include": [{"kind": "session", "id": value[len("session:") :]}]}
    return None


# ---------------------------------------------------------------------------
# §2.2/§2.4/§1.8 -- resolution, authorization, k-anonymity, staleness
# ---------------------------------------------------------------------------


@dataclass
class PopulationMember:
    fip_id: str
    updated_at: datetime
    visibility: str
    owner_id: str | None
    session_id: str | None
    readable_individually: bool
    facets_fip_updated_at: datetime | None
    facets_projection_epoch: int | None


@dataclass
class ResolvedPopulation:
    members: list[PopulationMember] = field(default_factory=list)
    current_epoch: int = 0

    @property
    def fip_ids(self) -> list[str]:
        return [m.fip_id for m in self.members]

    @property
    def count(self) -> int:
        return len(self.members)

    @property
    def k_hidden(self) -> int:
        return sum(1 for m in self.members if not m.readable_individually)

    @property
    def stale_ids(self) -> list[str]:
        return [
            m.fip_id
            for m in self.members
            if m.facets_fip_updated_at is None
            or m.facets_fip_updated_at != m.updated_at
            or (m.facets_projection_epoch or 0) < self.current_epoch
        ]

    @property
    def unprojected_count(self) -> int:
        return sum(1 for m in self.members if m.facets_fip_updated_at is None)


def _readable_individually_expr(viewer: User | None):
    """Python-evaluable predicate for spec §2.4's `readable_individually`:
    "not public, not owned, **not in an owned session**, viewer not admin".
    The session-ownership clause is the one `fipm.authz.can_read` doesn't
    need (a plain `GET /api/fips/{id}` has no session-owner shortcut of its
    own -- session ownership only ever mattered for population membership,
    §2.2's security predicate), so it is spelled out here rather than
    delegated. Round-3 fix (item G): `owned_session_match` is now a column
    computed in SQL by the caller's own resolution statement (the same
    `owned_sessions_subq` already embedded in its security predicate),
    passed in per-row -- not a separately fetched `owned_session_ids` set,
    which cost the caller an extra statement per resolution and broke its
    documented statement budget. Used for both k-anonymity's `k_hidden`
    and (in brief B) filtering any view that names an individual FIP."""

    def _check(visibility: str, owner_id: str | None, owned_session_match: bool) -> bool:
        if viewer is not None and (
            viewer.role == "admin"
            or (owner_id is not None and viewer.id == owner_id)
            or owned_session_match
        ):
            return True
        return visibility in ("public", "link")

    return _check


def resolve_population(
    db: Session,
    spec: dict[str, Any],
    viewer: User | None,
    *,
    include_network: bool = True,
) -> ResolvedPopulation:
    """spec §2.2. Two statements when the spec's `include` list names
    `{"kind": "network"}` (the local `fips` query below, `UNION ALL`-ed with
    a `network_fips` one per spec §2.2's own sketch); one statement
    otherwise. `include_network=False` is an escape hatch for a caller that
    wants the local-only resolution regardless of the spec (none does,
    today) -- brief A's `TODO(spec13-B)` is resolved by brief B's
    `network_fips` table (§5.4) landing; every existing call site picks up
    network support with no change of its own, since the default is now
    `True` and the `{"kind": "network"}` gate (`inc_network` below) already
    makes the branch a no-op unless the spec actually asks for it."""
    include = spec.get("include") or []
    exclude = spec.get("exclude") or []

    inc_public = any(t["kind"] == "public" for t in include)
    inc_mine = any(t["kind"] == "mine" for t in include)
    inc_network = include_network and any(t["kind"] == "network" for t in include)
    inc_sessions = [t["id"] for t in include if t["kind"] == "session"]
    inc_km_refs = [(t["id"], t["version"]) for t in include if t["kind"] == "questionnaire"]
    inc_areas = [(t["sessionId"], t["id"], t["version"]) for t in include if t["kind"] == "area"]

    exc_sessions = [t["id"] for t in exclude if t["kind"] == "session"]
    exc_km_refs = [(t["id"], t["version"]) for t in exclude if t["kind"] == "questionnaire"]
    exc_areas = [(t["sessionId"], t["id"], t["version"]) for t in exclude if t["kind"] == "area"]

    include_clauses = []
    if inc_public:
        include_clauses.append(Fip.visibility == "public")
    if inc_sessions:
        include_clauses.append(Fip.session_id.in_(inc_sessions))
    if inc_km_refs:
        include_clauses.append(
            or_(
                *[
                    and_(Fip.questionnaire_id == kid, Fip.questionnaire_version == kver)
                    for kid, kver in inc_km_refs
                ]
            )
        )
    if inc_areas:
        include_clauses.append(
            or_(
                *[
                    and_(
                        Fip.session_id == sid,
                        Fip.questionnaire_id == kid,
                        Fip.questionnaire_version == kver,
                    )
                    for sid, kid, kver in inc_areas
                ]
            )
        )
    if viewer is not None and inc_mine:
        include_clauses.append(Fip.owner_id == viewer.id)
    if not include_clauses:
        # Every include term was "network" (or the include list is empty) --
        # a spec that matches nothing *local*, not an error; the network
        # branch below (if `inc_network`) still contributes its own rows.
        include_predicate = false()
    else:
        include_predicate = or_(*include_clauses)

    exclude_clauses = []
    if exc_sessions:
        exclude_clauses.append(Fip.session_id.in_(exc_sessions))
    if exc_km_refs:
        exclude_clauses.append(
            or_(
                *[
                    and_(Fip.questionnaire_id == kid, Fip.questionnaire_version == kver)
                    for kid, kver in exc_km_refs
                ]
            )
        )
    if exc_areas:
        exclude_clauses.append(
            or_(
                *[
                    and_(
                        Fip.session_id == sid,
                        Fip.questionnaire_id == kid,
                        Fip.questionnaire_version == kver,
                    )
                    for sid, kid, kver in exc_areas
                ]
            )
        )
    exclude_predicate = or_(*exclude_clauses) if exclude_clauses else false()

    viewer_id = viewer.id if viewer is not None else None
    viewer_is_admin = viewer is not None and viewer.role == "admin"
    owned_sessions_subq = (
        select(WorkshopSession.id).where(WorkshopSession.owner_id == viewer_id)
        if viewer_id is not None
        else None
    )

    security_clauses = [Fip.visibility == "public"]
    if viewer_id is not None:
        security_clauses.append(Fip.owner_id == viewer_id)
        security_clauses.append(Fip.session_id.in_(owned_sessions_subq))
    if viewer_is_admin:
        security_clauses.append(true())
    security_predicate = or_(*security_clauses)

    date_clauses = []
    after = _parse_iso8601(spec.get("updatedAfter"))
    before = _parse_iso8601(spec.get("updatedBefore"))
    if after is not None:
        date_clauses.append(Fip.updated_at >= after)
    if before is not None:
        date_clauses.append(Fip.updated_at < before)

    epoch_subq = (
        select(DashboardMeta.value).where(DashboardMeta.key == "projection_epoch").scalar_subquery()
    )

    # Round-3 fix (item G): a prior round's k-anonymity "owned session"
    # fix computed this per-row in Python from a *separately fetched*
    # `owned_session_ids` set (one extra `SELECT id FROM workshop_sessions
    # ...` round trip on every resolution with a signed-in viewer), which
    # silently broke this function's own documented "two statements /
    # one statement" budget (and, downstream, `coverage`/`gaps`/etc.'s
    # spec §8.2 hard statement-count budgets -- AC caught at N=2000 by
    # `tests/scale/test_scale_13_dashboard.py`). `owned_sessions_subq`
    # (used in `security_predicate` above) is already embedded in this
    # same statement, so the membership check can be pushed into SQL as an
    # ordinary boolean column instead of paying for a second statement.
    owned_session_match_expr = (
        Fip.session_id.in_(owned_sessions_subq) if owned_sessions_subq is not None else false()
    )

    local_stmt = (
        select(
            Fip.id,
            Fip.updated_at,
            Fip.visibility,
            Fip.owner_id,
            Fip.session_id,
            owned_session_match_expr.label("owned_session_match"),
            FipFacets.fip_updated_at,
            FipFacets.projection_epoch,
            epoch_subq.label("current_epoch"),
        )
        .outerjoin(FipFacets, and_(FipFacets.fip_id == Fip.id, FipFacets.source == "local"))
        .where(
            include_predicate,
            # `~exclude_predicate` would be wrong here: for a NULLable
            # column (session_id in particular), `col IN (...)` evaluates
            # to SQL NULL rather than FALSE when col IS NULL, and `NOT
            # NULL` is *also* NULL -- which fails the WHERE clause and
            # silently drops every row with a NULL session_id, even ones
            # that plainly don't match any exclude term. `IS NOT TRUE`
            # treats both FALSE and NULL as "not excluded", correctly.
            exclude_predicate.isnot(True),
            security_predicate,
            *date_clauses,
        )
    )

    if inc_network:
        # spec §2.2's own sketch: `UNION ALL SELECT n.fip_id, n.fetched_at
        # FROM network_fips n WHERE :inc_network = 1` -- no further
        # predicate. Network rows are "public nanopublications by
        # construction" (§5.4/D8): always `visibility='public'`, no
        # `owner_id`/`session_id`, never subject to the local security
        # predicate (there is nothing to authorize -- they're already
        # public) or to the `exclude`/date-range clauses above, which are
        # a `Fip`-column concept the network branch has no equivalent for.
        net_facets = aliased(FipFacets)
        network_stmt = select(
            NetworkFip.fip_id.label("id"),
            NetworkFip.fetched_at.label("updated_at"),
            literal("public").label("visibility"),
            literal(None, type_=String).label("owner_id"),
            literal(None, type_=String).label("session_id"),
            # Network rows have no session-ownership concept at all (§5.4/
            # D8: always public, no `owner_id`/`session_id`) -- always
            # `false()`, matching item G's local-branch column above so the
            # `UNION ALL` stays column-compatible.
            false().label("owned_session_match"),
            net_facets.fip_updated_at,
            net_facets.projection_epoch,
            epoch_subq.label("current_epoch"),
        ).outerjoin(
            net_facets,
            and_(net_facets.fip_id == NetworkFip.fip_id, net_facets.source == "network"),
        )
        combined_stmt = union_all(local_stmt, network_stmt)
    else:
        combined_stmt = local_stmt

    is_readable = _readable_individually_expr(viewer)
    members: list[PopulationMember] = []
    current_epoch = 0
    for row in db.execute(combined_stmt):
        current_epoch = int(row.current_epoch or 0)
        members.append(
            PopulationMember(
                fip_id=row.id,
                updated_at=row.updated_at,
                visibility=row.visibility,
                owner_id=row.owner_id,
                session_id=row.session_id,
                readable_individually=is_readable(
                    row.visibility, row.owner_id, bool(row.owned_session_match)
                ),
                facets_fip_updated_at=row.fip_updated_at,
                facets_projection_epoch=row.projection_epoch,
            )
        )
    return ResolvedPopulation(members=members, current_epoch=current_epoch)


def check_k_anonymity(pop: ResolvedPopulation) -> None:
    """spec §2.4: refuse (403) only when the population is non-empty, below
    the threshold, AND contains at least one FIP the viewer could not read
    individually -- an empty population is always 200/all-zero, and the
    count is echoed only when `k_hidden == 0`."""
    settings = get_settings()
    k = settings.dashboard_min_population
    if 0 < pop.count < k and pop.k_hidden > 0:
        raise DashboardError(403, {"detail": "population_too_small", "minimum": k})
