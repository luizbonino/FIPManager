"""Unsigned nanopublication bundle export (spec 11-nanopub-network.md §2).

One FIP Manager FIP becomes N + 3 nanopublications (community, one per
surviving declaration, a declaration index, the FIP itself) -- the Wizard's
own decomposition (spec §0.2), reproduced here as plain TriG text (no
`nanopub` dependency, no signing, no network write -- §1's hard "no"s).

Determinism (builder brief A, acceptance criterion 5): every graph's triples
are rendered as sorted, individually-formatted Turtle lines before being
joined, so two calls with the same input and the same `now` produce
byte-identical output regardless of set/dict iteration order (which, for
`str`-keyed structures, is affected by hash randomisation across
processes).
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from rdflib import RDF, RDFS, XSD, Literal, Namespace, URIRef
from sqlalchemy.orm import Session

from fipm.config import Settings
from fipm.exporters import fip_url
from fipm.models import Fer, Fip, KnowledgeModel
from fipm.rdf import (
    FAIR,
    FIP,
    KNOWN_PRINCIPLE_IDS,
    LICENSE_IRI_MAP,
    ORCID_RE,
    STATUS_AVAILABILITY_CLASS,
    STATUS_PREDICATE,
    _fer_type_class,
    _free_text_hash,
    _is_http_iri,
    _none_declaration_text,
    _question_individual_local,
    _questions_by_id,
    _resolve_lang_pair,
)

NP = Namespace("http://www.nanopub.org/nschema#")
NPX = Namespace("http://purl.org/nanopub/x/")
DCTERMS = Namespace("http://purl.org/dc/terms/")
PROV = Namespace("http://www.w3.org/ns/prov#")
DC11 = Namespace("http://purl.org/dc/elements/1.1/")  # the index nanopub's title, spec §0.2 note 3

_TEMP_PREFIX = "http://purl.org/nanopub/temp/fipm"

# spec §2.4: the network's own decomposition has at most a handful of
# declarations per FIP; nanopub-py's own MAX_NP_PER_INDEX (1100, §0) is the
# hard ceiling a `npx:NanopubIndex` may not exceed. This is a guard, not a
# real case -- but a malicious/buggy caller building a FIP with thousands of
# declarations must get a clean 413, not a bundle a later signing step
# would reject anyway.
MAX_NP_PER_INDEX = 1100


class NanopubBundleError(Exception):
    """Raised with a stable error code and the HTTP status it maps to;
    mirrors `fipm.network.NetworkError`'s shape. The three
    `/export/nanopubs*` endpoints in `fipm.routers.fips` catch this and
    turn it into `HTTPException(status_code, {"detail": code})`."""

    def __init__(self, code: str, status_code: int) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


# ---------------------------------------------------------------------------
# Review finding 2: the hand-rolled TriG serialiser below never escapes an
# IRI -- `_format_term` emits it as `f"<{term}>"` verbatim -- so any IRI
# reaching it must first be proven free of every character RFC 3987 forbids
# inside a Turtle/TriG IRIREF (`<>"{}|^\``, ASCII whitespace, and C0/DEL
# control characters). `_format_term` itself enforces this as the last line
# of defence (raising rather than ever emitting one of these characters
# raw); `build_bundle` additionally gates known untrusted inputs (a
# declaration's ferId/successorFerId, a community link) *before* building
# any triple from them, so the common case never reaches the raise at all
# and can be turned into a clean `skipped`/dropped-triple outcome instead of
# a hard failure.
# ---------------------------------------------------------------------------

_UNSAFE_IRIREF_CHARS_RE = re.compile(r'[\x00-\x20<>"{}|^`\\]')


def _is_safe_iriref(value: str) -> bool:
    return not _UNSAFE_IRIREF_CHARS_RE.search(value)


# ---------------------------------------------------------------------------
# One nanopub: four named graphs (Head/assertion/provenance/pubinfo) under
# its own temp base (spec §2.2). Triples are kept as plain sets and
# serialised by hand (not via rdflib's own TriG writer) so output order is
# fully under our control -- see module docstring.
# ---------------------------------------------------------------------------


class _Nanopub:
    def __init__(self, fip_id: str, n: int, role: str) -> None:
        self.n = n
        self.role = role
        self.base = f"{_TEMP_PREFIX}/{fip_id}/{n}/"
        self.uri = URIRef(self.base)
        self.head_uri = URIRef(self.base + "Head")
        self.assertion_uri = URIRef(self.base + "assertion")
        self.provenance_uri = URIRef(self.base + "provenance")
        self.pubinfo_uri = URIRef(self.base + "pubinfo")
        self.head: set[tuple[Any, Any, Any]] = set()
        self.assertion: set[tuple[Any, Any, Any]] = set()
        self.provenance: set[tuple[Any, Any, Any]] = set()
        self.pubinfo: set[tuple[Any, Any, Any]] = set()
        self.head.add((self.uri, RDF.type, NP.Nanopublication))
        self.head.add((self.uri, NP.hasAssertion, self.assertion_uri))
        self.head.add((self.uri, NP.hasProvenance, self.provenance_uri))
        self.head.add((self.uri, NP.hasPublicationInfo, self.pubinfo_uri))

    def concept(self, local: str) -> URIRef:
        return URIRef(self.base + local)

    def a(self, s: Any, p: Any, o: Any) -> None:
        self.assertion.add((s, p, o))

    def p(self, s: Any, p: Any, o: Any) -> None:
        self.provenance.add((s, p, o))

    def i(self, s: Any, p: Any, o: Any) -> None:
        self.pubinfo.add((s, p, o))

    def to_trig(self) -> str:
        graphs = (
            (self.head_uri, self.head),
            (self.assertion_uri, self.assertion),
            (self.provenance_uri, self.provenance),
            (self.pubinfo_uri, self.pubinfo),
        )
        return "\n".join(_format_graph(uri, triples) for uri, triples in graphs) + "\n"


def _format_literal(term: Literal) -> str:
    value = str(term)
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    text = f'"{escaped}"'
    if term.language:
        text += f"@{term.language}"
    elif (
        term.datatype is not None
        and str(term.datatype) != "http://www.w3.org/2001/XMLSchema#string"
    ):
        text += f"^^<{term.datatype}>"
    return text


def _format_term(term: Any) -> str:
    if isinstance(term, Literal):
        return _format_literal(term)
    iri = str(term)
    if not _is_safe_iriref(iri):
        # Last-resort backstop (review finding 2): every known untrusted
        # source of an IRI is gated *before* it reaches here, so hitting
        # this in practice means a gate was missed -- fail loudly rather
        # than ever emit an unescaped, injectable IRIREF.
        raise ValueError(f"unsafe characters in IRI, refusing to emit: {iri!r}")
    return f"<{iri}>"


def _format_graph(graph_uri: URIRef, triples: set[tuple[Any, Any, Any]]) -> str:
    lines = sorted(
        f"  {_format_term(s)} {_format_term(p)} {_format_term(o)} ." for s, p, o in triples
    )
    body = "\n".join(lines)
    return f"<{graph_uri}> {{\n{body}\n}}\n"


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# FER resolution inside a declaration's assertion graph (spec §2.4.1).
# ---------------------------------------------------------------------------


def _fer_reference(
    nanopub: _Nanopub,
    db: Session,
    settings: Settings,
    fipmx: Namespace,
    fer_id: str | None,
    free_text: str | None,
    fer_type_key: str | None,
    language: str,
    status: str | None,
) -> tuple[URIRef | None, str | None]:
    """Returns `(iri, origin)`: `origin` is `"network"` | `"catalogue"` |
    `"free-text"` | `None`, recorded in `index.json` for the caller's
    reporting. Case 1 (a `source="network"` catalogue row) links the IRI
    verbatim with **no** description block -- the network already describes
    it. Case 2 (any other catalogue row) and case 3 (free text) both emit
    `<iri> a fip:FAIR-Enabling-Resource, <type>, <availability>; rdfs:label
    "..."@lang .` into the same declaration's assertion graph."""
    availability_iri = STATUS_AVAILABILITY_CLASS.get(status) if status else None

    if fer_id:
        fer_iri = URIRef(fer_id)
        fer_row = db.get(Fer, fer_id)
        if fer_row is not None and fer_row.source == "network":
            return fer_iri, "network"

        nanopub.a(fer_iri, RDF.type, FIP["FAIR-Enabling-Resource"])
        type_iri = None
        if fer_row is not None:
            type_iri = _fer_type_class(settings, fer_row.type) or _fer_type_class(
                settings, fer_type_key
            )
            label_pair = _resolve_lang_pair(fer_row.label, language, settings.default_language)
            if label_pair:
                text, tag = label_pair
                nanopub.a(fer_iri, RDFS.label, Literal(text, lang=tag))
        else:
            type_iri = _fer_type_class(settings, fer_type_key)
        if type_iri is not None:
            nanopub.a(fer_iri, RDF.type, type_iri)
        if availability_iri is not None:
            nanopub.a(fer_iri, RDF.type, availability_iri)
        return fer_iri, "catalogue"

    if free_text:
        fer_iri = URIRef(f"{settings.base_url}/fers/text/{_free_text_hash(free_text)}")
        nanopub.a(fer_iri, RDF.type, FIP["FAIR-Enabling-Resource"])
        type_iri = _fer_type_class(settings, fer_type_key)
        if type_iri is not None:
            nanopub.a(fer_iri, RDF.type, type_iri)
        if availability_iri is not None:
            nanopub.a(fer_iri, RDF.type, availability_iri)
        nanopub.a(fer_iri, RDFS.label, Literal(free_text, lang=language))
        nanopub.a(fer_iri, fipmx["free-text"], Literal(True, datatype=XSD.boolean))
        return fer_iri, "free-text"

    return None, None


# ---------------------------------------------------------------------------
# The bundle.
# ---------------------------------------------------------------------------


@dataclass
class NanopubBundle:
    files: list[tuple[str, str]]
    index: dict[str, Any]
    manifest: str
    _now: datetime = field(repr=False)

    def zip_bytes(self) -> bytes:
        date_time = self._now.timetuple()[:6]
        fip_id = self.index["fip"]["id"]
        root = f"{fip_id}-nanopubs"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            entries = [
                ("index.json", json.dumps(self.index, indent=2)),
                ("MANIFEST.md", self.manifest),
                *[(path, text) for path, text in self.files],
            ]
            for name, content in entries:
                info = zipfile.ZipInfo(f"{root}/{name}", date_time=date_time)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                zf.writestr(info, content)
        return buf.getvalue()


_MISSING_PREREQUISITES = [
    {
        "what": "orcid",
        "detail": (
            "No ORCID iD is recorded for this FIP's author. Every network nanopub's "
            "provenance graph names a person by ORCID; the bundle currently attributes "
            "the assertion to the FIP Manager agent IRI instead."
        ),
    },
    {
        "what": "signing-key",
        "detail": (
            "An RSA 2048 keypair, generated by `np setup` (nanopub-py) or "
            '`MakeKeys.make("~/.nanopub/id", SignatureAlgorithm.RSA)` (nanopub-java). '
            "FIP Manager holds no key material."
        ),
    },
    {
        "what": "key-declaration",
        "detail": (
            "A published nanopub linking that public key to the ORCID iD "
            "(`np setup` offers to publish it)."
        ),
    },
    {
        "what": "signing-tool",
        "detail": (
            "nanopub-py >= (whatever is current) or the nanopub-java `np` CLI. "
            "Neither is a FIP Manager dependency."
        ),
    },
    {
        "what": "cross-reference-rewrite",
        "detail": (
            "Apply `rewrites` in `signingOrder`; nanopub-py rewrites only each "
            "nanopub's own temp namespace."
        ),
    },
    {
        "what": "publication-decision",
        "detail": (
            "Publishing is irreversible in practice: a nanopub can be retracted but "
            "not deleted. See MANIFEST.md."
        ),
    },
]


def build_bundle(db: Session, fip: Fip, settings: Settings, now: datetime) -> NanopubBundle:
    # Review finding 5: second precision, no sub-second jitter between the
    # literal below and anything a caller derives from the same `now`
    # (index.json's own `generatedAt`, the zip's file timestamps).
    now = now.replace(microsecond=0)
    language = fip.language
    default_language = settings.default_language
    fipmx = Namespace(settings.ext_ns)
    km = db.get(KnowledgeModel, (fip.questionnaire_id, fip.questionnaire_version))
    questions_by_id = _questions_by_id(km)
    community = fip.community or {}
    include_derived_from = fip.visibility in ("public", "link")
    # normalize=False: rdflib's Literal would otherwise round-trip the value
    # through its own datetime parser/formatter, which is unnecessary here
    # (the string is already exactly the lexical form spec §2.4 wants) and
    # risks silently changing the printed form on a future rdflib version.
    created_literal = Literal(_iso_utc(now), datatype=XSD.dateTime, normalize=False)
    license_iri = LICENSE_IRI_MAP.get(fip.license)
    fip_url_str = fip_url(fip, settings)

    def add_common_pubinfo(nanopub: _Nanopub) -> None:
        nanopub.i(nanopub.uri, DCTERMS.created, created_literal)
        nanopub.i(nanopub.uri, DCTERMS.creator, URIRef(settings.base_url))
        if license_iri:
            nanopub.i(nanopub.uri, DCTERMS.license, URIRef(license_iri))
        if include_derived_from:
            nanopub.i(nanopub.uri, PROV.wasDerivedFrom, URIRef(fip_url_str))

    # -- nanopub 1: community ---------------------------------------------
    n1 = _Nanopub(fip.id, 1, "community")
    community_concept = n1.concept("community")
    n1.a(community_concept, RDF.type, FIP["FAIR-Implementation-Community"])
    label_text = community.get("name") or fip.title or f"FIP {fip.id}"
    n1.a(community_concept, RDFS.label, Literal(label_text, lang=language))
    # Review finding 7 / spec §7 Q5: also emit an untagged rdfs:label --
    # the network's own FIP nanopubs use untagged literals, so a consumer
    # that only ever looks for one keeps working even though ours is
    # (more informatively) also language-tagged.
    n1.a(community_concept, RDFS.label, Literal(label_text))
    description = community.get("description")
    if description:
        n1.a(community_concept, RDFS.comment, Literal(description, lang=language))
    domain = community.get("domain")
    if domain:
        if _is_http_iri(domain):
            n1.a(community_concept, FIP["has-research-domain"], URIRef(domain))
        else:
            n1.a(community_concept, DCTERMS.subject, Literal(domain, lang=language))
    data_steward = community.get("dataSteward") or {}
    orcid = data_steward.get("orcid")
    steward_name = data_steward.get("name")
    if orcid and ORCID_RE.match(orcid):
        n1.a(community_concept, FIP["has-data-steward"], URIRef(f"https://orcid.org/{orcid}"))
    elif steward_name:
        steward_iri = n1.concept("data-steward")
        n1.a(community_concept, FIP["has-data-steward"], steward_iri)
        n1.a(steward_iri, RDF.type, URIRef("http://xmlns.com/foaf/0.1/Person"))
        n1.a(steward_iri, RDFS.label, Literal(steward_name))
        n1.a(steward_iri, URIRef("http://xmlns.com/foaf/0.1/name"), Literal(steward_name))
    for link in community.get("links") or []:
        # Review finding 2(b): `community.links` is free-form,
        # facilitator-authored text with no schema-level IRI validation
        # (unlike ferId/successorFerId) -- gate it here, the same rule
        # `fip:has-research-domain` already uses (`_is_http_iri`) plus the
        # IRIREF character rule. A link that fails either check is silently
        # dropped rather than emitted.
        if _is_http_iri(link) and _is_safe_iriref(link):
            n1.a(community_concept, RDFS.seeAlso, URIRef(link))
    n1.p(n1.assertion_uri, PROV.wasAttributedTo, URIRef(settings.base_url))
    # Review finding 1: `npx:introduces` is a pubinfo-graph triple whose
    # SUBJECT is the nanopub itself (`this:`), not the pubinfo graph's own
    # IRI -- spec §0.2's quoted TriG: `this: ... npx:introduces sub:X`.
    n1.i(n1.uri, NPX.introduces, community_concept)
    add_common_pubinfo(n1)

    # -- nanopubs 2..N+1: declarations -------------------------------------
    if km is not None:
        question_order = [
            q["id"]
            for section in (km.content or {}).get("sections", [])
            for q in section.get("questions", [])
        ]
    else:
        question_order = [a.get("questionId") for a in (fip.answers or []) if a.get("questionId")]

    answers_by_qid = {a["questionId"]: a for a in (fip.answers or []) if a.get("questionId")}

    decl_nanopubs: list[_Nanopub] = []
    decl_meta: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    not_applicable_ids: list[str] = []
    answer_comment_ids: list[str] = []
    dmp_evidence_entries: list[dict[str, Any]] = []
    n = 1

    for qid in question_order:
        answer = answers_by_qid.get(qid)
        if answer is None:
            continue
        question_meta = questions_by_id.get(qid, {})
        if question_meta.get("hidden") is True:
            continue

        declarations = answer.get("declarations") or []
        for idx, decl in enumerate(declarations):
            if decl.get("dmpEvidence"):
                dmp_evidence_entries.append({"questionId": qid, "declarationIndex": idx})

        if answer.get("notApplicable"):
            not_applicable_ids.append(qid)
            continue

        q_local = _question_individual_local(qid)
        if q_local is None:
            for idx in range(len(declarations)):
                skipped.append(
                    {"questionId": qid, "declarationIndex": idx, "reason": "no_question_individual"}
                )
            continue

        comment = answer.get("comment")
        attach_comment_to_single = comment if len(declarations) == 1 else None
        if comment and len(declarations) != 1:
            answer_comment_ids.append(qid)

        principle = question_meta.get("principle")
        fer_type_key = question_meta.get("ferType")

        for idx, decl in enumerate(declarations):
            status = decl.get("status")
            # Review finding 2(a): ferId/successorFerId are only ever
            # embedded as IRIs (via _fer_reference) when status != "none" --
            # gate them here, before a _Nanopub is even created, so an
            # unsafe value never gets the chance to reach the hand-rolled
            # serialiser at all. schemas._validate_fer_iri already blocks
            # this at write time for anything written through the API; this
            # is the defence for data that predates that gate (or bypassed
            # it, e.g. a direct DB write).
            if status != "none":
                unsafe_fer_id = decl.get("ferId") and not _is_safe_iriref(decl["ferId"])
                unsafe_successor_id = decl.get("successorFerId") and not _is_safe_iriref(
                    decl["successorFerId"]
                )
                if unsafe_fer_id or unsafe_successor_id:
                    skipped.append(
                        {"questionId": qid, "declarationIndex": idx, "reason": "invalid_iri"}
                    )
                    continue

            n += 1
            role = f"decl-{q_local}-{idx}"
            nanopub = _Nanopub(fip.id, n, role)
            decl_concept = nanopub.concept("declaration")

            if status == "none":
                nanopub.a(decl_concept, RDF.type, FIP["FIP-No-Choice-Declaration"])
            else:
                nanopub.a(decl_concept, RDF.type, FIP["FIP-Declaration"])
            nanopub.a(decl_concept, FIP["declared-by"], community_concept)
            nanopub.a(decl_concept, FIP["refers-to-question"], FIP[f"FIP-Question-{q_local}"])
            if principle and principle in KNOWN_PRINCIPLE_IDS:
                nanopub.a(decl_concept, FIP["refers-to-principle"], FAIR[principle])

            resource_iri: URIRef | None = None
            resource_origin: str | None = None
            if status == "none":
                none_text = _none_declaration_text(db, decl, language, default_language)
                if none_text:
                    nanopub.a(decl_concept, FIP.considerations, Literal(none_text, lang=language))
            else:
                resource_iri, resource_origin = _fer_reference(
                    nanopub,
                    db,
                    settings,
                    fipmx,
                    decl.get("ferId"),
                    decl.get("ferFreeText"),
                    fer_type_key,
                    language,
                    status,
                )
                predicate = STATUS_PREDICATE.get(status) if status else None
                if predicate is not None and resource_iri is not None:
                    nanopub.a(decl_concept, predicate, resource_iri)

                if status == "planned-replacement":
                    successor_fer_id = decl.get("successorFerId")
                    successor_free_text = decl.get("successorFreeText")
                    if successor_fer_id or successor_free_text:
                        successor_iri, _successor_origin = _fer_reference(
                            nanopub,
                            db,
                            settings,
                            fipmx,
                            successor_fer_id,
                            successor_free_text,
                            fer_type_key,
                            language,
                            "current",
                        )
                        if successor_iri is not None:
                            nanopub.a(decl_concept, FIP["declares-planned-use-of"], successor_iri)

            for note_lang, note_text in (decl.get("note") or {}).items():
                if note_text:
                    nanopub.a(decl_concept, FIP.considerations, Literal(note_text, lang=note_lang))
            if attach_comment_to_single:
                nanopub.a(
                    decl_concept,
                    FIP.considerations,
                    Literal(attach_comment_to_single, lang=language),
                )

            nanopub.p(nanopub.assertion_uri, PROV.wasAttributedTo, URIRef(settings.base_url))
            add_common_pubinfo(nanopub)

            decl_nanopubs.append(nanopub)
            decl_meta.append(
                {
                    "n": n,
                    "questionId": qid,
                    "questionIri": str(FIP[f"FIP-Question-{q_local}"]),
                    "declarationIndex": idx,
                    "status": status,
                    "resourceIri": str(resource_iri) if resource_iri is not None else None,
                    "resourceOrigin": resource_origin,
                }
            )

    declaration_count = len(decl_nanopubs)
    # Review finding 6 / spec §2.4: a `npx:NanopubIndex` may include at most
    # nanopub-py's own MAX_NP_PER_INDEX elements.
    if declaration_count > MAX_NP_PER_INDEX:
        raise NanopubBundleError("too_many_declarations", 413)
    index_n = n + 1
    fip_n = n + 2

    # -- nanopub N+2: declaration index -------------------------------------
    n_index = _Nanopub(fip.id, index_n, "index")
    for decl_np in decl_nanopubs:
        n_index.a(n_index.uri, NPX.includesElement, decl_np.uri)
    n_index.p(n_index.assertion_uri, RDF.type, NPX.IndexAssertion)
    n_index.p(n_index.assertion_uri, PROV.wasAttributedTo, URIRef(settings.base_url))
    fip_title = fip.title or community.get("name") or f"FIP {fip.id}"
    n_index.i(n_index.uri, DC11.title, Literal(fip_title, lang=language))
    n_index.i(n_index.uri, RDF.type, NPX.NanopubIndex)
    add_common_pubinfo(n_index)

    # -- nanopub N+3: the FIP -------------------------------------------
    n_fip = _Nanopub(fip.id, fip_n, "fip")
    fip_concept = n_fip.concept("fip")
    n_fip.a(fip_concept, RDF.type, FIP["FAIR-Implementation-Profile"])
    n_fip.a(fip_concept, RDFS.label, Literal(fip_title, lang=language))
    n_fip.a(fip_concept, RDFS.label, Literal(fip_title))  # review finding 7 / spec §7 Q5
    if description:
        n_fip.a(fip_concept, DCTERMS.description, Literal(description, lang=language))
    n_fip.a(fip_concept, FIP["declared-by"], community_concept)
    n_fip.a(fip_concept, FIP["has-declaration-index"], n_index.uri)
    km_iri = URIRef(
        f"{settings.base_url}/knowledge-models/{fip.questionnaire_id}/{fip.questionnaire_version}"
    )
    n_fip.a(fip_concept, DCTERMS.conformsTo, km_iri)
    # Every nanopub's provenance graph carries at least the same attribution
    # placeholder as the community/declaration nanopubs (§2.4's ORCID gap),
    # so the graph is never empty -- an empty named graph would vanish on
    # round-trip parsing (rdflib drops a graph with zero triples), which
    # would make this file fail extract_np_metadata's 4-named-graph check.
    n_fip.p(n_fip.assertion_uri, PROV.wasAttributedTo, URIRef(settings.base_url))
    # Review finding 1: subject is the nanopub itself (`this:`), not the
    # pubinfo graph's own IRI -- see the matching fix on the community
    # nanopub above.
    n_fip.i(n_fip.uri, NPX.introduces, fip_concept)
    add_common_pubinfo(n_fip)

    # -- files, in signing order -------------------------------------------
    files: list[tuple[str, str]] = [(f"np/{1:04d}-community.trig", n1.to_trig())]
    for nanopub in decl_nanopubs:
        files.append((f"np/{nanopub.n:04d}-{nanopub.role}.trig", nanopub.to_trig()))
    files.append((f"np/{index_n:04d}-index.trig", n_index.to_trig()))
    files.append((f"np/{fip_n:04d}-fip.trig", n_fip.to_trig()))

    # -- index.json ----------------------------------------------------
    temp_base = f"{_TEMP_PREFIX}/{fip.id}/"
    declaration_ns = [meta["n"] for meta in decl_meta]

    # Review finding 16: a dict, not an O(N) scan of `files` per lookup --
    # `rewrites` below calls this once per (nanopub, referencedBy) pair, so
    # the old linear scan was O(N^2) in the number of nanopubs.
    _file_by_n: dict[int, str] = {
        int(path[len("np/") : path.index("-", len("np/"))]): path for path, _ in files
    }

    def _nanopub_file(nn: int) -> str:
        try:
            return _file_by_n[nn]
        except KeyError:
            raise AssertionError(f"no file for nanopub {nn}") from None  # pragma: no cover

    nanopubs_entries: list[dict[str, Any]] = []
    nanopubs_entries.append(
        {
            "n": 1,
            "role": "community",
            "file": _nanopub_file(1),
            "tempNanopubIri": n1.base,
            "conceptIri": str(community_concept),
            "introduces": str(community_concept),
            "referencedBy": [*declaration_ns, fip_n],
        }
    )
    for nanopub, meta in zip(decl_nanopubs, decl_meta, strict=True):
        nanopubs_entries.append(
            {
                "n": meta["n"],
                "role": "declaration",
                "file": _nanopub_file(meta["n"]),
                "tempNanopubIri": nanopub.base,
                "conceptIri": str(nanopub.concept("declaration")),
                "questionId": meta["questionId"],
                "questionIri": meta["questionIri"],
                "declarationIndex": meta["declarationIndex"],
                "status": meta["status"],
                "resourceIri": meta["resourceIri"],
                "resourceOrigin": meta["resourceOrigin"],
                "references": [1],
                "referencedBy": [index_n],
            }
        )
    nanopubs_entries.append(
        {
            "n": index_n,
            "role": "index",
            "file": _nanopub_file(index_n),
            "tempNanopubIri": n_index.base,
            "conceptIri": None,
            "references": declaration_ns,
            "referencedBy": [fip_n],
        }
    )
    nanopubs_entries.append(
        {
            "n": fip_n,
            "role": "fip",
            "file": _nanopub_file(fip_n),
            "tempNanopubIri": n_fip.base,
            "conceptIri": str(fip_concept),
            "introduces": str(fip_concept),
            "references": [1, index_n],
            "referencedBy": [],
        }
    )

    rewrites = [
        {
            "afterSigning": entry["n"],
            "replacePrefix": entry["tempNanopubIri"],
            "withPrefix": f"<the trusty base of nanopub {entry['n']}>",
            "inFiles": [_nanopub_file(rb) for rb in entry["referencedBy"]],
        }
        for entry in nanopubs_entries
        if entry["referencedBy"]
    ]

    index_doc: dict[str, Any] = {
        "schema": "fipm-nanopub-bundle/1",
        "generator": {
            "tool": "FIP Manager",
            "agent": settings.base_url,
            "generatedAt": _iso_utc(now),
        },
        "fip": {
            "id": fip.id,
            "url": fip_url_str,
            "title": fip_title,
            "language": fip.language,
            "license": fip.license,
            "questionnaire": {"id": fip.questionnaire_id, "version": fip.questionnaire_version},
        },
        "tempBase": temp_base,
        "signed": False,
        "nanopubs": nanopubs_entries,
        "signingOrder": [entry["n"] for entry in nanopubs_entries],
        "rewrites": rewrites,
        "counts": {
            "nanopubs": len(nanopubs_entries),
            "declarations": declaration_count,
            "skipped": len(skipped),
        },
        "skipped": skipped,
        "notRepresented": {
            "notApplicable": not_applicable_ids,
            "answerComments": answer_comment_ids,
            "dmpEvidence": dmp_evidence_entries,
            "relatedDmps": len(fip.related_dmps or []),
        },
        "publishPrerequisites": {
            "satisfied": [],
            "missing": _MISSING_PREREQUISITES,
        },
    }

    manifest = _render_manifest(fip, now, index_doc)

    return NanopubBundle(files=files, index=index_doc, manifest=manifest, _now=now)


def _render_manifest(fip: Fip, now: datetime, index_doc: dict[str, Any]) -> str:
    counts = index_doc["counts"]
    not_represented = index_doc["notRepresented"]
    lines = [
        "# What this is",
        f"An unsigned nanopublication bundle for FIP {fip.id}, generated by "
        f"FIP Manager on {_iso_utc(now)}.",
        "Nothing here has been published. Nothing here is signed. No key material was used.",
        "",
        "# What is still needed to publish",
        "1. An ORCID iD for the person who takes responsibility for these declarations.",
        "2. An RSA 2048 keypair for that ORCID:  `np setup`   (nanopub-py)",
        '   or  MakeKeys.make("~/.nanopub/id", SignatureAlgorithm.RSA)   (nanopub-java)',
        "3. A published key declaration linking the key to the ORCID (`np setup` offers this).",
        "4. A signing tool: nanopub-py, or the nanopub-java `np` CLI.",
        '5. Apply index.json\'s `rewrites` in `signingOrder` order -- see "Order matters" below.',
        "",
        "# Order matters",
        "Signing changes a nanopub's IRI (it becomes a hash of its content), so siblings that",
        "reference it must be updated afterwards. Sign in this order -- which is also the file",
        "order in np/:",
        "  1. the community nanopub",
        "  2. every declaration nanopub",
        "  3. the declaration index",
        "  4. the FIP nanopub",
        "After each step, replace that nanopub's temp base (index.json -> `tempBase`, "
        "`nanopubs[].tempNanopubIri`)",
        "with its new trusty base in the files listed under `rewrites[].inFiles`.",
        "nanopub-py does NOT do this for you: `replace_trusty_in_graph` rewrites only the "
        "nanopub's own namespace.",
        "",
        "# What is in the bundle",
        f"- {counts['nanopubs']} nanopublications: 1 community, "
        f"{counts['declarations']} declaration(s), 1 declaration index, 1 FIP.",
        f"- {counts['skipped']} declaration(s) skipped (see below).",
        "",
        "# What FIP Manager data is NOT in the bundle, and why",
        '- `answer.notApplicable: true` -- a different claim from "no choice made yet"; '
        f"questions: {', '.join(not_represented['notApplicable']) or '(none)'}.",
        "- An answer comment on more than one declaration (or none) -- "
        '`fip:considerations` has no subject for "the answer as a whole"; '
        f"questions: {', '.join(not_represented['answerComments']) or '(none)'}.",
        "- `declaration.dmpEvidence` -- the FIP ontology has no DMP-evidence "
        "property, and a DMP URL "
        f"may be an internal link; {len(not_represented['dmpEvidence'])} declaration(s) affected.",
        f"- `fip.relatedDmps` -- {not_represented['relatedDmps']} plan(s), "
        "omitted for the same reason.",
        "- `fip.orphanedAnswers` -- by construction these have no current question to attach to.",
        "- A declaration on a question with no `fip:FIP-Question-*` counterpart (a forked "
        f"knowledge model) -- {counts['skipped']} declaration(s), see `skipped` in index.json.",
        "",
        "# Publishing is irreversible",
        "A published nanopublication is immutable and is replicated across the network. It can be",
        "retracted (a further nanopub saying so) or superseded, but not deleted. Do not "
        "publish a FIP",
        "whose community has not agreed to publish it.",
        "",
    ]
    return "\n".join(lines)
