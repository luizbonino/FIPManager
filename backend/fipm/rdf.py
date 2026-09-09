"""FIP -> RDF export (spec 03-matrix-and-rdf.md §2).

Builds an rdflib Graph for one FIP (`fip_graph`) or for a whole workshop
session (`session_graph`, the union of its FIPs' graphs plus a session
node), and serialises it to Turtle or JSON-LD. Reuses `exporters.resolve_lang`
and `exporters.fip_url` so the RDF and the JSON/CSV exports agree on lang
fallback and on the FIP's canonical URL.

Instance IRIs (FIPs, sessions, free-text FERs, ...) are minted from
`settings.base_url` at call time (never cached), so a different
`FIPM_BASE_URL` changes every instance IRI and nothing else (AC9). The
`fipmx` extension VOCABULARY namespace (classes/properties FIP Manager
defines) is a separate, fixed IRI -- `settings.ext_ns`, default
`https://w3id.org/fipm/ns#` -- independent of base_url, so the same classes
and properties mean the same thing across deployments.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlparse

from rdflib import RDF, RDFS, XSD, Graph, Literal, Namespace, URIRef
from rdflib.namespace import FOAF
from sqlalchemy.orm import Session

from fipm.config import Settings
from fipm.dmp import resolve_dmp_evidence_for_export
from fipm.exporters import fip_url
from fipm.fer_types import get_fer_types
from fipm.models import Fer, Fip, KnowledgeModel, WorkshopSession

FIP = Namespace("https://w3id.org/fair/fip/terms/")
FAIR = Namespace("https://w3id.org/fair/principles/terms/")
DCTERMS = Namespace("http://purl.org/dc/terms/")
PROV = Namespace("http://www.w3.org/ns/prov#")
# RDA DMP Common Standard ontology (audit finding 12): replaces the
# home-grown `fipmx:Data-Management-Plan` class.
DCSO = Namespace("https://w3id.org/dcso/ns/core#")

ONTOLOGY_CREDIT_TEXT = (
    "FIP exported by FIP Manager. Ontology terms: FIP Ontology "
    "(https://w3id.org/fair/fip/terms/), CC0 1.0."
)
TURTLE_HEADER = f"# {ONTOLOGY_CREDIT_TEXT}\n"

# spec 00-fip-ontology-mapping.md §2: FIP Manager status -> ontology property.
# `none` deliberately has no entry: no `declares-*` triple is emitted for it.
STATUS_PREDICATE: dict[str, URIRef] = {
    "current": FIP["declares-current-use-of"],
    "planned": FIP["declares-planned-use-of"],
    "planned-development": FIP["declares-planned-development-of"],
    "planned-replacement": FIP["declares-planned-replacement-of"],
}

# audit finding 7: a FER's availability class depends on the status(es) it is
# declared under. current/planned/planned-replacement => already available;
# planned-development => still to be developed. A FER referenced by several
# declarations with different statuses ends up carrying both types (a Graph
# is a set of triples, so repeats collapse).
STATUS_AVAILABILITY_CLASS: dict[str, URIRef] = {
    "current": FIP["Available-FAIR-Enabling-Resource"],
    "planned": FIP["Available-FAIR-Enabling-Resource"],
    "planned-replacement": FIP["Available-FAIR-Enabling-Resource"],
    "planned-development": FIP["FAIR-Enabling-Resource-to-be-Developed"],
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

# audit finding 12: whitelist of `fair:<id>` principle IRIs that may be
# minted -- exactly the 15 individuals spec 00 (§4) actually uses. Anything
# else (e.g. a stray "R2") is skipped rather than guessed into an IRI.
KNOWN_PRINCIPLE_IDS: frozenset[str] = frozenset(
    {
        "F1",
        "F2",
        "F3",
        "F4",
        "A1",
        "A1.1",
        "A1.2",
        "A2",
        "I1",
        "I2",
        "I3",
        "R1",
        "R1.1",
        "R1.2",
        "R1.3",
    }
)
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
    """The `fipmx` extension VOCABULARY namespace (audit finding 2): a fixed
    IRI (`settings.ext_ns`, default `https://w3id.org/fipm/ns#`), independent
    of `settings.base_url`, so class/property IRIs don't differ per
    deployment. Instance IRIs (FIPs, sessions, free-text FERs) keep following
    base_url -- see module docstring and AC9."""
    return Namespace(settings.ext_ns)


def new_graph(settings: Settings) -> Graph:
    """A fresh Graph with the §2.1 prefixes bound."""
    g = Graph()
    g.bind("fip", FIP)
    g.bind("fair", FAIR)
    g.bind("dcterms", DCTERMS)
    g.bind("prov", PROV)
    g.bind("rdfs", RDFS)
    g.bind("xsd", XSD)
    g.bind("dcso", DCSO)
    g.bind("foaf", FOAF)
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


def _is_http_iri(value: str) -> bool:
    """True if `value` parses as an http(s) IRI -- audit finding 4:
    `fip:has-research-domain` is an ObjectProperty, so a bare literal domain
    string must fall back to `dcterms:subject` instead."""
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


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
    status: str | None = None,
) -> URIRef | None:
    """Emit the FER node for a declaration (catalogue or free-text) and
    return its IRI, or None if the declaration carries neither. `status`
    (audit finding 7) additionally types the FER `fip:Available-FAIR-
    Enabling-Resource` (current/planned/planned-replacement) or `fip:FAIR-
    Enabling-Resource-to-be-Developed` (planned-development); a FER used
    under several statuses across declarations picks up both types."""
    fipmx = _fipmx_ns(settings)
    fer_id = decl.get("ferId")
    free_text = decl.get("ferFreeText")
    fer_type_iri = _fer_type_class(settings, fer_type_key)
    availability_iri = STATUS_AVAILABILITY_CLASS.get(status) if status else None

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
        if availability_iri is not None:
            g.add((fer_iri, RDF.type, availability_iri))
        return fer_iri

    if free_text:
        fer_iri = URIRef(f"{settings.base_url}/fers/text/{_free_text_hash(free_text)}")
        g.add((fer_iri, RDF.type, FIP["FAIR-Enabling-Resource"]))
        if fer_type_iri is not None:
            g.add((fer_iri, RDF.type, fer_type_iri))
        if availability_iri is not None:
            g.add((fer_iri, RDF.type, availability_iri))
        g.add((fer_iri, RDFS.label, Literal(free_text, lang=language)))
        g.add((fer_iri, fipmx["free-text"], Literal(True)))
        return fer_iri

    return None


def _none_declaration_text(
    db: Session, decl: dict[str, Any], language: str, default_language: str
) -> str | None:
    """The FER label or free text that a "none"-status declaration would
    otherwise silently drop -- audit finding 6. No FER node is minted for a
    "none" declaration; only its label/text survives, as a plain
    `fip:considerations` literal tagged with the FIP's own language."""
    fer_id = decl.get("ferId")
    if fer_id:
        fer_row = db.get(Fer, fer_id)
        if fer_row is not None:
            pair = _resolve_lang_pair(fer_row.label, language, default_language)
            if pair:
                return pair[0]
        return None
    free_text = decl.get("ferFreeText")
    return free_text or None


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
    # audit finding 12: the CC0 ontology-credit, also as a triple (not only
    # as a Turtle comment header) so it survives into JSON-LD too.
    g.add((fip_iri, RDFS.comment, Literal(ONTOLOGY_CREDIT_TEXT, lang="en")))

    km = db.get(KnowledgeModel, (fip.questionnaire_id, fip.questionnaire_version))
    km_iri = URIRef(
        f"{settings.base_url}/knowledge-models/{fip.questionnaire_id}/{fip.questionnaire_version}"
    )
    g.add((fip_iri, DCTERMS.conformsTo, km_iri))

    community_iri = URIRef(f"{fip_iri}#community")
    # audit finding 3: `fip:declared-by` has domain fip:FAIR-Declaration, not
    # the FIP itself -- use the fipmx extension property here. Each
    # declaration node (below) is itself a FAIR-Declaration subclass, so it
    # keeps `fip:declared-by` pointing at the community.
    g.add((fip_iri, fipmx["declared-by-community"], community_iri))

    # -- community -----------------------------------------------------
    g.add((community_iri, RDF.type, FIP["FAIR-Implementation-Community"]))
    if community_name:
        g.add((community_iri, DCTERMS.title, Literal(community_name, lang=language)))
    description = community.get("description")
    if description:
        g.add((community_iri, DCTERMS.description, Literal(description, lang=language)))
    domain = community.get("domain")
    if domain:
        # audit finding 4: fip:has-research-domain is an ObjectProperty; a
        # literal there would make the graph OWL-DL invalid. Only emit it
        # when the value is itself an http(s) IRI, otherwise fall back to
        # dcterms:subject (a literal-friendly annotation property).
        if _is_http_iri(domain):
            g.add((community_iri, FIP["has-research-domain"], URIRef(domain)))
        else:
            g.add((community_iri, DCTERMS.subject, Literal(domain, lang=language)))
    data_steward = community.get("dataSteward")
    if data_steward:
        orcid = data_steward.get("orcid")
        steward_name = data_steward.get("name")
        if orcid and ORCID_RE.match(orcid):
            g.add((community_iri, FIP["has-data-steward"], URIRef(f"https://orcid.org/{orcid}")))
        elif steward_name:
            # audit finding 5: fip:has-data-steward is an ObjectProperty --
            # without a verified ORCID, mint a local foaf:Person node instead
            # of putting a name literal directly in object position.
            steward_iri = URIRef(f"{fip_iri}#data-steward")
            g.add((community_iri, FIP["has-data-steward"], steward_iri))
            g.add((steward_iri, RDF.type, FOAF.Person))
            g.add((steward_iri, RDFS.label, Literal(steward_name)))
            g.add((steward_iri, FOAF.name, Literal(steward_name)))
    for link in community.get("links") or []:
        g.add((community_iri, RDFS.seeAlso, URIRef(link)))

    # -- related DMPs ----------------------------------------------------
    for dmp in fip.related_dmps or []:
        dmp_url = dmp.get("url")
        if not dmp_url:
            continue
        dmp_iri = URIRef(dmp_url)
        g.add((fip_iri, PROV.wasDerivedFrom, dmp_iri))
        # audit finding 12: dcso:DMP (RDA DMP Common Standard ontology)
        # replaces the home-grown fipmx:Data-Management-Plan class; the link
        # itself (prov:wasDerivedFrom above) is unchanged.
        g.add((dmp_iri, RDF.type, DCSO.DMP))
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
        # The importer flattens a {"name","url"} source to its name in the
        # `source` column; the stored document keeps the full object.
        content_source = (km.content or {}).get("source") if isinstance(km.content, dict) else None
        source = content_source if isinstance(content_source, dict) else km.source
        # audit finding 8: a dict source with a "url" becomes a proper
        # dcterms:source URIRef, with the name (if any) as a
        # dcterms:bibliographicCitation; a plain-string source (or a dict
        # without "url") keeps the name-literal behaviour.
        if isinstance(source, dict):
            source_url = source.get("url")
            source_name = source.get("name")
            if source_url:
                g.add((km_iri, DCTERMS.source, URIRef(source_url)))
                if source_name:
                    g.add((km_iri, DCTERMS.bibliographicCitation, Literal(source_name, lang="en")))
            elif source_name:
                g.add((km_iri, DCTERMS.source, Literal(source_name, lang="en")))
        elif source:
            g.add((km_iri, DCTERMS.source, Literal(source, lang="en")))
        km_license_node = _license_node(km.license)
        if km_license_node is not None:
            g.add((km_iri, DCTERMS.license, km_license_node))
        if (km.license or "").startswith("CC-BY-SA"):
            g.add((km_iri, DCTERMS.rights, Literal(KM_ATTRIBUTION_TEXT, lang="en")))
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
        # spec 04-knowledge-model-editor.md §4: hidden questions emit nothing
        # at all in the RDF export.
        if question_meta.get("hidden") is True:
            continue
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
            if principle and principle in KNOWN_PRINCIPLE_IDS:
                g.add((decl_iri, FIP["refers-to-principle"], FAIR[principle]))

            if status == "none":
                g.add((decl_iri, RDF.type, FIP["FIP-No-Choice-Declaration"]))
                # audit finding 6: don't silently drop the FER label/text a
                # "none" declaration still carries -- surface it as a plain
                # consideration instead (no FER node is minted for it).
                none_text = _none_declaration_text(db, decl, language, default_language)
                if none_text:
                    g.add((decl_iri, FIP.considerations, Literal(none_text, lang=language)))
            else:
                fer_iri = _emit_fer(g, db, settings, decl, fer_type_key, language, status)
                predicate = STATUS_PREDICATE.get(status) if status else None
                if predicate is not None and fer_iri is not None:
                    g.add((decl_iri, predicate, fer_iri))

                # spec 05-v1-completion.md §5 (supersedes the "does not
                # auto-emit" sentence of spec 03 §2.3): a planned-replacement
                # declaration with a successor also emits
                # fip:declares-planned-use-of <successor>, on the same
                # declaration node as fip:declares-planned-replacement-of,
                # and types the successor fip:Available-FAIR-Enabling-
                # Resource (status="current"). Nothing extra when no
                # successor is set.
                if status == "planned-replacement":
                    successor_fer_id = decl.get("successorFerId")
                    successor_free_text = decl.get("successorFreeText")
                    if successor_fer_id or successor_free_text:
                        successor_decl = {
                            "ferId": successor_fer_id,
                            "ferFreeText": successor_free_text,
                        }
                        successor_iri = _emit_fer(
                            g, db, settings, successor_decl, fer_type_key, language, "current"
                        )
                        if successor_iri is not None:
                            g.add((decl_iri, FIP["declares-planned-use-of"], successor_iri))

            for note_lang, note_text in (decl.get("note") or {}).items():
                if note_text:
                    g.add((decl_iri, FIP.considerations, Literal(note_text, lang=note_lang)))

            # spec 06-dmp-linkage.md §2.4: resolve the stored dmpEvidence
            # (new index-based shape, or the legacy {url, questionRef}
            # shape) the same way the JSON export does, so both agree on
            # what "the DMP's IRI" is.
            resolved_evidence = resolve_dmp_evidence_for_export(
                decl.get("dmpEvidence"), fip.related_dmps or []
            )
            if resolved_evidence and resolved_evidence.get("dmpUrl"):
                evidence_iri = URIRef(resolved_evidence["dmpUrl"])
                # The existing declaration-level prov:wasDerivedFrom to the
                # same IRI is kept: prov: is what a generic consumer
                # understands, fipmx:dmp-evidence says "this is the
                # *justification* for this declaration".
                g.add((decl_iri, PROV.wasDerivedFrom, evidence_iri))
                g.add((decl_iri, fipmx["dmp-evidence"], evidence_iri))
                section = resolved_evidence.get("section")
                if section:
                    g.add((decl_iri, fipmx["dmp-section"], Literal(section)))
                question_ref = resolved_evidence.get("questionRef")
                if question_ref:
                    g.add((decl_iri, fipmx["dmp-question-ref"], Literal(question_ref)))

            g.add((fip_iri, fipmx["has-declaration"], decl_iri))

        comment = answer.get("comment")
        if comment:
            answer_iri = URIRef(f"{fip_iri}#answer-{_frag(qid)}")
            g.add((answer_iri, RDF.type, fipmx["Answer"]))
            g.add((answer_iri, fipmx["question-id"], Literal(qid)))
            if q_local:
                # audit finding 1: fip:refers-to-question has rdfs:domain
                # fip:FIP-Declaration, so using it here would type this
                # fipmx:Answer comment node as a declaration too. Use the
                # fipmx equivalent instead.
                g.add((answer_iri, fipmx["refers-to-question"], FIP[f"FIP-Question-{q_local}"]))
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
        # audit finding 12: tag the session title with the session's own
        # default language rather than leaving it a bare, untagged literal.
        g.add((session_iri, DCTERMS.title, Literal(session.title, lang=session.default_language)))
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
    namespaces -- `fipmx` is the fixed extension-vocabulary IRI (audit
    finding 2: `settings.ext_ns`), while `fip`/`fair`/etc. are the fixed
    ontology IRIs; only instance IRIs vary with `settings.base_url` (AC9)."""
    ns = dict(g.namespaces())
    return {
        "fip": str(ns["fip"]),
        "fair": str(ns["fair"]),
        "fipmx": str(ns["fipmx"]),
        "dcterms": str(ns["dcterms"]),
        "prov": str(ns["prov"]),
        "rdfs": str(ns["rdfs"]),
        "xsd": str(ns["xsd"]),
        "dcso": str(ns["dcso"]),
        "foaf": str(ns["foaf"]),
        "id": "@id",
        "type": "@type",
        "label": {"@id": "rdfs:label"},
        "title": {"@id": "dcterms:title"},
        "considerations": {"@id": "fip:considerations"},
        "declarationStatus": {"@id": "fipmx:declaration-status"},
        "created": {"@id": "dcterms:created", "@type": "xsd:dateTime"},
        "modified": {"@id": "dcterms:modified", "@type": "xsd:dateTime"},
        "declarationIndex": {"@id": "fipmx:declaration-index", "@type": "xsd:integer"},
        # spec 06-dmp-linkage.md §2.4: amends spec 03 §2.1's closed term list.
        "dmpEvidence": {"@id": "fipmx:dmp-evidence", "@type": "@id"},
        "dmpSection": {"@id": "fipmx:dmp-section"},
        "license": {"@id": "dcterms:license", "@type": "@id"},
        "conformsTo": {"@id": "dcterms:conformsTo", "@type": "@id"},
        "declaredBy": {"@id": "fip:declared-by", "@type": "@id"},
        "declaredByCommunity": {"@id": "fipmx:declared-by-community", "@type": "@id"},
        "hasDeclaration": {"@id": "fipmx:has-declaration", "@type": "@id"},
        "refersToQuestion": {"@id": "fip:refers-to-question", "@type": "@id"},
        "answerRefersToQuestion": {"@id": "fipmx:refers-to-question", "@type": "@id"},
        "refersToPrinciple": {"@id": "fip:refers-to-principle", "@type": "@id"},
        "currentUseOf": {"@id": "fip:declares-current-use-of", "@type": "@id"},
        "plannedUseOf": {"@id": "fip:declares-planned-use-of", "@type": "@id"},
        "plannedDevelopmentOf": {"@id": "fip:declares-planned-development-of", "@type": "@id"},
        "plannedReplacementOf": {"@id": "fip:declares-planned-replacement-of", "@type": "@id"},
    }


def to_jsonld(g: Graph) -> str:
    context = _jsonld_context(g)
    return g.serialize(format="json-ld", context=context, indent=2, auto_compact=True)
