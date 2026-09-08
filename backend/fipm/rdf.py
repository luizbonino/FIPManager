"""FIP -> RDF export (spec 03-matrix-and-rdf.md §2).

Builds an rdflib Graph for one FIP (`fip_graph`) or for a whole workshop
session (`session_graph`, the union of its FIPs' graphs plus a session
node), and serialises it to Turtle or JSON-LD. Reuses `exporters.resolve_lang`
and `exporters.fip_url` so the RDF and the JSON/CSV exports agree on lang
fallback and on the FIP's canonical URL.

IRIs are minted from `settings.base_url` at call time (never cached), so a
different `FIPM_BASE_URL` changes every minted IRI and nothing else (AC9).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from rdflib import RDF, RDFS, XSD, Graph, Literal, Namespace, URIRef
from sqlalchemy.orm import Session

from fipm.config import Settings
from fipm.exporters import fip_url
from fipm.fer_types import get_fer_types
from fipm.models import Fer, Fip, KnowledgeModel, WorkshopSession

FIP = Namespace("https://w3id.org/fair/fip/terms/")
FAIR = Namespace("https://w3id.org/fair/principles/terms/")
DCTERMS = Namespace("http://purl.org/dc/terms/")
PROV = Namespace("http://www.w3.org/ns/prov#")

TURTLE_HEADER = (
    "# FIP exported by FIP Manager. Ontology terms: FIP Ontology "
    "(https://w3id.org/fair/fip/terms/), CC0 1.0.\n"
)

# spec 00-fip-ontology-mapping.md §2: FIP Manager status -> ontology property.
# `none` deliberately has no entry: no `declares-*` triple is emitted for it.
STATUS_PREDICATE: dict[str, URIRef] = {
    "current": FIP["declares-current-use-of"],
    "planned": FIP["declares-planned-use-of"],
    "planned-development": FIP["declares-planned-development-of"],
    "planned-replacement": FIP["declares-planned-replacement-of"],
}

# spec 03 §2.3: licence string -> IRI. An unmapped string stays a plain
# literal, never a guessed IRI.
LICENSE_IRI_MAP: dict[str, str] = {
    "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
    "CC-BY-SA-4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
    "CC-BY-NC-4.0": "https://creativecommons.org/licenses/by-nc/4.0/",
}

# The 21 `fip:FIP-Question-*` individuals verified in spec 00 §4.
KNOWN_QUESTION_INDIVIDUALS: frozenset[str] = frozenset(
    {
        "F1-MD",
        "F1-D",
        "F2",
        "F3",
        "F4-MD",
        "F4-D",
        "A1.1-MD",
        "A1.1-D",
        "A1.2-MD",
        "A1.2-D",
        "A2",
        "I1-MD",
        "I1-D",
        "I2-MD",
        "I2-D",
        "I3-MD",
        "I3-D",
        "R1.1-MD",
        "R1.1-D",
        "R1.2-MD",
        "R1.2-D",
    }
)

PRINCIPLE_RE = re.compile(r"^[FAIR]\d(\.\d)?$")
ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")

# spec 00 §6: required attribution string for a CC-BY-SA-licensed knowledge
# model, plus its two verified ORCIDs (a third author, Jacintha Schultes, has
# no verified ORCID and is cited as a plain literal instead).
KM_ATTRIBUTION_TEXT = (
    "FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, Barbara Magagna, "
    "Jacintha Schultes / GO FAIR Foundation, CC BY-SA 4.0."
)
KM_ATTRIBUTION_ORCIDS = ("0000-0001-8888-635X", "0000-0003-2195-3997")
KM_ATTRIBUTION_NAME_LITERAL = "Jacintha Schultes"


def _fipmx_ns(settings: Settings) -> Namespace:
    return Namespace(f"{settings.base_url}/ns#")


def new_graph(settings: Settings) -> Graph:
    """A fresh Graph with the §2.1 prefixes bound."""
    g = Graph()
    g.bind("fip", FIP)
    g.bind("fair", FAIR)
    g.bind("dcterms", DCTERMS)
    g.bind("prov", PROV)
    g.bind("rdfs", RDFS)
    g.bind("xsd", XSD)
    g.bind("fipmx", _fipmx_ns(settings))
    return g


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat().replace("+00:00", "Z")


def _license_node(value: str | None) -> URIRef | Literal | None:
    if not value:
        return None
    mapped = LICENSE_IRI_MAP.get(value)
    if mapped:
        return URIRef(mapped)
    return Literal(value)


def _question_individual_local(question_id: str) -> str | None:
    """Map a knowledge-model question id to a `fip:FIP-Question-<X>` local
    name, per spec 03 §2.3: `-metadata` -> `-MD`, `-data` -> `-D`, unscoped
    ids unchanged -- but only if the result is one of the 21 verified
    individuals (spec 00 §4); otherwise None."""
    if question_id.endswith("-metadata"):
        candidate = question_id[: -len("-metadata")] + "-MD"
    elif question_id.endswith("-data"):
        candidate = question_id[: -len("-data")] + "-D"
    else:
        candidate = question_id
    return candidate if candidate in KNOWN_QUESTION_INDIVIDUALS else None


def _frag(part: str) -> str:
    """Percent-encode a fragment part, leaving `.` and `-` (and other
    unreserved characters) untouched -- spec 03 §2.2."""
    return quote(part, safe=".-")


def _free_text_hash(text: str) -> str:
    """First 16 hex chars of SHA-256 of the NFC-normalised, stripped,
    whitespace-collapsed, casefolded text -- spec 03 §2.4, the same
    normalisation the comparison matrix uses (spec 03 §1.2) so both agree on
    what "the same resource" is."""
    normalised = unicodedata.normalize("NFC", text).strip()
    normalised = re.sub(r"\s+", " ", normalised).casefold()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:16]


def _fer_type_class(settings: Settings, fer_type_key: str | None) -> URIRef | None:
    if not fer_type_key:
        return None
    entry = get_fer_types(settings).get(fer_type_key)
    if not entry or not entry.get("iri"):
        return None
    return URIRef(entry["iri"])


def _resolve_lang_pair(
    langmap: dict[str, str] | None, language: str, default_language: str
) -> tuple[str, str] | None:
    """Like `exporters.resolve_lang`, but also returns the langmap key the
    text actually came from, so the emitted literal is tagged with the
    language it is really written in (not necessarily the FIP's own
    language) -- used for the knowledge model's own multilingual `title`."""
    if not langmap:
        return None
    if language in langmap:
        return langmap[language], language
    if language == "pt-PT" and "pt-BR" in langmap:
        return langmap["pt-BR"], "pt-BR"
    if language == "pt-BR" and "pt-PT" in langmap:
        return langmap["pt-PT"], "pt-PT"
    if default_language in langmap:
        return langmap[default_language], default_language
    for key, value in langmap.items():
        return value, key
    return None


def _emit_fer(
    g: Graph,
    db: Session,
    settings: Settings,
    decl: dict[str, Any],
    fer_type_key: str | None,
    language: str,
) -> URIRef | None:
    """Emit the FER node for a declaration (catalogue or free-text) and
    return its IRI, or None if the declaration carries neither."""
    fipmx = _fipmx_ns(settings)
    fer_id = decl.get("ferId")
    free_text = decl.get("ferFreeText")
    fer_type_iri = _fer_type_class(settings, fer_type_key)

    if fer_id:
        fer_iri = URIRef(fer_id)
        g.add((fer_iri, RDF.type, FIP["FAIR-Enabling-Resource"]))
        fer_row = db.get(Fer, fer_id)
        if fer_row is not None:
            row_type_iri = _fer_type_class(settings, fer_row.type) or fer_type_iri
            if row_type_iri is not None:
                g.add((fer_iri, RDF.type, row_type_iri))
            for lang, text in (fer_row.label or {}).items():
                if text:
                    g.add((fer_iri, RDFS.label, Literal(text, lang=lang)))
        elif fer_type_iri is not None:
            g.add((fer_iri, RDF.type, fer_type_iri))
        return fer_iri

    if free_text:
        fer_iri = URIRef(f"{settings.base_url}/fers/text/{_free_text_hash(free_text)}")
        g.add((fer_iri, RDF.type, FIP["FAIR-Enabling-Resource"]))
        if fer_type_iri is not None:
            g.add((fer_iri, RDF.type, fer_type_iri))
        g.add((fer_iri, RDFS.label, Literal(free_text, lang=language)))
        g.add((fer_iri, fipmx["free-text"], Literal(True)))
        return fer_iri

    return None


def _questions_by_id(km: KnowledgeModel | None) -> dict[str, dict[str, Any]]:
    content = km.content if km else {}
    return {
        question["id"]: question
        for section in (content or {}).get("sections", [])
        for question in section.get("questions", [])
    }


def fip_graph(db: Session, fip: Fip, settings: Settings, g: Graph | None = None) -> Graph:
    """The triples for one FIP: the FIP node, its community, its
    declarations, its answer comments and the knowledge model it conforms
    to. `g`, when given, lets a caller (namely `session_graph`) merge several
    FIPs' triples into one shared Graph -- identical triples across FIPs
    (e.g. the same knowledge-model node, or two groups' matching free-text
    FER) simply collapse, since a Graph is a set of triples."""
    if g is None:
        g = new_graph(settings)
    fipmx = _fipmx_ns(settings)

    fip_iri = URIRef(fip_url(fip, settings))
    community = fip.community or {}
    community_name = community.get("name")
    language = fip.language
    default_language = settings.default_language

    g.add((fip_iri, RDF.type, FIP["FAIR-Implementation-Profile"]))
    if community_name:
        g.add((fip_iri, DCTERMS.title, Literal(community_name, lang=language)))
    license_node = _license_node(fip.license)
    if license_node is not None:
        g.add((fip_iri, DCTERMS.license, license_node))
    g.add((fip_iri, DCTERMS.created, Literal(_iso_utc(fip.created_at), datatype=XSD.dateTime)))
    g.add((fip_iri, DCTERMS.modified, Literal(_iso_utc(fip.updated_at), datatype=XSD.dateTime)))
    g.add((fip_iri, DCTERMS.language, Literal(language)))

    km = db.get(KnowledgeModel, (fip.questionnaire_id, fip.questionnaire_version))
    km_iri = URIRef(
        f"{settings.base_url}/knowledge-models/{fip.questionnaire_id}/{fip.questionnaire_version}"
    )
    g.add((fip_iri, DCTERMS.conformsTo, km_iri))

    community_iri = URIRef(f"{fip_iri}#community")
    g.add((fip_iri, FIP["declared-by"], community_iri))

    # -- community -----------------------------------------------------
    g.add((community_iri, RDF.type, FIP["FAIR-Implementation-Community"]))
    if community_name:
        g.add((community_iri, DCTERMS.title, Literal(community_name, lang=language)))
    description = community.get("description")
    if description:
        g.add((community_iri, DCTERMS.description, Literal(description, lang=language)))
    domain = community.get("domain")
    if domain:
        g.add((community_iri, FIP["has-research-domain"], Literal(domain, lang=language)))
    data_steward = community.get("dataSteward")
    if data_steward:
        orcid = data_steward.get("orcid")
        steward_name = data_steward.get("name")
        if orcid and ORCID_RE.match(orcid):
            g.add((community_iri, FIP["has-data-steward"], URIRef(f"https://orcid.org/{orcid}")))
        elif steward_name:
            g.add((community_iri, FIP["has-data-steward"], Literal(steward_name)))
    for link in community.get("links") or []:
        g.add((community_iri, RDFS.seeAlso, URIRef(link)))

    # -- related DMPs ----------------------------------------------------
    for dmp in fip.related_dmps or []:
        dmp_url = dmp.get("url")
        if not dmp_url:
            continue
        dmp_iri = URIRef(dmp_url)
        g.add((fip_iri, PROV.wasDerivedFrom, dmp_iri))
        g.add((dmp_iri, RDF.type, fipmx["Data-Management-Plan"]))
        version = dmp.get("version")
        if version:
            g.add((dmp_iri, fipmx["dmp-version"], Literal(version)))
        system = dmp.get("system")
        if system:
            g.add((dmp_iri, fipmx["dmp-system"], Literal(system)))

    # -- knowledge model + attribution ------------------------------------
    if km is not None:
        title_pair = _resolve_lang_pair(km.title, language, default_language)
        if title_pair:
            text, tag = title_pair
            g.add((km_iri, DCTERMS.title, Literal(text, lang=tag)))
        if km.version:
            g.add((km_iri, DCTERMS.hasVersion, Literal(km.version)))
        source = km.source
        source_text = source.get("name") if isinstance(source, dict) else source
        if source_text:
            g.add((km_iri, DCTERMS.source, Literal(source_text)))
        km_license_node = _license_node(km.license)
        if km_license_node is not None:
            g.add((km_iri, DCTERMS.license, km_license_node))
        if (km.license or "").startswith("CC-BY-SA"):
            g.add((km_iri, DCTERMS.rights, Literal(KM_ATTRIBUTION_TEXT)))
            for orcid in KM_ATTRIBUTION_ORCIDS:
                g.add((km_iri, DCTERMS.creator, URIRef(f"https://orcid.org/{orcid}")))
            g.add((km_iri, DCTERMS.creator, Literal(KM_ATTRIBUTION_NAME_LITERAL)))

    # -- declarations + answer comments -----------------------------------
    questions_by_id = _questions_by_id(km)
    for answer in fip.answers or []:
        qid = answer.get("questionId")
        if not qid:
            continue
        question_meta = questions_by_id.get(qid, {})
        principle = question_meta.get("principle")
        fer_type_key = question_meta.get("ferType")
        q_local = _question_individual_local(qid)

        for idx, decl in enumerate(answer.get("declarations") or []):
            decl_iri = URIRef(f"{fip_iri}#decl-{_frag(qid)}-{idx}")
            g.add((decl_iri, RDF.type, FIP["FIP-Declaration"]))
            g.add((decl_iri, FIP["declared-by"], community_iri))
            g.add((decl_iri, fipmx["declaration-index"], Literal(idx, datatype=XSD.integer)))
            status = decl.get("status")
            if status:
                g.add((decl_iri, fipmx["declaration-status"], Literal(status)))
            if q_local:
                g.add((decl_iri, FIP["refers-to-question"], FIP[f"FIP-Question-{q_local}"]))
            else:
                g.add((decl_iri, fipmx["question-id"], Literal(qid)))
            if principle and PRINCIPLE_RE.match(principle):
                g.add((decl_iri, FIP["refers-to-principle"], FAIR[principle]))

            if status == "none":
                g.add((decl_iri, RDF.type, FIP["FIP-No-Choice-Declaration"]))
            else:
                fer_iri = _emit_fer(g, db, settings, decl, fer_type_key, language)
                predicate = STATUS_PREDICATE.get(status) if status else None
                if predicate is not None and fer_iri is not None:
                    g.add((decl_iri, predicate, fer_iri))

            for note_lang, note_text in (decl.get("note") or {}).items():
                if note_text:
                    g.add((decl_iri, FIP.considerations, Literal(note_text, lang=note_lang)))

            dmp_evidence = decl.get("dmpEvidence")
            if dmp_evidence:
                evidence_url = dmp_evidence.get("url")
                if evidence_url:
                    g.add((decl_iri, PROV.wasDerivedFrom, URIRef(evidence_url)))
                question_ref = dmp_evidence.get("questionRef")
                if question_ref:
                    g.add((decl_iri, fipmx["dmp-question-ref"], Literal(question_ref)))

            g.add((fip_iri, fipmx["has-declaration"], decl_iri))

        comment = answer.get("comment")
        if comment:
            answer_iri = URIRef(f"{fip_iri}#answer-{_frag(qid)}")
            g.add((answer_iri, RDF.type, fipmx["Answer"]))
            g.add((answer_iri, fipmx["question-id"], Literal(qid)))
            if q_local:
                g.add((answer_iri, FIP["refers-to-question"], FIP[f"FIP-Question-{q_local}"]))
            g.add((answer_iri, fipmx["answer-comment"], Literal(comment, lang=language)))

    return g


def session_graph(
    db: Session, session: WorkshopSession, fips: list[Fip], settings: Settings
) -> Graph:
    """One merged graph: every FIP's triples (deduplicated, since a Graph is
    a set) plus a session node typed `fipmx:Workshop-Session`."""
    g = new_graph(settings)
    fipmx = _fipmx_ns(settings)
    for fip in fips:
        fip_graph(db, fip, settings, g=g)

    session_iri = URIRef(f"{settings.base_url}/sessions/{session.id}")
    g.add((session_iri, RDF.type, fipmx["Workshop-Session"]))
    if session.title:
        g.add((session_iri, DCTERMS.title, Literal(session.title)))
    created_literal = Literal(_iso_utc(session.created_at), datatype=XSD.dateTime)
    g.add((session_iri, DCTERMS.created, created_literal))
    for fip in fips:
        g.add((session_iri, fipmx["has-fip"], URIRef(fip_url(fip, settings))))

    return g


def to_turtle(g: Graph) -> str:
    """Turtle serialisation with the CC0 ontology-credit comment header
    (spec 03 §2.3: "a Turtle comment header, not a triple")."""
    return TURTLE_HEADER + g.serialize(format="turtle")


def _jsonld_context(g: Graph) -> dict[str, Any]:
    """Spec 03 §2.6, with the prefix IRIs taken from the graph's own bound
    namespaces so `fipmx` always matches the `settings.base_url` the graph
    was built with (AC9)."""
    ns = dict(g.namespaces())
    return {
        "fip": str(ns["fip"]),
        "fair": str(ns["fair"]),
        "fipmx": str(ns["fipmx"]),
        "dcterms": str(ns["dcterms"]),
        "prov": str(ns["prov"]),
        "rdfs": str(ns["rdfs"]),
        "xsd": str(ns["xsd"]),
        "id": "@id",
        "type": "@type",
        "label": {"@id": "rdfs:label"},
        "title": {"@id": "dcterms:title"},
        "considerations": {"@id": "fip:considerations"},
        "declarationStatus": {"@id": "fipmx:declaration-status"},
        "created": {"@id": "dcterms:created", "@type": "xsd:dateTime"},
        "modified": {"@id": "dcterms:modified", "@type": "xsd:dateTime"},
        "declarationIndex": {"@id": "fipmx:declaration-index", "@type": "xsd:integer"},
        "license": {"@id": "dcterms:license", "@type": "@id"},
        "conformsTo": {"@id": "dcterms:conformsTo", "@type": "@id"},
        "declaredBy": {"@id": "fip:declared-by", "@type": "@id"},
        "hasDeclaration": {"@id": "fipmx:has-declaration", "@type": "@id"},
        "refersToQuestion": {"@id": "fip:refers-to-question", "@type": "@id"},
        "refersToPrinciple": {"@id": "fip:refers-to-principle", "@type": "@id"},
        "currentUseOf": {"@id": "fip:declares-current-use-of", "@type": "@id"},
        "plannedUseOf": {"@id": "fip:declares-planned-use-of", "@type": "@id"},
        "plannedDevelopmentOf": {"@id": "fip:declares-planned-development-of", "@type": "@id"},
        "plannedReplacementOf": {"@id": "fip:declares-planned-replacement-of", "@type": "@id"},
    }


def to_jsonld(g: Graph) -> str:
    context = _jsonld_context(g)
    return g.serialize(format="json-ld", context=context, indent=2, auto_compact=True)
