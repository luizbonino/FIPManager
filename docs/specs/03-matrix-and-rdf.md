# Spec 03 – Comparison matrix and RDF export

Status: approved for implementation, 2026-09-08. Covers ROADMAP week 3 items 1 and 3. Authority: PLAN §4–§5; builds on
`00-fip-ontology-mapping.md` (terms, IRIs, status map), `01-foundations.md` (§3 exports, §6 API) and `02-core-flows.md` (§1 vocabulary, §4.2
SessionDetail, §6 frontend structure). **Not here:** the knowledge-model editor (week 3 item 2) — spec 04, may slip to v2. No DB change
(`SCHEMA_VERSION` stays 1), no new table, no change to the §3.1/§3.2 export shapes.

## 1. Comparison matrix — `/sessions/:id/matrix`

### 1.1 Decision: derived client-side, no new endpoint

`SessionMatrix.vue` derives everything from calls that already exist: `GET /api/sessions/{id}/fips` (owner-only, full FIPs, already fetched
by the 10 s poll of `stores/session.ts`), plus one-off calls to `GET /api/knowledge-models/{qid}/{qver}` (question order and texts in **all**
languages), `GET /api/fers?limit=500` (the catalogue the editor already caches, `ferId` → label) and `GET /api/fer-types` (row chips). A
server-side `GET /api/sessions/{id}/matrix` is rejected because (a) the matrix is owner/admin-only, so it
runs on the facilitator's laptop, not on 40 phones; (b) the poll already fetches these FIPs for `SessionFipList`, so an aggregate would
double the traffic or need a second poll; (c) the language switcher must retint question texts with **no** refetch, which a server-resolved
payload cannot do; (d) size is fine — ≈5 kB of JSON per FIP (21 answers, 1–2 declarations), so the workshop's ~8 group FIPs are ≈40 kB and
the pathological 40-FIP case ≈200 kB uncompressed (≈30 kB gzipped) per 10 s on one laptop. Escape hatch if the dry run disagrees: add
`?summary=1` to `GET /api/sessions/{id}/fips` (reserved in spec 02 §4.2), not a new matrix endpoint.

### 1.2 Data shape — `src/lib/matrix.ts`, pure and unit-tested

```ts
export type CellStatus = DeclarationStatus | 'unanswered'
export interface MatrixChip {          // one stored declaration
  key: string        // ferId ?? 'text:' + normalised free text — the convergence identity
  label: string      // resolved FER label, or the free text, or the bare IRI
  iri: string | null; freeText: boolean; status: DeclarationStatus; note: string | null }
export interface MatrixCell { fipId: string; chips: MatrixChip[]; comment: string | null; unanswered: boolean }
export interface Convergence {         // agreed = declaringFips >= 2 && distinctCurrent === 1
  declaringFips: number                // FIPs with >= 1 'current' declaration on this row
  distinctCurrent: number; topKey: string | null; topLabel: string | null; topCount: number; agreed: boolean }
export interface MatrixRow {
  questionId: string; principle: string | null; scope: 'metadata' | 'data' | null
  ferType: string | null; ferTypeLabel: string | null
  text: string; cells: MatrixCell[]; convergence: Convergence }
export interface MatrixGroup {         // one per knowledge-model section: F, A, I, R
  sectionId: string; title: string; rows: MatrixRow[]; rowsWithData: number; rowsAgreed: number }
export interface MatrixColumn {        // label = community.name truncated to 24 chars + '…'
  fipId: string; label: string; fullLabel: string; url: string; answeredCount: number; updatedAt: string }
export interface Matrix { columns: MatrixColumn[]; groups: MatrixGroup[]; questionCount: number }
export function buildMatrix(fips: FipOut[], km: KnowledgeModelOut, fers: Map<string, FerOut>,
                            ferTypes: Map<string, FerType>, locale: string): Matrix
```

Rows follow knowledge-model order (never the FIPs' `answers` order); columns follow `createdAt`, the order the endpoint returns. A missing
`answers` entry, or one with no declarations, gives `unanswered: true` and no chips — spec 02 §1 ("answered" = ≥1 declaration, `none` counts).
A free-text chip's `key` is `'text:'` plus the NFC-normalised, whitespace-collapsed, casefolded text — the **same** normalisation as the RDF
hash (§2.4), so matrix and Turtle agree on what "the same resource" is; an unknown `ferId` renders as the IRI. Convergence counts **only** status `current`, ties breaking on the smallest `topKey` so renders are deterministic.

### 1.3 Components

- **`views/SessionMatrix.vue`** (replaces the placeholder; the route is already `requiresAuth`) — a non-owner gets 404 from the API, which
  renders `common.notFound`. Header: session title, small join code, `LanguageSwitcher`, the three toggles, `MatrixLegend`, Print, and the
  store's reconnecting dot. Body: one `<table>` inside a horizontally scrolling wrapper, one `<tbody>` per group with a group-head row; the
  first column is a sticky `<th scope="row">` (`position:sticky;left:0`) carrying the question-id badge, resolved text, scope badge
  (`metadata`/`data`, absent for F2/F3/A2) and FER-type chip; one `<th scope="col">` per FIP with the truncated community name (`title` =
  full name) and an `answered/21` micro-bar; the last column holds the row's `ConvergenceBadge`. Uses `useSessionStore()` (`load`,
  `loadFips`, `startPolling`/`stopPolling`) — no new store.
- **`components/MatrixCell.vue`** — props `{ cell, compact }`. Each chip is a `<button type="button">` with class `chip status-<status>`,
  reusing the five `--color-status-*` variables of `styles.css` plus a new `--color-status-unanswered` (`#f3f4f6` fill, `#9ca3af` dashed
  border). Chip content = label **and** the `declarationStatus.*` text (colour is never the only signal, spec 02 §4.3); `compact` abbreviates
  that text to three letters, keeping it in full in `title`/`aria-label`. A chip with a note shows a degree marker: hover gives `title`, tap
  toggles the note under the chips. An empty cell renders "–", `aria-label` `matrix.unanswered`.
- **`components/ConvergenceBadge.vue`** — props `{ convergence, compact }`: `distinctCurrent` big, most-common label × count beneath, a
  green check when `agreed`; group heads reuse it with `rowsAgreed` of `rowsWithData`.
- **`components/MatrixLegend.vue`** — the six cell states with colours and labels, the scope badges, the convergence number. Always printed.

### 1.4 Toggles, language, print

Three header checkboxes, persisted as one JSON object in `localStorage['fipm.matrix.opts']` (try/catch, per `lib/editTokens.ts`):
`onlyCurrent` (hide chips whose status is not `current`; a cell emptied that way renders as unanswered), `hideUnanswered` (drop rows where
**every** cell is unanswered — never rows that merely have gaps), and `compact` (smaller type, tighter padding, abbreviated status text,
question text clamped to two lines). All three are pure view state and never refetch. The `LanguageSwitcher` writes the shared
`localStorage['fip-language']`; `buildMatrix` is a `computed` over the FIPs, model, FERs, FER types and locale, so a language change
re-derives from the cached model. Texts, titles, labels and notes resolve through `lib/lang.ts`; a FIP's own `language` is irrelevant here —
the reader's locale wins. `src/assets/print-matrix.css`, imported by the view, sets `@page { size: A3 landscape; margin: 10mm }`; hides
`.app-header`, `.app-nav` and `.no-print` (toggles, print button, switcher); makes the scroll wrapper `overflow: visible`; sets
`table{width:100%;font-size:7pt;table-layout:fixed}`, `thead{display:table-header-group}` (FIP names repeat on page 2) and
`tbody{break-inside:avoid}`; gives chips a 1 px border and pale fill; forces the legend visible. Target: 8 columns × 21 rows on one A3 sheet.

### 1.5 i18n keys to add (English values; pt-PT / pt-BR go to the translator agent)

```text
matrix: title "Comparison matrix" · subtitle "{fips} FIPs · {questions} questions" · question "Question" · convergence "Convergence" ·
  convergenceHint "Distinct resources declared as currently used, across the FIPs of this session." · agreed "All groups agree" ·
  distinct "{count} distinct" · mostCommon "{label} ({count})" · groupAgreement "{agreed} of {total} rows agree" · legend "Legend" ·
  unanswered "Not answered" · noFips "No FIPs in this session yet." · scopeMetadata "metadata" · scopeData "data" · note "Why" ·
  onlyCurrent "Only currently used" · hideUnanswered "Hide unanswered rows" · compact "Compact" · print "Print (A3 landscape)" ·
  showNote "Show reason"
export: ttl "Turtle (RDF)" · jsonld "JSON-LD" · rdfHint "FIP ontology (w3id.org/fair/fip/terms/)" · sessionTtl "All FIPs as Turtle"
```

## 2. RDF export

### 2.1 Module and namespaces

New module `backend/fipm/rdf.py` (rdflib ≥7, already a dependency), reading the FIP row directly (for the untranslated `note` LangMaps) plus
the knowledge model, and reusing `exporters.resolve_lang` and `exporters.fip_url`. Prefixes: `fip:` for `https://w3id.org/fair/fip/terms/`
and `fair:` for `https://w3id.org/fair/principles/terms/` (both verified, spec 00 §1 and §4); `dcterms:` for `http://purl.org/dc/terms/`;
`prov:` for `http://www.w3.org/ns/prov#`; plus `rdfs:` and `xsd:`; and **the extension namespace** `fipmx:` = `{FIPM_BASE_URL}/ns#` for
everything spec 00 could not verify. The `fipmx:` terms used, and only these: `has-declaration`,
`declaration-index` (an integer, order within a question), `declaration-status` (the literal FIP Manager status, so `none` and round trips
are lossless), `question-id` (questions with no ontology individual), `free-text` (boolean), `Answer` with `answer-comment`,
`Data-Management-Plan` with `dmp-version`, `dmp-system` and `dmp-question-ref`, and `Workshop-Session` with `has-fip`. The namespace document
is **not** served in v1 — the IRIs are stable but non-resolvable (§6.4).

### 2.2 IRI scheme

FIP `{base}/fips/{fipId}` (identical to `exporters.fip_url`); community `{base}/fips/{fipId}#community` (stored inline per FIP, not a shared
entity); declaration `{base}/fips/{fipId}#decl-{questionId}-{index}`, e.g. `#decl-R1.1-data-0`; answer comment
`{base}/fips/{fipId}#answer-{questionId}`, only when a comment exists; knowledge model `{base}/knowledge-models/{qid}/{qversion}`; session `{base}/sessions/{sessionId}`; catalogue FER the stored `ferId` verbatim; free-text FER `{base}/fers/text/<hash>` (§2.4).
Both `.` and `-` are legal in a fragment, so `R1.1-data` needs no escaping; any other character in a question id is percent-encoded; every
minted IRI is built from `settings.base_url` at export time (spec 01 §8.3).

### 2.3 Triples

**FIP** — `a fip:FAIR-Implementation-Profile`; `dcterms:title` = community name (lang-tagged with the FIP's language); `dcterms:license` as a
mapped IRI (`CC0-1.0` → `https://creativecommons.org/publicdomain/zero/1.0/`; `CC-BY-4.0`, `CC-BY-SA-4.0`, `CC-BY-NC-4.0` → the matching
`https://creativecommons.org/licenses/...` IRI; an unmapped string stays a plain literal, never a guessed IRI); `dcterms:created` and
`dcterms:modified` (`xsd:dateTime`, UTC); `dcterms:language`; `dcterms:conformsTo` the knowledge-model IRI;
`fip:declared-by` the community; `fipmx:has-declaration` each declaration; and each `relatedDMPs` entry as `prov:wasDerivedFrom` the DMP URL,
that URL typed `fipmx:Data-Management-Plan` with `fipmx:dmp-version` and `fipmx:dmp-system` literals.

**Community** — `a fip:FAIR-Implementation-Community` (the class spec 00 §2 verified; **no** `schema:Organization`, which spec 00 did not
verify, and never a `Mature-` or `Emerging-Community` subclass, which FIP Manager does not ask about); `dcterms:title`, `dcterms:description`,
`fip:has-research-domain` (lang-tagged), `fip:has-data-steward` as an `https://orcid.org/...` IRI when the ORCID pattern matches and
otherwise the steward name as a literal, and every `community.links` entry as `rdfs:seeAlso`.

**Declaration**, one per stored declaration in stored order — `a fip:FIP-Declaration`; `fip:declared-by` the community;
`fipmx:declaration-index`; `fipmx:declaration-status`; `fip:refers-to-question` the individual `fip:FIP-Question-<X>`, where `<X>` maps a
`-metadata` suffix to `-MD`, `-data` to `-D` and unscoped ids to themselves, **only if** the result is one of the 21 individuals of
spec 00 §4 — otherwise no `fip:refers-to-question` and a `fipmx:question-id` literal instead (the from-scratch-model path of PLAN §5);
`fip:refers-to-principle` the `fair:` (sub)principle when `principle` matches `^[FAIR]\d(\.\d)?$`; and the resource link per status:
`current` → `fip:declares-current-use-of`, `planned` → `fip:declares-planned-use-of`, `planned-development` →
`fip:declares-planned-development-of`, `planned-replacement` → `fip:declares-planned-replacement-of`, and `none` → **no** `declares-*`
predicate, the declaration additionally typed `fip:FIP-No-Choice-Declaration` and any FER dropped. `planned-replacement` does **not**
auto-emit `fip:declares-planned-use-of`: spec 00 §2 wants that on the *successor*, which here is a second, separate `planned` declaration
(the spec 02 §2.2 hint). The `note` LangMap becomes one lang-tagged `fip:considerations` literal **per key**, untranslated — the only
multilingual part of the export; a `dmpEvidence` becomes `prov:wasDerivedFrom` the DMP URL plus a `fipmx:dmp-question-ref` literal.

**Answer comment** — a node `#answer-<qid>` typed `fipmx:Answer`, carrying `fip:refers-to-question`, `fipmx:question-id` and the comment as a
lang-tagged `fipmx:answer-comment`; emitted only for a non-empty comment. Unanswered questions emit **nothing** (unlike the JSON and CSV
exports, which pad them): a graph states what is declared.

**Knowledge model and attribution** — `dcterms:title`, `dcterms:hasVersion`, `dcterms:source`, `dcterms:license`, and when the model's
`license` starts with `CC-BY-SA`, the spec 00 §6 string as `dcterms:rights` plus `dcterms:creator` for the two verified ORCIDs
(`0000-0001-8888-635X`, `0000-0003-2195-3997`) with "Jacintha Schultes" as a literal (no ORCID verified). The FIP Ontology's own CC0 credit is
a Turtle **comment header**, not a triple: a claim about the vocabulary, not about this graph. `fip:has-declaration-index` is **not** emitted —
spec 00 §5 shows it pointing at a container whose collection semantics are unverified, and `fipmx:has-declaration` with
`fipmx:declaration-index` carries the same information without inventing meaning (§6.1).

### 2.4 Free-text FERs

A declaration with `ferFreeText` gets a **hash IRI**, not a blank node: `{base}/fers/text/<hash>`, where the hash is the first 16 hex
characters of the SHA-256 of the normalised text (NFC → strip → collapse internal whitespace → casefold). The node carries
`a fip:FAIR-Enabling-Resource`, the question's FER-type class (`fip:` plus the local name from `data/fers/fer-types.json`, e.g.
`fip:Structured-vocabulary`) when `ferType` is set, an `rdfs:label` with the original text and the FIP's language tag, and a
`fipmx:free-text` flag. A hash IRI beats a blank node because two groups typing the same wording collapse to one node in the session graph
(the convergence the matrix shows), and blank nodes would break AC 8. Catalogue FERs likewise get `a fip:FAIR-Enabling-Resource`, their FER-type class and an `rdfs:label` per language key of the stored LangMap.

### 2.5 Endpoints

| Method | Path | Auth | Returns | Codes |
|---|---|---|---|---|
| GET | `/api/fips/{id}/export.ttl` | – / U / T (as `export.json`) | `text/turtle; charset=utf-8`, `attachment; filename="{id}.ttl"` | 200, 404 |
| GET | `/api/fips/{id}/export.jsonld` | – / U / T | `application/ld+json`, `attachment; filename="{id}.jsonld"` | 200, 404 |
| GET | `/api/sessions/{id}/export.ttl` | U (owner or admin) | one graph with every FIP of the session | 200, 401, 404 |

The two FIP routes replace the `501` stub in `routers/fips.py` and reuse `_get_readable_fip` verbatim (assumption A2). The session route
reuses `_get_owned_session` (which already admits admins) and orders FIPs by `created_at` like the other session exports; its graph adds the
session IRI typed `fipmx:Workshop-Session` with `dcterms:title`, `dcterms:created` and one `fipmx:has-fip` per FIP; no session JSON-LD in v1.
The `rdf.py` API is `fip_graph(db, fip, settings)`, `session_graph(db, session, fips, settings)`, `to_turtle(g)` and `to_jsonld(g)`
(`g.serialize(format="json-ld", context=JSONLD_CONTEXT, indent=2, auto_compact=True)`) — one `Graph` with the §2.1 prefixes bound, so Turtle
and JSON-LD are the same triples.

### 2.6 JSON-LD context, emitted inline as `@context`

```json
{"fip": "https://w3id.org/fair/fip/terms/", "fair": "https://w3id.org/fair/principles/terms/", "fipmx": "{base}/ns#",
 "dcterms": "http://purl.org/dc/terms/", "prov": "http://www.w3.org/ns/prov#", "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
 "xsd": "http://www.w3.org/2001/XMLSchema#", "id": "@id", "type": "@type", "label": {"@id": "rdfs:label"},
 "title": {"@id": "dcterms:title"}, "considerations": {"@id": "fip:considerations"}, "declarationStatus": {"@id": "fipmx:declaration-status"}, "created": {"@id": "dcterms:created", "@type": "xsd:dateTime"}, "modified": {"@id": "dcterms:modified", "@type": "xsd:dateTime"},
 "declarationIndex": {"@id": "fipmx:declaration-index", "@type": "xsd:integer"}, "license": {"@id": "dcterms:license", "@type": "@id"},
 "conformsTo": {"@id": "dcterms:conformsTo", "@type": "@id"}, "declaredBy": {"@id": "fip:declared-by", "@type": "@id"},
 "hasDeclaration": {"@id": "fipmx:has-declaration", "@type": "@id"}, "refersToQuestion": {"@id": "fip:refers-to-question", "@type": "@id"},
 "refersToPrinciple": {"@id": "fip:refers-to-principle", "@type": "@id"}, "currentUseOf": {"@id": "fip:declares-current-use-of", "@type": "@id"},
 "plannedUseOf": {"@id": "fip:declares-planned-use-of", "@type": "@id"}, "plannedDevelopmentOf": {"@id": "fip:declares-planned-development-of", "@type": "@id"},
 "plannedReplacementOf": {"@id": "fip:declares-planned-replacement-of", "@type": "@id"}}
```

### 2.7 Turtle example — one FIP, two answers

```turtle
# FIP exported by FIP Manager. Ontology terms: FIP Ontology (https://w3id.org/fair/fip/terms/), CC0 1.0.
# Questionnaire content: FIP mini-questionnaire v2.0.0, CC BY-SA 4.0, GO FAIR Foundation. `this:` = the FIP's own fragment namespace.
@prefix fip: <https://w3id.org/fair/fip/terms/> .   @prefix fair: <https://w3id.org/fair/principles/terms/> .
@prefix dcterms: <http://purl.org/dc/terms/> .      @prefix prov: <http://www.w3.org/ns/prov#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .  @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix fipmx: <https://fipm.example.org/ns#> .     @prefix this: <https://fipm.example.org/fips/7Q2M8XKD#> .
<https://fipm.example.org/fips/7Q2M8XKD> a fip:FAIR-Implementation-Profile ;
    dcterms:title "CONFOA 2026 grupo A"@pt-BR ; dcterms:language "pt-BR" ; dcterms:license <https://creativecommons.org/publicdomain/zero/1.0/> ;
    dcterms:created "2026-10-06T09:12:03+00:00"^^xsd:dateTime ; dcterms:modified "2026-10-06T09:41:55+00:00"^^xsd:dateTime ;   # rdflib normalises Z to +00:00
    dcterms:conformsTo <https://fipm.example.org/knowledge-models/gofair-fip-mini/1.0.0> ; fip:declared-by this:community ;
    fipmx:has-declaration this:decl-F1-data-0 , this:decl-I2-metadata-0 ;
    prov:wasDerivedFrom <https://fiodmp.fiocruz.br/KQU5N0C> .
<https://fiodmp.fiocruz.br/KQU5N0C> a fipmx:Data-Management-Plan ; fipmx:dmp-version "13" ; fipmx:dmp-system "FioDMP" .
this:community a fip:FAIR-Implementation-Community ; dcterms:title "CONFOA 2026 grupo A"@pt-BR ;
    dcterms:description "Saúde pública, dados de vigilância."@pt-BR ; fip:has-research-domain "Saúde pública"@pt-BR ;
    fip:has-data-steward <https://orcid.org/0000-0002-1825-0097> .
<https://fipm.example.org/knowledge-models/gofair-fip-mini/1.0.0> dcterms:title "FIP mini-questionnaire"@en ; dcterms:hasVersion "1.0.0" ;
    dcterms:source "GO FAIR FIP mini-questionnaire" ; dcterms:license <https://creativecommons.org/licenses/by-sa/4.0/> ;
    dcterms:rights "FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, Barbara Magagna, Jacintha Schultes / GO FAIR Foundation, CC BY-SA 4.0." ;
    dcterms:creator <https://orcid.org/0000-0001-8888-635X> , <https://orcid.org/0000-0003-2195-3997> , "Jacintha Schultes" .
# status = current, catalogue FER
this:decl-F1-data-0 a fip:FIP-Declaration ; fip:declared-by this:community ; fipmx:declaration-index 0 ;
    fip:refers-to-question fip:FIP-Question-F1-D ; fip:refers-to-principle fair:F1 ;
    fip:declares-current-use-of <https://www.doi.org/> ; fipmx:declaration-status "current" .
<https://www.doi.org/> a fip:FAIR-Enabling-Resource , fip:Identifier-service ; rdfs:label "DOI"@en .
# status = planned-development, free-text FER, with a consideration and a question comment
this:decl-I2-metadata-0 a fip:FIP-Declaration ; fip:declared-by this:community ; fipmx:declaration-index 0 ;
    fip:refers-to-question fip:FIP-Question-I2-MD ; fip:refers-to-principle fair:I2 ; fipmx:declaration-status "planned-development" ;
    fip:declares-planned-development-of <https://fipm.example.org/fers/text/55c036a2b284564b> ;
    fip:considerations "Nenhum vocabulário publicado cobre o domínio."@pt-BR .
<https://fipm.example.org/fers/text/55c036a2b284564b> a fip:FAIR-Enabling-Resource , fip:Structured-vocabulary ;
    rdfs:label "Ministério da Saúde vocabulary"@pt-BR ; fipmx:free-text true .
this:answer-I2-metadata a fipmx:Answer ; fip:refers-to-question fip:FIP-Question-I2-MD ;
    fipmx:question-id "I2-metadata" ; fipmx:answer-comment "Decidir com a equipa de terminologia."@pt-BR .
```

## 3. Frontend export buttons (nothing else)

`components/ExportButtons.vue` (spec 02 §2.4) gains two `<a download>` links, to `export.ttl` and `export.jsonld`, labelled `export.ttl` and
`export.jsonld` with `export.rdfHint` as their `title`, exactly like the existing JSON and CSV links. It appears, unchanged in behaviour, on
**`FipRead.vue`**, in the **`FipEditor.vue`** share panel, and on **`SessionDetail.vue`**, where "Export all" gains one more link to
`/api/sessions/{id}/export.ttl` labelled `export.sessionTtl`. `.no-print` as before. No new view, no RDF rendering in the browser.

## 4. Acceptance criteria

**Backend — pytest, `backend/tests/`**

1. `GET /api/fips/{id}/export.ttl` returns 200 `text/turtle`; the body parses with `rdflib.Graph().parse(format="turtle")` and
   `{base_url}/fips/{id}` is a subject typed `fip:FAIR-Implementation-Profile`.
2. For a FIP with 5 stored declarations over 3 questions (one of each status) the graph has **exactly 5** subjects typed
   `fip:FIP-Declaration` — one per stored declaration — each with exactly one `fip:declares-*` triple using the predicate spec 00 §2 demands,
   and **no** `fip:declares-planned-use-of` on the `planned-replacement` one.
3. The `none` declaration is typed both `fip:FIP-Declaration` and `fip:FIP-No-Choice-Declaration`, carries no `fip:declares-*` triple, and
   still carries a `fipmx:declaration-status` of `none`.
4. A declaration with `ferFreeText` "Ministério da Saúde vocabulary" yields one IRI under `{base}/fers/text/` whose `rdfs:label` is that exact
   text with the FIP's language tag, typed both `fip:FAIR-Enabling-Resource` and the question's FER-type class, and carrying a
   `fipmx:free-text` flag; two FIPs using that wording up to case and whitespace yield **one** such node in a session graph.
5. A `note` LangMap with `en` and `pt-BR` keys yields two `fip:considerations` literals with those tags; a question comment yields exactly one
   `fipmx:answer-comment`; a question with no answer contributes no triple.
6. `GET /api/sessions/{id}/export.ttl` as owner of a session with 3 FIPs returns 200 and a graph holding all 3 FIP IRIs as
   `fip:FAIR-Implementation-Profile` subjects plus the session IRI typed `fipmx:Workshop-Session` with 3 `fipmx:has-fip` triples, its triple
   count equalling the union of the three single-FIP graphs (shared FER and knowledge-model nodes deduplicated).
7. `GET /api/sessions/{id}/export.ttl` returns **404** for another signed-in user, **401** for an anonymous client and 200 for a non-owning
   admin; a `private` FIP's `export.ttl` is 404 for a non-owner and 200 for its owner and for a valid `X-Edit-Token` holder.
8. `GET /api/fips/{id}/export.jsonld` returns 200 `application/ld+json`, valid JSON with an `@context`, and parsing it with rdflib as
   JSON-LD gives the **same triple count** as, and a graph isomorphic to (`rdflib.compare.isomorphic`), the same FIP's Turtle.
9. Every minted IRI starts with `settings.base_url`: re-running with `FIPM_BASE_URL=https://other.example` changes every minted IRI and
   nothing else (declaration count, predicates and literals identical).

**Frontend — vitest, `npm run test:unit`**

10. `buildMatrix` against a fixture of the real `gofair-fip-mini-1.0.0` model and **3 FIPs** returns 4 groups (`F/A/I/R`) totalling **21**
    rows in knowledge-model order, 3 columns in `createdAt` order with labels truncated to 24 chars, one cell per (row, column),
    `unanswered: true` exactly where there are no declarations, and notes and comments resolved by `resolveLang` for the switched locale.
11. Convergence on that fixture: a row where two FIPs declare DOI as `current` and one declares Handle gives `declaringFips` 3,
    `distinctCurrent` 2, `topLabel` "DOI", `topCount` 2 and `agreed` false; all three declaring DOI gives `distinctCurrent` 1 and `agreed`
    true; free-text currents differing only in case and a trailing space give `distinctCurrent` 1; `planned`/`none` never count; and group
    counters equal the number of rows with `agreed`.
12. `MatrixCell.vue` renders one chip per declaration carrying the class `status-current`, `status-planned`, `status-planned-development`,
    `status-planned-replacement` or `status-none` **and** the status text in each chip; an unanswered cell renders the `status-unanswered`
    placeholder; the three toggles change chip and row counts as §1.4 says (a row with gaps is never hidden).
13. `src/assets/print-matrix.css` exists, is imported by `SessionMatrix.vue`, and contains the A3-landscape `@page` rule, the
    `table-header-group` `thead` rule and a `.no-print` rule; a snapshot asserts toggles, print button and switcher carry `no-print`.

## 5. Assumptions (facilitators away; revisit at the 12 Sep scope freeze)

- **A1. The matrix is owner/admin-only in v1.** No public or join-code room view; the room sees it on the projector, driven by the
  facilitator. A read-only `/sessions/:id/room` for participants' phones is a v2 option needing a new endpoint (today's returns full FIPs).
- **A2. A FIP's RDF is exportable whenever the FIP is readable by the caller** — the same rule as `export.json` and `export.csv`, `link`
  visibility and the `X-Edit-Token` path included; RDF withholds nothing the JSON export shows and shows nothing it withholds.
- **A3. `fipmx:` is `{FIPM_BASE_URL}/ns#`, not resolvable in v1.** If hosting moves (PLAN §9.3), already exported files keep the old base —
  acceptable: those terms are tool bookkeeping, not FAIR vocabulary.
- **A4. `considered` stays out** (spec 00 §2); nothing here can express it.
- **A5. Unanswered questions produce no triples.** A consumer must not read absence as "no choice"; status `none` is the explicit form.

## 6. Open questions

1. `fip:has-declaration-index` exists, and spec 00 §5 uses it with a container object whose collection semantics are unverified, so §2.3
   emits `fipmx:has-declaration` instead. Worth asking Erik Schultes or Barbara Magagna before the workshop: if they confirm an `rdf:Seq`-like
   index node, the extension property can go.
2. Session Turtle as one merged graph (as specified) or TriG with one named graph per FIP? Merged is what the projector conversation needs;
   named graphs would keep per-FIP provenance for nanopublications (v2).
3. Convergence counts only `current`. Facilitators may want a second number for "current + planned" (direction of travel) — one field in
   `Convergence` and one legend line.
4. Should `{base}/ns` serve a small vocabulary document (HTML plus Turtle) so `fipmx:` IRIs resolve? Cheap, but one more artefact to sync.


## 6. Audit corrections (8 Sep 2026)

The FAIR-expert audit of the first implementation led to these changes, now normative for `fipm/rdf.py`:
- The extension vocabulary lives at a fixed IRI, `https://w3id.org/fipm/ns#` (env `FIPM_EXT_NS`), independent of the deployment base URL; only instance IRIs follow `FIPM_BASE_URL`. **Action for week 4: register the `fipm` w3id** (pull request to w3id.org) pointing at a page that documents the terms.
- `fip:refers-to-question` and `fip:declared-by` only on declaration nodes (their asserted domains); Answer/comment nodes use `fipmx:refers-to-question`; the FIP links to its community with `fipmx:declared-by-community`.
- `fip:has-research-domain` and `fip:has-data-steward` are object properties: emit IRIs (ORCID, or a minted `{fip}#data-steward` foaf:Person), and `dcterms:subject` for free-text domains.
- No-choice declarations keep their text as `fip:considerations`.
- FERs are typed `fip:Available-FAIR-Enabling-Resource` or `fip:FAIR-Enabling-Resource-to-be-Developed` according to the declaration status.
- Related DMPs are typed `dcso:DMP` (RDA DMP Common Standard).
- Product gap recorded for v2: a `planned-replacement` declaration should be able to name its successor FER (`successorFerId` / `successorFreeText`) so `fip:declares-planned-use-of` can be emitted honestly.
