"""Read-only proxy to the FAIR nanopublication network (spec
11-nanopub-network.md §3). Pure module: no FastAPI imports, no exception
here is an HTTPException -- callers (`fipm.routers.network`,
`fipm.routers.fips`'s `POST /fips/from-network`) catch `NetworkError` and
translate `.code`/`.status_code` into the matching response.

Two injectable seams, `_post_sparql` and `_get_grlc`, are the only place an
actual HTTP request is made; tests monkeypatch these directly (never
`httpx` globally), so a test that forgets to patch one fails with a clear
"no fixture registered" error (`tests/conftest.py`'s autouse guard) instead
of attempting a real request.
"""

from __future__ import annotations

import copy
import json
import logging
import re
import time
import unicodedata
from collections import OrderedDict
from threading import Lock
from typing import Any
from urllib.parse import urlparse

import httpx

from fipm.config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# §3.1 SPARQL templates, byte-identical to the spec (verified by
# test_ac_11_05_network_safety.py against the same text quoted there).
# Placeholders (?COMMUNITY, ?INDEX, ?RESOURCES, ?QUERY, ?LIMIT) are
# substituted by plain string replacement -- never by str.format/f-string
# templating of the whole query -- so these constants stay exactly what's
# quoted in the spec.
# ---------------------------------------------------------------------------

Q0_ARTIFACT_CODE = "RAoQRAype8NkynHDgj5ofRSjFmkeXYIeybunn1EnGpyyQ"
Q0_QUERY_NAME = "fip-communities"

# Type-repo id for fip:FAIR-Implementation-Profile (spec §0 table).
FIP_TYPE_REPO = "92efd7a0ea4be4e01ec0817ccec87f975203b30addcc3166a204498ffed73b66"

Q1_SPARQL = """prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#>
prefix fip:  <https://w3id.org/fair/fip/terms/>
prefix dct:  <http://purl.org/dc/terms/>
prefix npa:  <http://purl.org/nanopub/admin/>
prefix npx:  <http://purl.org/nanopub/x/>
prefix np:   <http://www.nanopub.org/nschema#>
prefix dcat: <https://www.w3.org/ns/dcat#>
select distinct ?fip_np ?label ?index ?created ?startDate ?endDate where {
  graph npa:graph {
    ?fip_np npa:hasValidSignatureForPublicKey ?pk ;
            npx:hasNanopubType fip:FAIR-Implementation-Profile ;
            dct:created ?created ; np:hasAssertion ?a .
    filter not exists { ?x npx:invalidates ?fip_np ; npa:hasValidSignatureForPublicKey ?pk }
    filter not exists { ?y npx:supersedes  ?fip_np ; npa:hasValidSignatureForPublicKey ?pk }
  }
  graph ?a {
    ?fip a fip:FAIR-Implementation-Profile ;
         fip:declared-by ?COMMUNITY ;
         rdfs:label ?label .
    optional { ?fip fip:has-declaration-index ?index }
    optional { ?fip dcat:startDate ?startDate }
    optional { ?fip dcat:endDate   ?endDate }
  }
} order by desc(?created)"""

Q2_SPARQL = """prefix fip:  <https://w3id.org/fair/fip/terms/>
prefix np:   <http://www.nanopub.org/nschema#>
prefix npx:  <http://purl.org/nanopub/x/>
prefix dcat: <https://www.w3.org/ns/dcat#>
select distinct ?decl_np ?question ?rel ?resource ?considerations ?nochoice ?startDate ?endDate where {
  graph ?ih { ?INDEX np:hasAssertion ?ia }
  graph ?ia { ?INDEX npx:includesElement ?decl_np }
  graph ?dh { ?decl_np np:hasAssertion ?da }
  graph ?da {
    ?decl fip:refers-to-question ?question .
    optional { ?decl ?rel ?resource .
      filter(?rel in (fip:declares-current-use-of, fip:declares-planned-use-of,
                      fip:declares-planned-replacement-of, fip:declares-planned-development-of)) }
    optional { ?decl fip:considerations ?considerations }
    optional { ?decl dcat:startDate ?startDate }
    optional { ?decl dcat:endDate   ?endDate }
    optional { ?decl a fip:FIP-No-Choice-Declaration . bind(true as ?nochoice) }
  }
} order by ?question"""

Q3_SPARQL = """prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#>
prefix fip:  <https://w3id.org/fair/fip/terms/>
prefix skos: <http://www.w3.org/2004/02/skos/core#>
prefix dct:  <http://purl.org/dc/terms/>
prefix npa:  <http://purl.org/nanopub/admin/>
prefix npx:  <http://purl.org/nanopub/x/>
prefix np:   <http://www.nanopub.org/nschema#>
select distinct ?resource ?label ?comment ?match ?type ?date where {
  values ?resource { ?RESOURCES }
  graph npa:graph {
    ?np npa:hasValidSignatureForPublicKey ?pk ; np:hasAssertion ?a ; dct:created ?date .
    filter not exists { ?x npx:invalidates ?np ; npa:hasValidSignatureForPublicKey ?pk }
  }
  graph ?a {
    ?resource a fip:FAIR-Enabling-Resource ; rdfs:label ?label .
    optional { ?resource rdfs:comment ?comment }
    optional { ?resource skos:exactMatch ?match }
    optional { ?resource a ?type . filter(strstarts(str(?type), "https://w3id.org/fair/fip/terms/")) }
  }
}"""

Q4_SPARQL = """prefix rdfs:   <http://www.w3.org/2000/01/rdf-schema#>
prefix fip:    <https://w3id.org/fair/fip/terms/>
prefix npa:    <http://purl.org/nanopub/admin/>
prefix npx:    <http://purl.org/nanopub/x/>
prefix search: <http://www.openrdf.org/contrib/lucenesail#>
select distinct ?np ?label (max(?score) as ?s) where {
  graph npa:graph {
    ?np rdfs:label ?label ; npa:hasValidSignatureForPublicKey ?pk .
    filter exists { ?np npx:hasNanopubType fip:FAIR-Enabling-Resource }
    filter not exists { ?x npx:invalidates ?np ; npa:hasValidSignatureForPublicKey ?pk }
  }
  ?np search:matches [ search:query ?QUERY ; search:score ?score ]
} group by ?np ?label order by desc(?s) limit ?LIMIT"""


class NetworkError(Exception):
    """Raised with a stable spec §3.2 error code and the HTTP status it maps
    to; the router (`fipm.routers.network`, and the from-network prefill
    endpoint in `fipm.routers.fips`) turns it into `HTTPException(status_code,
    {"detail": code})`. Mirrors `fipm.migration.MigrationError`'s shape."""

    def __init__(self, code: str, status_code: int) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


# ---------------------------------------------------------------------------
# §5 SPARQL-injection guard: `communityIri` (and each Q3 resource IRI) is
# substituted as `<{iri}>` only after passing this check -- an http(s) IRI
# with none of the characters that could terminate an IRI literal or escape
# the substitution point in the query text.
# ---------------------------------------------------------------------------

_SPARQL_IRI_UNSAFE_RE = re.compile(r'[<>"\\{}|^`\s\x00-\x1f\x7f]')


def _is_safe_sparql_iri(value: str) -> bool:
    if _SPARQL_IRI_UNSAFE_RE.search(value):
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def validate_community_iri(value: str) -> str:
    """400 `invalid_community_iri` unless `value` is a safe http(s) IRI."""
    if not _is_safe_sparql_iri(value):
        raise NetworkError("invalid_community_iri", 400)
    return value


def _safe_resource_iris(values: list[str]) -> list[str]:
    """Q3's `values` block: any IRI that fails the same safety check is
    dropped from the batch rather than failing the whole request (spec §5)."""
    return [v for v in values if _is_safe_sparql_iri(v)]


# ---------------------------------------------------------------------------
# HTTP transport: streamed, size-capped, no redirects followed, no query
# string or response body ever logged.
# ---------------------------------------------------------------------------

_REQUEST_HEADERS = {"Accept": "application/sparql-results+json", "User-Agent": "FIPManager"}


def _perform_request(
    settings: Settings, method: str, url: str, data: dict[str, str] | None = None
) -> dict[str, Any]:
    timeout = httpx.Timeout(settings.network_timeout_seconds, connect=5.0)
    max_bytes = settings.network_max_response_bytes
    path = urlparse(url).path
    start = time.monotonic()
    status: int | str = "error"
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            with client.stream(method, url, data=data, headers=_REQUEST_HEADERS) as response:
                status = response.status_code
                if status >= 300:
                    # Review: a redirect (3xx, follow_redirects=False leaves
                    # it unfollowed) is a network_unavailable, never a hop
                    # to another host.
                    raise NetworkError("network_unavailable", 502)
                total = 0
                chunks: list[bytes] = []
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise NetworkError("network_response_too_large", 502)
                    chunks.append(chunk)
                body = b"".join(chunks)
    except NetworkError:
        raise
    except httpx.HTTPError as exc:
        logger.warning("network upstream call failed: %s %s (%s)", method, path, type(exc).__name__)
        raise NetworkError("network_unavailable", 502) from exc
    finally:
        elapsed = time.monotonic() - start
        logger.info(
            "network upstream call: %s %s status=%s elapsed=%.2fs", method, path, status, elapsed
        )

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise NetworkError("network_unavailable", 502) from exc


def _post_sparql(settings: Settings, repo: str, query: str) -> dict[str, Any]:
    """`POST {nanopub_query_url}/repo/{repo}`, `query=` form-encoded. One of
    the two injectable seams -- tests monkeypatch this to return a fixture's
    parsed JSON instead of making a real request."""
    url = f"{settings.nanopub_query_url}/repo/{repo}"
    return _perform_request(settings, "POST", url, data={"query": query})


def _get_grlc(settings: Settings, artifact_code: str, query_name: str) -> dict[str, Any]:
    """`GET {nanopub_query_url}/api/{artifactCode}/{queryName}`. The other
    injectable seam."""
    url = f"{settings.nanopub_query_url}/api/{artifact_code}/{query_name}"
    return _perform_request(settings, "GET", url)


def _bindings(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return raw.get("results", {}).get("bindings", [])


def _val(row: dict[str, Any], key: str) -> str | None:
    entry = row.get(key)
    return entry.get("value") if entry else None


# ---------------------------------------------------------------------------
# §3.4 cache: process-local, LRU+TTL, stale-on-failure.
# ---------------------------------------------------------------------------

_CACHE_MAX_ENTRIES = 256
_TRANSIENT_ERROR_CODES = {"network_unavailable", "network_response_too_large"}

_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_cache_lock = Lock()


def reset_network_cache() -> None:
    """Test-only helper: clear the cache between tests (the `fipm.auth.
    reset_rate_limits` pattern)."""
    with _cache_lock:
        _cache.clear()


def _cached_call(key: str, ttl: float, fetch: Any) -> tuple[Any, float, bool]:
    """Returns `(value, cached_at, stale)`. A fresh cache hit never calls
    `fetch`. A miss/expired entry calls `fetch()`; if that raises a
    *transient* `NetworkError` (network_unavailable /
    network_response_too_large) and a cache entry exists -- even an expired
    one -- it is served with `stale=True` rather than propagating the
    error. Any other exception (including a non-transient `NetworkError`,
    e.g. `network_fip_not_found`) always propagates.

    Review finding 9: every value handed to a caller is a `copy.deepcopy` of
    what's stored, never the stored object itself -- callers downstream
    (e.g. `fipm.routers.network._resolve_in_catalogue`, which mutates each
    resource dict in place to add `inCatalogue`) must never be able to
    corrupt the cached entry that a *later*, unrelated request would then be
    served."""
    now = time.time()
    with _cache_lock:
        entry = _cache.get(key)
        if entry is not None:
            cached_at, value = entry
            if now - cached_at <= ttl:
                _cache.move_to_end(key)
                return copy.deepcopy(value), cached_at, False

    try:
        value = fetch()
    except NetworkError as exc:
        if exc.code not in _TRANSIENT_ERROR_CODES:
            raise
        with _cache_lock:
            entry = _cache.get(key)
        if entry is not None:
            cached_at, stale_value = entry
            return copy.deepcopy(stale_value), cached_at, True
        raise

    cached_at = time.time()
    with _cache_lock:
        _cache[key] = (cached_at, value)
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)
    return copy.deepcopy(value), cached_at, False


# ---------------------------------------------------------------------------
# Q0: communities with at least one FIP.
# ---------------------------------------------------------------------------


def _dedupe_communities(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """spec §3.1: the raw list has duplicate `community` IRIs (same
    community, two labels from two nanopub versions) -- dedupe keeping the
    longest label and the maximum fip_count."""
    best: dict[str, dict[str, Any]] = {}
    for row in bindings:
        iri = _val(row, "community")
        label = _val(row, "community_label") or ""
        fip_count = int(_val(row, "fip_count") or 0)
        if iri is None:
            continue
        current = best.get(iri)
        if current is None:
            best[iri] = {"iri": iri, "label": label, "fipCount": fip_count}
            continue
        if len(label) > len(current["label"]):
            current["label"] = label
        if fip_count > current["fipCount"]:
            current["fipCount"] = fip_count
    return sorted(best.values(), key=lambda item: item["label"].casefold())


def get_fip_communities(settings: Settings) -> tuple[list[dict[str, Any]], float, bool]:
    """Q0, deduped (§3.1). Returns `(items, cached_at_epoch_seconds, stale)`;
    `items` is `[{"iri","label","fipCount"}]`, unfiltered/unpaginated --
    that's the router's job (`fipm.routers.network`), matched-in-process per
    §3.2 so `q` never reaches SPARQL."""

    def fetch() -> list[dict[str, Any]]:
        raw = _get_grlc(settings, Q0_ARTIFACT_CODE, Q0_QUERY_NAME)
        return _dedupe_communities(_bindings(raw))

    return _cached_call("communities", settings.network_cache_ttl_seconds, fetch)


# ---------------------------------------------------------------------------
# Q1 + Q2 + Q3: one community's newest FIP, its declarations, its resources.
# ---------------------------------------------------------------------------

_REL_STATUS = {
    "https://w3id.org/fair/fip/terms/declares-current-use-of": "current",
    "https://w3id.org/fair/fip/terms/declares-planned-use-of": "planned",
    "https://w3id.org/fair/fip/terms/declares-planned-replacement-of": "planned-replacement",
    "https://w3id.org/fair/fip/terms/declares-planned-development-of": "planned-development",
}
# Preference order when a declaration carries more than one declares-*
# triple (e.g. a planned-replacement plus its successor's declares-planned-
# use-of): the more specific status wins.
_REL_PRIORITY = (
    "https://w3id.org/fair/fip/terms/declares-planned-replacement-of",
    "https://w3id.org/fair/fip/terms/declares-current-use-of",
    "https://w3id.org/fair/fip/terms/declares-planned-development-of",
    "https://w3id.org/fair/fip/terms/declares-planned-use-of",
)

_QUESTION_PREFIX = "https://w3id.org/fair/fip/terms/FIP-Question-"


def _group_declarations(bindings: list[dict[str, Any]]) -> OrderedDict[str, dict[str, Any]]:
    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for row in bindings:
        decl_np = _val(row, "decl_np")
        if decl_np is None:
            continue
        group = groups.setdefault(
            decl_np,
            {
                "question": None,
                "considerations": [],
                "nochoice": False,
                "resource_by_rel": {},
                "startDate": None,
                "endDate": None,
            },
        )
        question = _val(row, "question")
        if question is not None:
            group["question"] = question
        if _val(row, "nochoice") == "true":
            group["nochoice"] = True
        considerations = _val(row, "considerations")
        if considerations is not None and considerations not in group["considerations"]:
            group["considerations"].append(considerations)
        rel = _val(row, "rel")
        resource = _val(row, "resource")
        if rel is not None and resource is not None:
            group["resource_by_rel"][rel] = resource
        start_date = _val(row, "startDate")
        if start_date is not None:
            group["startDate"] = start_date
        end_date = _val(row, "endDate")
        if end_date is not None:
            group["endDate"] = end_date
    return groups


def _status_and_resource(group: dict[str, Any]) -> tuple[str | None, str | None]:
    if group["nochoice"]:
        return "none", None
    resource_by_rel = group["resource_by_rel"]
    for rel in _REL_PRIORITY:
        if rel in resource_by_rel:
            return _REL_STATUS[rel], resource_by_rel[rel]
    return None, None


def _group_resources(bindings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """spec §3.1 Q3 post-processing: group by `?resource`; keep the label/
    comment/match from the row with the maximum `?date`; union all `?type`
    values. Never filters by `npx:supersedes` (only `npx:invalidates`,
    already baked into the query itself)."""
    by_resource: dict[str, dict[str, Any]] = {}
    for row in bindings:
        iri = _val(row, "resource")
        if iri is None:
            continue
        entry = by_resource.setdefault(
            iri,
            {
                "iri": iri,
                "label": None,
                "comment": None,
                "homepage": None,
                "types": [],
                "_date": "",
            },
        )
        row_type = _val(row, "type")
        if row_type is not None and row_type not in entry["types"]:
            entry["types"].append(row_type)
        date = _val(row, "date") or ""
        if date >= entry["_date"]:
            entry["_date"] = date
            entry["label"] = _val(row, "label")
            entry["comment"] = _val(row, "comment")
            entry["homepage"] = _val(row, "match")
    for entry in by_resource.values():
        del entry["_date"]
    return by_resource


def _resolve_fer_type_key(
    fer_types: dict[str, dict[str, Any]], type_iris: list[str], question_local: str | None
) -> str | None:
    """spec §3.3: invert `fer-types.json`'s `iri` field over the resource's
    `?type` values; a resource carrying several resolves to the one whose
    `principle` matches the question individual's own principle (`"F1-MD"`
    -> `"F1"`, `"A1.2-D"` -> `"A1.2"`, ...); failing that, the first key in
    `fer-types.json`'s own order; failing that, `None`."""
    iri_to_key = {t["iri"]: key for key, t in fer_types.items() if t.get("iri")}
    candidates = [iri_to_key[iri] for iri in type_iris if iri in iri_to_key]
    if not candidates:
        return None
    if question_local:
        principle = question_local
        for suffix in ("-MD", "-D"):
            if principle.endswith(suffix):
                principle = principle[: -len(suffix)]
                break
        for key in candidates:
            if fer_types[key].get("principle") == principle:
                return key
    order = list(fer_types.keys())
    candidates.sort(key=lambda key: order.index(key) if key in order else len(order))
    return candidates[0]


def get_community_fip(settings: Settings, community_iri: str) -> tuple[dict[str, Any], float, bool]:
    """Q1 (newest FIP + other versions) -> Q2 (its declarations) -> Q3 (their
    resources), assembled into the spec §3.3 shape (minus `inCatalogue`,
    which needs the `fers` DB table and is added by the router). Returns
    `(payload, cached_at_epoch_seconds, stale)`.

    404 `network_fip_not_found` and 400 `invalid_community_iri` are raised
    immediately -- never cached, never treated as a transient failure the
    stale-cache fallback would paper over."""
    from fipm.fer_types import get_fer_types
    from fipm.rdf import KNOWN_QUESTION_INDIVIDUALS_ORDER, question_id_from_individual

    validate_community_iri(community_iri)

    def fetch() -> dict[str, Any]:
        q1_query = Q1_SPARQL.replace("?COMMUNITY", f"<{community_iri}>")
        q1_rows = _bindings(_post_sparql(settings, f"type/{FIP_TYPE_REPO}", q1_query))
        if not q1_rows:
            raise NetworkError("network_fip_not_found", 404)

        current = q1_rows[0]
        other_versions = [
            {
                "nanopubIri": _val(row, "fip_np"),
                "label": _val(row, "label"),
                "created": _val(row, "created"),
            }
            for row in q1_rows[1:]
        ]

        index_iri = _val(current, "index")
        decl_groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
        if index_iri:
            # Review finding 4: ?index comes back from Q1 (upstream data,
            # not a caller-supplied value) but is substituted verbatim into
            # Q2's query text -- the same injection surface `_is_safe_sparql_
            # iri` already guards for `?COMMUNITY`/`?RESOURCES`. A malformed
            # or hostile upstream response is a network fault, not a 500.
            if not _is_safe_sparql_iri(index_iri):
                raise NetworkError("network_unavailable", 502)
            q2_query = Q2_SPARQL.replace("?INDEX", f"<{index_iri}>")
            q2_rows = _bindings(_post_sparql(settings, "full", q2_query))
            decl_groups = _group_declarations(q2_rows)

        resource_iris = sorted(
            {
                resource
                for group in decl_groups.values()
                for resource in group["resource_by_rel"].values()
            }
        )
        resources: dict[str, dict[str, Any]] = {}
        safe_resource_iris = _safe_resource_iris(resource_iris)
        for i in range(0, len(safe_resource_iris), 100):
            batch = safe_resource_iris[i : i + 100]
            values_block = " ".join(f"<{iri}>" for iri in batch)
            q3_query = Q3_SPARQL.replace("?RESOURCES", values_block)
            q3_rows = _bindings(_post_sparql(settings, "full", q3_query))
            resources.update(_group_resources(q3_rows))

        fer_types = get_fer_types(settings)

        questions_by_local: dict[str, dict[str, Any]] = {
            local: {
                "questionId": question_id_from_individual(_QUESTION_PREFIX + local),
                "questionIri": _QUESTION_PREFIX + local,
                "declarations": [],
            }
            for local in KNOWN_QUESTION_INDIVIDUALS_ORDER
        }
        unmapped_by_iri: OrderedDict[str, dict[str, Any]] = OrderedDict()

        for decl_np, group in decl_groups.items():
            question_iri = group["question"]
            question_local = (
                question_iri[len(_QUESTION_PREFIX) :]
                if question_iri and question_iri.startswith(_QUESTION_PREFIX)
                else None
            )
            status, resource_iri = _status_and_resource(group)
            resource_obj: dict[str, Any] | None = None
            if resource_iri is not None:
                res = resources.get(resource_iri)
                type_iris = res["types"] if res else []
                resource_obj = {
                    "iri": resource_iri,
                    "label": res["label"] if res else None,
                    "comment": res["comment"] if res else None,
                    "homepage": res["homepage"] if res else None,
                    "types": type_iris,
                    "ferTypeKey": _resolve_fer_type_key(fer_types, type_iris, question_local),
                }
            considerations = "; ".join(group["considerations"]) if group["considerations"] else None
            declaration = {
                "nanopubIri": decl_np,
                "status": status,
                "resource": resource_obj,
                "considerations": considerations,
                "startDate": group["startDate"],
                "endDate": group["endDate"],
            }
            if question_local is not None and question_local in questions_by_local:
                questions_by_local[question_local]["declarations"].append(declaration)
            else:
                key = question_iri or "?"
                entry = unmapped_by_iri.setdefault(
                    key, {"questionIri": question_iri, "declarations": []}
                )
                entry["declarations"].append(declaration)

        return {
            "community": {"iri": community_iri, "label": None},
            "fip": {
                "nanopubIri": _val(current, "fip_np"),
                "label": _val(current, "label"),
                "indexIri": index_iri,
                "created": _val(current, "created"),
                "startDate": _val(current, "startDate"),
                "endDate": _val(current, "endDate"),
                "otherVersions": other_versions,
            },
            "questions": [questions_by_local[local] for local in KNOWN_QUESTION_INDIVIDUALS_ORDER],
            "unmapped": list(unmapped_by_iri.values()),
        }

    return _cached_call(f"fips:{community_iri}", settings.network_cache_ttl_seconds, fetch)


# ---------------------------------------------------------------------------
# Q4: FER full-text search (v2 roadmap, §3.2/§7 Q8 -- shipped, not wired
# into the FER picker for CONFOA).
# ---------------------------------------------------------------------------

_QUERY_UNSAFE_RE = re.compile(r'["\\\x00-\x1f\x7f]')


def _sanitise_fer_query(q: str) -> str:
    """§5: length-capped at 100 characters, `"`/`\\`/control characters
    stripped, before it reaches Q4's Lucene `search:query` binding."""
    q = unicodedata.normalize("NFC", q)[:100]
    return _QUERY_UNSAFE_RE.sub("", q)


def search_fers(settings: Settings, q: str, limit: int) -> tuple[list[dict[str, Any]], float, bool]:
    """Q4, then Q3 to enrich each hit's comment/homepage/types where
    available (a Q4 hit's own `label` is always used regardless -- Q3 may
    legitimately return nothing for a resource IRI Q3's query shape doesn't
    match)."""
    from fipm.fer_types import get_fer_types

    safe_q = _sanitise_fer_query(q)
    safe_limit = max(1, min(int(limit), 200))

    def fetch() -> list[dict[str, Any]]:
        # Review finding 11: ensure_ascii=False -- a non-ASCII query
        # (pt-BR/es text, e.g. "ômicos") must reach the SPARQL text index as
        # the literal UTF-8 characters, not a \uXXXX escape a Lucene
        # tokenizer may not decode the way the caller expects.
        query = Q4_SPARQL.replace("?QUERY", json.dumps(safe_q, ensure_ascii=False)).replace(
            "?LIMIT", str(safe_limit)
        )
        rows = _bindings(_post_sparql(settings, "text", query))
        hits = [
            {"iri": _val(row, "np"), "label": _val(row, "label")}
            for row in rows
            if _val(row, "np") is not None
        ]
        iris = [h["iri"] for h in hits]
        resources: dict[str, dict[str, Any]] = {}
        safe_iris = _safe_resource_iris(iris)
        for i in range(0, len(safe_iris), 100):
            batch = safe_iris[i : i + 100]
            values_block = " ".join(f"<{iri}>" for iri in batch)
            q3_query = Q3_SPARQL.replace("?RESOURCES", values_block)
            q3_rows = _bindings(_post_sparql(settings, "full", q3_query))
            resources.update(_group_resources(q3_rows))

        fer_types = get_fer_types(settings)
        items: list[dict[str, Any]] = []
        for hit in hits:
            res = resources.get(hit["iri"])
            type_iris = res["types"] if res else []
            items.append(
                {
                    "iri": hit["iri"],
                    "label": (res["label"] if res else None) or hit["label"],
                    "comment": res["comment"] if res else None,
                    "homepage": res["homepage"] if res else None,
                    "types": type_iris,
                    "ferTypeKey": _resolve_fer_type_key(fer_types, type_iris, None),
                }
            )
        return items

    return _cached_call(f"fers:{safe_q}:{safe_limit}", settings.network_cache_ttl_seconds, fetch)
