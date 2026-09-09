# Spec 08 – Workshop picklists, "not applicable", multi-questionnaire sessions

Status: draft, 2026-09-09. Author: architect. Driver: the co-facilitator's didactic questionnaire
*PERFIS DE IMPLEMENTAÇÃO FAIR 2.docx* (pt-BR), which keeps the 21 GO FAIR question ids and the community
fields but turns every question into a **multi-select checklist of 4–6 concrete options per research area**
(omics demo + 10 areas), plus "Outro" (free text), "Ainda não definido" and "Não se aplica". It has no status
concept. Groups in the room each take one area; 5 of 11 area profiles exist so far and the document will change.

Four independent changes, each usable alone: **§1** suggested options on a question, **§2** a per-answer
*not applicable* flag, **§3** a session offering several questionnaires (one per area), **§4** an importer for the
.docx. §5 API list, §6 acceptance criteria, §7 assumptions taken while the facilitators are away, §8 open
questions. Deliberately unchanged: the five declaration statuses (§7 A1), the export shapes of a declaration,
`POST /api/fips` semantics, the single-FIP CSV column order, `SCHEMA_VERSION`'s additive-only rule.

## 0. Schema change (`SCHEMA_VERSION` 5 → **6**)

| Change | Shape |
|---|---|
| `workshop_sessions.questionnaire_refs` | JSON nullable — `[{"id","version","label":{lang:str}}]`, 1..12. NULL on a pre-v6 row means "derive the single-entry list from `questionnaire_id`/`questionnaire_version`", so no data migration. |

`questionnaire_id`/`questionnaire_version` **stay** and always hold `questionnaireRefs[0]` (the FK, both indices
and every existing read keep working). Everything else lives in JSON that already exists: `notApplicable` inside
`fips.answers`, the new question and model fields inside `knowledge_models.content`. One `_EXPECTED_COLUMNS`
entry (`("workshop_sessions", "questionnaire_refs", "JSON")`), no new table.

## 1. Suggested options on a question

### 1.1 Content fields

A knowledge-model question (spec 01 §3) gains two optional fields; a model gains three, siblings of `sections`:

```json
{"id": "confoa-2026-saude-publica", "version": "1.0.0",
 "defaultDeclarationStatus": "current", "compactDeclarations": true,
 "inlineFers": [{"id": "https://fipm.example.org/fers/draft/55c036a2b284564b",
                 "label": {"pt-BR": "Vocabulário do Ministério da Saúde"},
                 "type": "structured-vocabulary", "homepage": null}],
 "sections": [{"id": "F", "questions": [
   {"id": "F1-metadata", "ferType": "identifier-service",
    "suggestedFerIds": ["https://www.doi.org/", "https://www.handle.net/"],
    "allowFreeText": true}]}]}
```

| Field | Rule |
|---|---|
| `question.suggestedFerIds` | optional `string[]`, 0..12, unique, order = display order. Each is an absolute `http(s)` IRI that resolves to a `fers` row **or** to an `inlineFers` entry of the same model. |
| `question.allowFreeText` | optional bool, **default `true`**. `false` hides the picker's "Use my own wording" toggle and makes the backend reject `ferFreeText` on that question (422 `free_text_not_allowed`, checked in `fips._validate_question_ids`, which already has the model). |
| `model.inlineFers` | optional list, 0..300, of `{id, label: LangMap, type, homepage?}` — area-specific FERs a fork carries before they exist in the global catalogue. |
| `model.defaultDeclarationStatus` | optional, one of `config.DECLARATION_STATUSES`, default `current`. The status a quick-pick checkbox assigns. |
| `model.compactDeclarations` | optional bool, default `false`. §1.5. |

### 1.2 Validator (`km_content.validate_content`, mirrored in `lib/kmContent.ts`)

New rules 9–13, new codes, same `{path, code, message}` shape and the same `400 {"detail":"invalid_content","errors":[…]}` envelope:

9. `suggestedFerIds` is a list of unique absolute `http(s)` IRIs, ≤ 12 (`invalid_value`, `invalid_fer_iri`, `duplicate_suggested_fer`, `too_many`).
10. Every id resolves. `validate_content` stays pure: it gains an optional keyword `known_fer_ids: set[str] | None = None`, checks resolution against `inlineFers` ∪ `known_fer_ids`, and **skips the catalogue half when `known_fer_ids is None`**. Callers supply it — the routers from one `SELECT id FROM fers WHERE id IN (…)`, the importer from `seed.json`, the TS mirror from the picker's cached catalogue map. Unresolved → `unknown_suggested_fer`.
11. `allowFreeText`, `compactDeclarations` are bools when present; `defaultDeclarationStatus` ∈ `DECLARATION_STATUSES` (`invalid_value`).
12. `inlineFers`: ≤ 300 entries, `id` an absolute `http(s)` IRI unique within the model (`duplicate_inline_fer`), `type` one of the 12 keys of `data/fers/fer-types.json` (`unknown_fer_type`), `label` a LangMap by rule 3 **except that `en` is not required** (an area FER may be pt-BR only — `label` must simply be non-empty, code `missing_key`), `homepage` null or an absolute IRI. An id that already exists in `known_fer_ids` → `inline_fer_duplicates_catalogue` (reference it via `suggestedFerIds` instead).
13. **Publish only** (`publishing=True`): a question with `allowFreeText: false` and no `suggestedFerIds` is unanswerable → `no_answer_path`. An `inlineFers` entry no question references is *not* an error (a fork may stage FERs); the editor marks it "unused".

### 1.3 Promotion of inline FERs into the catalogue

`POST /knowledge-models/{id}/{version}/publish` and `python -m fipm import-data` both upsert every `inlineFers` entry into `fers` as `source="model"`, `owner_id = <the model's owner_id>` (NULL for a system model), `label_search` = the labels joined by `|` lowercased, exactly like `importer._upsert_fer`. An **existing** row with that id is left untouched whatever its source (never overwrite seed, `user` or `user-promoted` content) and counted in the publish response's `promotedFers: {created, skipped}`; promotion is idempotent. `GET /api/fers`'s source filter includes `"model"` for anonymous callers too — a workshop participant has no account and must still see the options their model suggests. Until promotion the picker resolves suggested labels from `km.content.inlineFers`, which it already holds, and only then from the catalogue, so the quick-pick also renders on a draft model and on the offline laptop.

### 1.4 Knowledge-model editor UI

All of it is `content` editing through the whole-document `PUT /knowledge-models/{id}/{version}/content` with
`If-Match` (spec 04 §2) — **no new endpoint**. In `components/KmQuestionCard.vue`, under the FER-type row, a
*Suggested options* block: the current ids as chips (resolved label · type · `×`) reordered with the existing
`MoveButtons.vue`; a counter `n/12`; an **Add from catalogue** search input calling
`GET /api/fers?type=<the question's ferType>&q=&limit=20` with a "show all types" checkbox (the checklists
occasionally mix types); an **Add inline FER** `<details>` sub-form (`id`, `label` through
`KmLangTabs.vue`, `type` prefilled from the question, `homepage`) that appends to `model.inlineFers` *and* to
this question's `suggestedFerIds`; an `allowFreeText` checkbox. The model settings panel gains a
`defaultDeclarationStatus` `<select>` and a `compactDeclarations` checkbox. An unused `inlineFers` entry is
listed in the settings panel with a delete button. `KmValidationList.vue` renders the new codes unchanged.

### 1.5 FER picker quick-pick and compact declarations

`FerPicker.vue` gains props `suggested: FerOut[]`, `allowFreeText?: boolean` (default `true`) and
`showSuggested?: boolean`, and a `toggleSuggested: [ferId: string, checked: boolean]` emit. Above the search
box, when `showSuggested` and `suggested.length > 0`, it renders a `<fieldset>` of checkboxes (44 px targets,
label plus homepage on a second line, `legend` = `editor.suggestedOptions`). `DeclarationEditor.vue` forwards
the emit; `QuestionCard.vue` handles it against the store: **checked** appends a declaration
`{ferId, status: km.content.defaultDeclarationStatus ?? 'current'}`; **unchecked** removes the declaration
whose `ferId` matches, asking `window.confirm(editor.dropAnnotatedDeclaration)` first if that declaration
carries a note, a `dmpEvidence`, a successor or a non-default status. The checklist belongs to the *question*,
so `QuestionCard.vue` passes `showSuggested` only to the **first** declaration row's picker, and renders one
empty declaration row when `suggestedFerIds` is non-empty and there are no declarations yet — an empty row is
already dropped from the PATCH payload (spec 02 §2.2), so the checklist is simply the first thing a
participant sees. `allowFreeText: false` hides the toggle and forces `mode = 'catalogue'`.

When `compactDeclarations: true`, `DeclarationEditor.vue` wraps `StatusSelect`, the note input and the
successor picker in a `<details>` labelled `editor.more`, closed by default, with the current status shown as a
`StatusBadge` on the summary line — colour plus text, so nothing is hidden information (spec 02 §4.3). With
`false`, the layout is byte-identical to today's. `StatusSelect.vue` itself does not change.

### 1.6 Exports

Unchanged, deliberately: the five fields are authoring aids, a declaration created by ticking a checkbox is an
ordinary declaration, and the FIP JSON, CSV, Turtle and JSON-LD emit nothing new for it. The model export
document (spec 04 §3 #7) carries all five verbatim inside `content`, so a model round-trips.

## 2. "Not applicable" per answer

### 2.1 Shape and validation

`schemas.Answer` gains `not_applicable: bool = False`; the optional note is the **existing `comment`** field
(no new field; it is already resolved, exported and RDF-emitted). A model validator rejects
`notApplicable is True and declarations` with `ValueError` → FastAPI **422**, `detail` code
`not_applicable_with_declarations` (on `POST /api/fips`, `PATCH /api/fips/{id}` and `POST /api/fips/import`).
`notApplicable: false` is never stored (the field is dropped from the payload when false, keeping old
`answers` blobs byte-identical).

### 2.2 UI, progress, matrix

`QuestionCard.vue` gains a toggle *"Não se aplica / Not applicable"* (`editor.notApplicable`) on the card
header; turning it on with declarations present confirms, then clears them, and while on the declaration rows
and "Add declaration" are hidden while the comment textarea stays, labelled `editor.notApplicableWhy`.
Progress: `lib/progress.ts` `answeredCount` counts an answer with
`declarations.length >= 1` **or** `notApplicable === true`; the backend mirror in `schemas._fip_summary` does
the same and `FipSummary` gains `notApplicable: int` (`byStatus` stays about declaration statuses only).
Matrix (`lib/matrix.ts`): `MatrixCell` gains `notApplicable: boolean` and keeps `unanswered: false` (it *is*
answered, so `hideUnanswered` keeps the row); `MatrixCell.vue` renders one distinct chip
`class="chip status-not-applicable"` with the short text **"N/A"**, the full `matrix.notApplicableFull` in
`title`/`aria-label` and a new `--color-status-not-applicable` var; `MatrixLegend.vue` gains a seventh state;
`Convergence` gains `notApplicableFips: number` (`declaringFips`, `distinctCurrent`, `agreed` untouched — N/A
is not a `current` declaration).

### 2.3 Exports

- **JSON** (spec 01 §3.1): the answer object gains `"notApplicable": true` alongside `declarations: []`.
  `POST /api/fips/import` accepts it and the round trip preserves it.
- **CSV** (26 columns, order unchanged): the question's single row carries `status` = **`not-applicable`** with
  `declaration_index`, `fer_id`, `fer_label`, `fer_free_text`, `note`, the three `dmp_*` and the two
  `successor_*` columns **empty**; `comment` as usual. `not-applicable` is a CSV rendering, never a stored
  declaration status, and is *not* added to `config.DECLARATION_STATUSES`.
- **RDF** (spec 03 §2.3), exactly: emit an answer node and nothing else —

  ```turtle
  this:answer-R1.2-data a fipmx:Answer ;
      fip:refers-to-question fip:FIP-Question-R1.2-D ;   # only when the id maps to one of the 21 individuals
      fipmx:question-id "R1.2-data" ;
      fipmx:not-applicable true ;
      fipmx:answer-comment "Não coletamos dados primários."@pt-BR .   # only when a comment exists
  ```

  **No** `fip:FIP-Declaration` node, no `fipmx:has-declaration` from the FIP, no `declares-*` predicate, no FER
  node, no `fip:FIP-No-Choice-Declaration` (that term means "no choice yet", not "the question does not
  apply"). Like today's comment-only answer nodes, the answer node is not linked from the FIP node.
  `fipmx:not-applicable` joins the closed `fipmx:` term list of spec 03 §2.1 and the JSON-LD context as
  `"notApplicable": {"@id": "fipmx:not-applicable", "@type": "xsd:boolean"}`.
- **Migration** (spec 07 §4.1): matching is by question id, so `notApplicable` is preserved when the id
  persists and lands in `orphanedAnswers` when it does not. The "answer is empty" predicate in
  `migration.py` / `migration.ts` must treat `notApplicable: true` as **non-empty**, or such answers are
  silently dropped on migration.

## 3. A session offering several questionnaires

### 3.1 Session shape

`SessionCreateRequest` gains `questionnaire_refs: list[QuestionnaireRefLabelled] | None`, 1..12, where
`QuestionnaireRefLabelled = {id, version, label: dict[str,str]}`. `questionnaire_ref` stays and stays required-ish:

- `questionnaireRefs` absent → derived as `[{**questionnaireRef, "label": <the model's title LangMap>}]`, so old clients keep working; both present and disagreeing on the first ref → **400 `questionnaire_ref_conflict`**; neither → 422.
- every ref goes through `authz.get_readable_published_km` (404/403 as today); a repeated `(id, version)` → 400 `duplicate_questionnaire_ref`; each `label` is validated with `km_content.validate_langmap` **without** the `en` requirement and capped at 80 chars per language (400 `invalid_content`, code `too_long`).

`SessionOut` and `SessionPublicOut` gain `questionnaireRefs: [{id, version, label, title}]`, where `title` is
the model's own title subject to the same anonymous-readability filter that guards `questionnaireTitle` today
(published **and** anonymously readable, else `{}`). `questionnaireRef` and `questionnaireTitle` stay populated
with the **first** ref. `SessionPatchRequest` accepts `questionnaire_refs` but only while the session has no
FIPs → otherwise **409 `session_has_fips`**, so a facilitator can still fix a label typo before the room joins.

### 3.2 Join, FIP creation, lists

`JoinSession.vue`: when `questionnaireRefs.length > 1`, a **required radio group** *"Which area?"*
(`join.chooseArea`, labels through `resolveLang`) above the community form, the choice remembered in
`localStorage['fipm.join.<sessionId>.area']`; `POST /api/fips` sends the chosen ref. Length 1 → no visual change.
`fips.create_fip`'s `questionnaire_ref_mismatch` check becomes "must equal **one of** the session's refs"; the
chosen ref goes into the FIP's existing `questionnaire_id`/`questionnaire_version` columns — **no new FIP
column**. The area *label* is never copied onto the FIP: it is looked up from the session's ref list at read
and export time, so a label fix propagates. `FipOut` gains `areaLabel: dict[str,str] | null` (non-null only for
a FIP in a multi-ref session). `SessionFipList.vue` renders it as a chip and its `answered / N` denominator
becomes per-FIP — the visible question count of *that* FIP's model, from one `GET /api/knowledge-models/{id}/{v}`
per distinct ref, cached.

### 3.3 Exports and matrix

- Session JSON: `session.questionnaireRefs` (the list) plus `area: {id, version, label}` on each embedded FIP document; `session.questionnaireRef` kept as the first ref.
- Session CSV: an **`area`** column prepended as the third prefix column → `session_id, fip_title, area, <the 26 FIP columns>`. The session prefix is its own contract and a facilitator reads the area next to the group name; the single-FIP CSV is untouched. Accepted consequence: session-CSV column indices from 3 on shift by one.
- Session TTL: unchanged. Each FIP already carries `dcterms:conformsTo` its own model, so a multi-area graph simply contains several knowledge-model nodes with their own attribution blocks; the session node keeps one `fipmx:has-fip` per FIP and gains no term.
- Matrix: `buildMatrix(fips, kms: Map<'id@version', KnowledgeModelOut>, fers, ferTypes, locale, refs)`. Columns are grouped by ref in `refs` order, then by `createdAt` within a group; `MatrixColumn` gains `refKey` and `areaLabel`, `Matrix` gains `columnGroups: [{refKey, label, columnCount}]` rendered as a second `<thead>` row of `<th colspan>` group headers (repeated on print, `thead{display:table-header-group}` already does that). Rows = the **union** of question ids over all refs, ordered by the first ref that has them; a row's `text`, `principle`, `scope` and `ferType` come from the first model that has that id (all 11 forks share the 21 ids, so in practice the base order). `MatrixRow` gains `presentIn: string[]`; a cell in a column whose model lacks the row gets `absent: true`, rendered as a hatched "—" distinct from both `unanswered` and N/A, and excluded from convergence.
- `SessionNew.vue`: a repeatable row list — model `<select>` (published, grouped System/Mine/Public per spec 04 §4) + a short label input (current editor language, ≤ 80 chars, prefilled from the model title) + remove; **Add another questionnaire** up to 12. A single-row form posts exactly what it posts today.

## 4. Importer — `scripts/import-workshop-docx.py`

Stdlib only (`zipfile`, `xml.etree.ElementTree`, `json`, `re`, `argparse`, `pathlib`, `unicodedata`, `difflib`,
`hashlib`) — no `python-docx`, no new dependency. Reads `word/document.xml` from the zip; a paragraph's text is
the concatenation of its `w:t` descendants (so split runs join), its style is `w:pPr/w:pStyle/@w:val`, namespace
`w = http://schemas.openxmlformats.org/wordprocessingml/2006/main`.

```
python3 scripts/import-workshop-docx.py --docx <path> [--base data/knowledge-models/gofair-fip-mini-1.0.0.json]
    [--map data/workshop/option-map.json] [--out data/knowledge-models] [--base-url https://fipm.example.org]
    [--report -] [--bump] [--strict] [--dry-run]
```

### 4.1 Detection

| What | Rule |
|---|---|
| Area | a paragraph whose style, accent-stripped and casefolded, is one of `ttulo1, titulo1, heading1, heading 1`. Its text is the area name; a leading `Área N –` / `Perfil …:` prefix and any trailing parenthesis are stripped. `slug = slugify(strip_accents(name))` (the rule of `km_content.slugify`), model id `confoa-2026-<slug>`. |
| Question | a paragraph whose text matches `^\s*(F[1-4](\.\d)?\|A[12](\.\d)?(\.\d)?\|I[123](\.\d)?\|R1(\.\d(\.\d)?)?)\s*[.):–-]\s*`. The captured code is looked up in the script's 21-entry `DOC_CODE_TO_QUESTION_ID` (`F1.1→F1-metadata`, `F1.2→F1-data`, `F2→F2`, `F3→F3`, `F4.1/F4.2→F4-metadata/-data`, `A1.1.1/A1.1.2→A1.1-metadata/-data`, `A1.2.1/A1.2.2→A1.2-metadata/-data`, `A2→A2`, `I1.1/I1.2`, `I2.1/I2.2`, `I3.1/I3.2`, `R1.1.1/R1.1.2`, `R1.2.1/R1.2.2` likewise). The table is asserted against the base model's question ids at start-up; a mismatch is a hard exit 2. The remainder of the paragraph, trimmed, is the pt-BR question text. |
| Option | a paragraph between a question and the next question or heading that either has a `w:numPr` (list) or starts with one of `☐ ☑ ▢ □ ○ ● - • [ ] ( )`; the glyph and leading space are stripped. Collected in document order. |
| Sentinels | after accent-stripping and casefolding: `outro(s)`/`outra(s)`/`especificar`/`other` → not a suggestion, sets `allowFreeText: true` (already the default); `ainda nao definido`/`nao definido`/`undefined` → dropped (leaving the question unanswered *is* "undefined", §7 A3); `nao se aplica`/`not applicable` → dropped, recorded in the report only, since the §2 toggle is always available. |

A question with no surviving options gets `suggestedFerIds: []`. A question the document omits keeps the base
model's text and no suggestions, and is listed in the report.

### 4.2 Option → FER matching

Normalisation `norm(s)`: NFC → strip accents (NFD, drop `Mn`) → drop parenthesised text → casefold → collapse
whitespace → strip trailing punctuation. First hit wins:

1. an entry in `data/workshop/option-map.json` keyed by `norm(option)` — the human/agent override, **always wins**, including an explicit `"ferId": null` meaning "deliberately no catalogue FER";
2. exact `norm` equality against a `seed.json` `label` value (any language key) or an `aliases` entry;
3. `norm(option)` is a prefix or suffix of, or contains as a whole-word substring, a `norm`'d label/alias — restricted to seed FERs whose `type` equals the question's `ferType` (so "Dublin Core" in "Dublin Core (DC Terms)" matches);
4. `difflib.SequenceMatcher` ratio ≥ **0.90** against a same-type label/alias, highest wins; a runner-up within **0.02** makes it **ambiguous → unresolved**, never guessed.

Steps 3 and 4 never cross FER types; steps 1 and 2 may. Resolved ids are appended to the question's
`suggestedFerIds` in document order, truncated to 12 with a report line. An unresolved option becomes an `inlineFers` draft: id `{--base-url}/fers/draft/<hash16>` where `hash16` is the
first 16 hex of the SHA-256 of `norm(option)` — the same hashing idea as the free-text FER IRIs of spec 03
§2.4, so two areas offering the same option converge on one draft IRI and one catalogue row. `type` = the
question's `ferType`, `label` = `{"pt-BR": "<the original option text>"}`, `homepage` = null. Every draft is
also written into `option-map.json` as `{"<norm>": {"ferId": null, "draftFerId": "<the IRI>", "questionId":
"...", "ferType": "...", "seen": ["<area slug>", …], "bestCandidate": {"ferId": "...", "ratio": 0.83}}}` so a
human or an agent can fill `ferId` and re-run. A real `--base-url` must be passed before publishing; with the
default placeholder host the report prints a warning line.

### 4.3 Output layout

- `data/knowledge-models/confoa-2026-<slug>-1.0.0.json` per area: a fork of the base — `status: "draft"`, `license`/`source` copied, `forkedFrom: {"id":"gofair-fip-mini","version":"1.0.0"}`, `title: {"pt-BR": "<area>", "en": "<area> (CONFOA 2026)"}` (the validator needs `en`; the report flags it for translation), `description` copied, `changelog: [{"version":"1.0.0","date":"<today>","notes":"Imported from PERFIS DE IMPLEMENTAÇÃO FAIR 2.docx (<sha256[:12]> of the .docx)"}]`, `defaultDeclarationStatus: "current"`, `compactDeclarations: true`, `inlineFers`, and the base's four sections with, per question, `text["pt-BR"]` replaced by the document wording when found, `en`/`pt-PT`/`es` and `help` **copied verbatim from the base**, plus `suggestedFerIds` and `allowFreeText: true`. Each file is run through `km_content.validate_content` (imported from `backend/`, or re-implemented shape checks when `backend/` is not importable) before being written.
- `data/workshop/option-map.json` — merged, never clobbered: resolved entries are kept as-is, new options appended, an entry whose option text has vanished from the document is kept and marked `"stale": true`. `sort_keys=True`, `indent=2`, `ensure_ascii=False`, trailing newline, so a re-run produces a readable diff or none at all.
- `data/workshop/import-report-<date>.md`, or stdout with `--report -`: per area the question count found (expect 21), options per question, every unresolved option with its draft IRI and best rejected candidate + ratio, missing questions, sentinel counts, and a totals line. Exit 0 unless `--strict`, which exits 1 on any missing question or unresolved option.
- `data/workshop/gofair-fip-mini-pt-BR-suggested.json` — `{questionId: <the document's pt-BR wording>}`. Adopting that wording as the **base** model's pt-BR text is a separate, parallel job for the translator agent: it edits a published system CC BY-SA model, so it needs version `1.0.1` with a changelog entry, not an importer side effect. **The script never touches `gofair-fip-mini-1.0.0.json`.**
- Idempotency by model id: a byte-identical re-run rewrites identical files. When a `1.0.0` file exists with a *different* content hash, `--bump` writes `confoa-2026-<slug>-1.0.1.json` and keeps the old file (a changed document becomes a new draft version, never an in-place overwrite — `import-data` would refuse the differing hash anyway, spec 01 §3.3).

## 5. API changes (complete list)

| # | Change | Auth | Codes |
|---|---|---|---|
| 5.1 | `PUT /knowledge-models/{id}/{version}/content`: accepts and validates the five new content fields (§1.1–§1.2); `errors[]` gains `duplicate_suggested_fer`, `unknown_suggested_fer`, `duplicate_inline_fer`, `inline_fer_duplicates_catalogue`, `no_answer_path` | U | 200, 400 `invalid_content`, 409, 428 |
| 5.2 | `POST /knowledge-models/{id}/{version}/publish`: promotes `inlineFers` to `fers` as `source="model"`; response gains `promotedFers: {created, skipped}` | U | 200, 400, 409 |
| 5.3 | `GET /fers`: anonymous and authenticated source filters include `"model"` | – / U | 200 |
| 5.4 | `POST /fips`, `PATCH /fips/{id}`, `POST /fips/import`: `answers[].notApplicable` accepted; both set → **422 `not_applicable_with_declarations`**; `ferFreeText` on a question with `allowFreeText: false` → **422 `free_text_not_allowed`** | – / U / T | 200, 201, 422 |
| 5.5 | `GET /fips/{id}` / `FipOut`: gains `areaLabel`, `summary.notApplicable` | – / U / T | 200 |
| 5.6 | `POST /sessions`: `questionnaireRefs` (1..12); `questionnaireRef` still accepted | U | 201, 400 `questionnaire_ref_conflict` / `duplicate_questionnaire_ref` / `invalid_content`, 404, 422 |
| 5.7 | `PATCH /sessions/{id}`: `questionnaireRefs` replaceable only while the session has no FIPs | U | 200, 409 `session_has_fips` |
| 5.8 | `GET /sessions/{id}`, `GET /sessions/by-code/{joinCode}`: gain `questionnaireRefs[]` (with per-ref `title`, anonymously-readable models only); `questionnaireRef`/`questionnaireTitle` keep the first ref | – / U | 200, 404 |
| 5.9 | `POST /fips` in a session: the ref must match **one of** the session's refs, else 400 `questionnaire_ref_mismatch` | – | 201, 400, 403, 409 |
| 5.10 | `GET /sessions/{id}/export.json` (`session.questionnaireRefs`, per-FIP `area`) and `.csv` (new third prefix column `area`) | U | 200, 404 |

Backward compatibility: a v5 database upgrades in place (§0); every pre-existing session reads as a one-ref
session; every pre-existing FIP has no `notApplicable` key and a null `areaLabel`; a model without the five new
content fields behaves exactly as today (`allowFreeText` defaults true, no quick-pick, no compact mode).

## 6. Acceptance criteria

**Backend (pytest)**
1. `validate_content` rejects 13 suggested ids, a duplicate id, a non-IRI id, and an id absent from both `inlineFers` and `known_fer_ids`, with the §1.2 codes; accepts the same document when `known_fer_ids is None`.
2. `validate_content(publishing=True)` returns `no_answer_path` for a question with `allowFreeText: false` and no suggestions, and accepts a pt-BR-only `inlineFers` label.
3. `PUT .../content` with a valid picklist model returns 200 and a new ETag; the round trip through `GET .../export.json` preserves all five new fields byte-for-byte.
4. Publishing a model with two `inlineFers` creates two `fers` rows with `source="model"` and `owner_id` = the model owner, reports `{created: 2, skipped: 0}`, and a second publish reports `{created: 0, skipped: 2}` without touching the rows; a seed row with the same id is never overwritten.
5. `GET /api/fers` as an anonymous caller returns `source="model"` rows.
6. `PATCH /api/fips/{id}` with `notApplicable: true` **and** a declaration → 422 `not_applicable_with_declarations`; with the flag alone → 200, and `summary.answeredQuestions` counts that question.
7. `ferFreeText` on a question with `allowFreeText: false` → 422 `free_text_not_allowed`; the same payload on a question with the field absent → 200.
8. A FIP with one N/A answer exports: JSON with `notApplicable: true` and `declarations: []`; CSV with exactly one row for that question, `status == "not-applicable"` and the 8 named columns empty; Turtle containing `fipmx:not-applicable true` on `#answer-<qid>` and **no** `fip:FIP-Declaration`, `fipmx:has-declaration` or `declares-*` triple for it. `POST /api/fips/import` of that JSON reproduces the flag.
9. Migrating a FIP with an N/A answer to a new model version preserves the flag when the question id persists and moves it to `orphanedAnswers` when it does not.
10. `POST /api/sessions` with three labelled refs returns them in order; `questionnaireRef` echoes the first; a duplicate ref → 400, a conflicting `questionnaireRef` → 400, a 90-char label → 400.
11. `POST /api/sessions` with only `questionnaireRef` (a pre-v6 client body) still returns 201 and a one-entry `questionnaireRefs` labelled with the model's title.
12. `POST /api/fips` into a three-ref session succeeds for the second ref and 400s for an unlisted one; `PATCH /api/sessions/{id}` replacing the refs 409s `session_has_fips` once one FIP exists.
13. `GET /api/sessions/{id}/export.csv` for a two-area session has `area` as its third column, the right label per row, and the 26 FIP columns after it; `export.json` carries `session.questionnaireRefs` and a per-FIP `area`. `init_db()` on a v5 SQLite file adds `questionnaire_refs` and reports version 6.

**Frontend (vitest, `†` = manual on a phone)**
14. `matrix.ts`: an N/A answer yields a cell with `notApplicable: true`, `unanswered: false`, one chip, and does not change `distinctCurrent`; `buildMatrix` over two models produces two `columnGroups`, a union row list, and `absent: true` cells for a model missing a row.
15. `kmContent.ts` mirrors AC 1 and AC 2 exactly (same codes, same paths) for the same fixtures.
16. `FerPicker.vue` renders a checkbox per suggestion above the search box, emits `toggleSuggested`, and hides the free-text toggle when `allowFreeText: false`; `QuestionCard.vue` adds a declaration with the model's `defaultDeclarationStatus` on check and confirms before dropping an annotated one. `†` With `compactDeclarations: true` the status control sits behind "more" with the status still visible as a badge, and a 21-question area profile is answerable one-thumbed.
17. `†` `JoinSession.vue` shows the area radio group only for a multi-ref session, remembers the choice, and the created FIP conforms to the chosen model; `SessionNew.vue` creates a 3-area session and `SessionMatrix.vue` prints it on one A3 sheet with group headers.

**Importer (pytest, synthetic .docx built in the test with `zipfile`)**
18. A fixture zip with `[Content_Types].xml` + `word/document.xml` holding 2 areas × 2 questions × (2 known options + 1 unknown + "Outro" + "Não se aplica") produces two valid model files (each passing `validate_content` with `known_fer_ids` from `seed.json`), resolves the known options to the right seed IRIs, mints one shared draft IRI for the unknown option seen in both areas, sets `allowFreeText: true`, drops both sentinels, writes an `option-map.json` whose unresolved entry has `"ferId": null` plus `draftFerId`/`bestCandidate`, and reports 2 missing-question warnings per area; a second run is byte-identical, `--bump` after an edited fixture writes `-1.0.1.json` and keeps `-1.0.0.json`, `--strict` exits 1, and `DOC_CODE_TO_QUESTION_ID` covers exactly the base model's 21 ids (ambiguity at ratio 0.89/0.90/0.91 asserted).

## 7. Assumptions (facilitators away; revisit at the 12 Sep scope freeze)

**A1** The five statuses stay; the document's absence of a status concept is handled by
`defaultDeclarationStatus: "current"` + `compactDeclarations: true`, so a group that never opens "more"
produces a FIP of `current` declarations — a defensible reading of "we use this". **A2** N/A is a per-question
flag, not a sixth status: the ontology has no term for it, it must exclude declarations, and as a status it
would have to export as a `declares-*` predicate. **A3** "Ainda não definido" means *unanswered*, not a stored
value; making it visible in the matrix would be a `status: "none"` declaration, a one-line importer change.
**A4** The 11 areas are 11 forked models sharing the 21 ids, not one model with an area dimension — forks are
what the editor, versioning, `conformsTo` and migration already understand. **A5** The document will change,
so everything is re-importable, idempotent by model id, a changed document becoming a new draft version.
**A6** Area labels live on the session, not the FIP, so a typo is fixed once. **A7** Area and inline-FER
`label` LangMaps do not require `en` (the source is pt-BR only); question and section texts still do.

## 8. Open questions

1. Do the facilitators want the status control visible by default in the room (`compactDeclarations: false`), or hidden as assumed in A1?
2. Should "Ainda não definido" be a stored `status: "none"` declaration instead of an unanswered question (A3)?
3. One session with 11 area questionnaires, or 11 sessions with one each? §3 supports both; the matrix is only comparable within one session, which argues for one.
4. Are the pt-BR option texts authoritative enough to promote the resulting draft FERs into the global catalogue after the workshop, or should `source="model"` rows stay unlisted until an admin curates them?
5. Who owns the 6 area profiles that do not exist yet, and is the 6 Oct deadline for all 11 or for the 5 that exist?
6. `gofair-fip-mini` 1.0.1 with the document's pt-BR wording: does replacing a CC BY-SA translation need GO FAIR's sign-off, or is a changelog note enough?
