# Spec 04 – Knowledge-model editor

Status: approved for implementation, 2026-09-08. Covers ROADMAP week 3 item 2, the last v1 feature (PLAN §2 goal 2, §5 v1 "Knowledge model
editor", §9 items 7–8). Authority: `01-foundations.md` §2 (table), §3 (content shape), §5 (authz), §6 (API); `00-fip-ontology-mapping.md`
(FER types, the 21 question ids, CC BY-SA obligations); `03-matrix-and-rdf.md` (matrix and RDF, whose untagged-question behaviour this spec
pins down). **No DB migration**: `SCHEMA_VERSION` stays 1, no new table, no new column — everything new lives inside the existing
`knowledge_models.content` JSON. The §3.1/§3.2 FIP export shapes do not change.

## 1. Lifecycle

**System models.** `owner_id IS NULL`, `visibility="public"`, loaded by the importer from `data/knowledge-models/*.json`
(`gofair-fip-mini` 1.0.0). Read-only for everyone except `admin`; a non-admin write of any kind returns **403 `system_model_readonly`**.
They are never edited in place (assumption A2): the GO FAIR text on disk and in the DB stay byte-identical, and `import-data` keeps working.

**Three ways a user model starts**, each creating exactly one row with `owner_id = caller`, `version = "1.0.0"`, `status = "draft"`,
`visibility = "private"`:
- **fork** of any readable model version (system, own, public): copies `content` verbatim, then sets `id`, `version`, `status`, drops
  `changelog` to `[]`, and records `content.forkedFrom = {"id": <src id>, "version": <src version>}`. Licence inheritance: if the source
  `license` starts with `CC-BY-SA`, the fork keeps `license = "CC-BY-SA-4.0"`, keeps the source's `source` object, and gets
  `content.attribution = "FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, Barbara Magagna, Jacintha Schultes / GO FAIR Foundation,
  CC BY-SA 4.0."` (spec 00 §6) — automatic, not a user choice. Any other source licence copies through unchanged.
- **from scratch**: `license = "CC0-1.0"`, `source = "FIP Manager"`, `sections = []`, no `forkedFrom`, no `attribution`.
- **import**: the request body is a spec 01 §3 document; `sections` are taken verbatim, `id`/`version`/`status`/`owner` are assigned by the
  server (a document's own `id`/`version`/`status` are ignored, never trusted), `license`/`source`/`title`/`description`/`changelog` copied.

**Model ids** are global (composite pk `(id, version)`), pattern `^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])$`. The caller may pass `id`; an
already-used id returns **409 `model_id_taken`**. Default when omitted: fork → `<sourceId>-fork`, then `-fork-2`, `-fork-3`… ; scratch and
import → slug of `title.en` (lowercased, non-alphanumerics to `-`, trimmed to 48 chars), same numeric suffix rule; fall back to
`model-<6 chars of Crockford base32>`.

**Draft.** Editable in place: `PATCH` metadata, `PUT` content, `DELETE`. At most **one draft per model id** (409 `draft_exists`); a draft is
never referenceable by a FIP because `authz.get_readable_published_km` requires `status="published"` — that gate stays as is.

**Publish.** `POST …/publish` with non-empty `notes`. Sets `status="published"`, `content.status="published"`, appends
`{"version": <version>, "date": <UTC date>, "notes": <notes>}` to `changelog` (and to `content.changelog`), recomputes `content_sha256`.
It creates **nothing else** — no new row, no copy. Publishing a model whose content fails validation returns 400 `invalid_content`.

**New version.** `POST …/new-version` on a **published** version (else 409 `not_published`) with `bump ∈ {minor, patch, major}` (default
`minor`) or an explicit `version` that must be strictly greater by semver (else 400 `version_not_greater`). Creates a new row: copied
`content` with the new `version` and `status="draft"`, `changelog` carried over, `visibility` and `license` inherited, `forkedFrom`
preserved. 409 `draft_exists` if this model already has a draft.

**Published versions are immutable** except `visibility` and ownership: `PATCH` on a published row accepts **only** `visibility`
(title/description/content changes are 409 `model_published`); ownership changes only through admin action and account deletion.

**Delete.** `DELETE …/{id}/{version}`: a draft → 204. A published version referenced by at least one `fips` row or `workshop_sessions` row
(match on `questionnaire_id` + `questionnaire_version`) → **409 `model_in_use`**. An unreferenced published version → 204. System model →
403 `system_model_readonly`.

**Deleting a user with owned models** (extends spec 01 §6 `DELETE /auth/me`, which already anonymises FIPs): owned **published** versions are
anonymised — `owner_id = NULL`, `visibility = "public"` — so every FIP that references them keeps resolving and they become read-only
community content; owned **drafts** are deleted outright (nothing can reference them). Nothing cascades to FIPs.

## 2. Editing a draft

All operations are transformations of the whole `content` document, implemented once as pure functions in
`frontend/src/lib/kmContent.ts` and validated on both sides (§3.3):

| Operation | Rule |
|---|---|
| edit texts | `title`, `description`, `sections[].title`, `questions[].text`, `questions[].help`, per language key. Writing an empty string deletes the key (never store `""`); `en` may not be deleted. |
| hide / unhide | sets or removes `question.hidden = true`. The question **stays in `content`**, keeps its id, and is skipped by questionnaires, exports and progress (§4). Unhiding restores it and any answers already stored on FIPs. |
| reorder | move a section or a question one step up/down within its parent. Cross-section moves are v2. |
| add question | `{id, principle?, scope?, text, help?, ferType?, required, allowMultiple}`; `id` pattern `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`, unique in the model; defaults `principle=null`, `scope=null`, `ferType=null`, `required=false`, `allowMultiple=true`. Appended to the chosen section. |
| split | on a question whose id ends in neither `-metadata` nor `-data` (else 400 `cannot_split`): replaces it, in place, with `<id>-metadata` (`scope:"metadata"`) and `<id>-data` (`scope:"data"`), both copying `text`, `help`, `principle`, `ferType`, `required`, `allowMultiple`. Collision with an existing id → 400 `duplicate_question_id`. |
| change FER type | any of the 12 keys of `data/fers/fer-types.json`, or `null`. |
| delete question / section | allowed on a draft, i.e. always (published rows reject every content write). Old FIPs are untouched: they answer the version they were created with. |
| missing translations | never blocked. The editor shows the `pt-PT ⇄ pt-BR → en` fallback in grey with a "missing" marker and counts it in the completeness meter (§5). |

**Granularity decision — whole-content `PUT` with an `If-Match` ETag, not per-operation endpoints.** The editor already holds the entire
document (the GO FAIR model is ~60 kB and the client fetched it to render), so ten operation endpoints plus a reorder protocol would add
API surface, tests and drift for no information the client lacks. Optimistic concurrency is what a document edit actually needs, and
`content_sha256` is already stored, so the ETag is free and detects the only real hazard: the same draft open in two tabs.

## 3. API

Prefix `/api`, auth column per spec 01 §6 (`–` public, `U` user, `A` admin). Bodies camelCase, errors `{"detail": "<snake_case_code>"}`.
Content-validation failures additionally carry `errors` (§3.3) — additive, `detail` stays a code. Routes replace the five `501` stubs in
`backend/fipm/routers/knowledge_models.py`; `/import` must stay declared **before** the `/{km_id}/{version}` routes.

| # | Method | Path | Auth | Request → Response | Codes |
|---|---|---|---|---|---|
| 1 | GET | `/knowledge-models` | – / U | unchanged filter (published+public, plus all of the caller's own); `?status&q&mine`. Summary gains `ownerId`, `isSystem`, `questionCount` (non-hidden), `forkedFrom` | 200 |
| 2 | GET | `/knowledge-models/{id}/versions` | – / U | unchanged (version, status, changelog) | 200, 404 |
| 3 | GET | `/knowledge-models/{id}/{version}` | – / U | unchanged body + header `ETag: "<content_sha256>"` | 200, 404 |
| 4 | POST | `/knowledge-models` | U | `{id?, title: LangMap, description?: LangMap, license?, sections?}` → `KnowledgeModelOut` (draft 1.0.0) | 201, 400, 409, 422 |
| 5 | POST | `/knowledge-models/{id}/{version}/fork` | U | `{newId?, title?: LangMap}` → new draft | 201, 400, 404, 409 |
| 6 | POST | `/knowledge-models/import` | U | `{id?, document: <spec 01 §3 doc>}` → new draft | 201, 400, 409, 413 |
| 7 | GET | `/knowledge-models/{id}/{version}/export.json` | – / U | the spec 01 §3 document (server-side fields authoritative), `Content-Disposition: attachment; filename="{id}-{version}.json"` | 200, 404 |
| 8 | PATCH | `/knowledge-models/{id}/{version}` | U | `{title?, description?, visibility?}`; on a published row only `visibility` | 200, 400, 403, 404, 409 |
| 9 | PUT | `/knowledge-models/{id}/{version}/content` | U | header `If-Match: "<etag>"` **required**; body `{sections, title?, description?}` → 200 `KnowledgeModelOut` + new `ETag` | 200, 400, 403, 404, 409, 428 |
| 10 | POST | `/knowledge-models/{id}/{version}/publish` | U | `{notes: str (1–2000, required)}` → published row | 200, 400, 403, 404, 409, 422 |
| 11 | POST | `/knowledge-models/{id}/{version}/new-version` | U | `{bump?: "minor"\|"patch"\|"major", version?}` → new draft | 201, 400, 403, 404, 409 |
| 12 | DELETE | `/knowledge-models/{id}/{version}` | U | – | 204, 403, 404, 409 |

Codes, exactly: not readable by the caller → **404 `not_found`** (spec 01 §5: private ids must not leak); readable but not owned →
**403 `forbidden`**, or `403 system_model_readonly` when `owner_id IS NULL`; content write on a published row → **409 `model_published`**;
`If-Match` absent → **428 `if_match_required`**; `If-Match` stale → **409 `content_conflict`** with body
`{"detail": "content_conflict", "etag": "<current>"}`; anonymous on any `U` route → 401. Import body capped at 2 MB (413 `payload_too_large`).

### 3.3 Content validation (`backend/fipm/km_content.py`, mirrored in `frontend/src/lib/kmContent.ts`)

One function `validate_content(doc) -> list[ContentError]`, `ContentError = {path, code, message}` with `path` in JSON-pointer-ish dot form
(`sections[2].questions[5].id`). The API answers `400 {"detail": "invalid_content", "errors": [...]}` (max 50 entries). The importer's
`_validate_knowledge_model` is replaced by a call to this module so disk and API agree. Rules:

1. `sections` is a list; each section has `id` (pattern as question ids) and a `questions` list; section ids unique. (`missing_key`,
   `invalid_id`, `duplicate_section_id`)
2. Question ids match `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$` and are **unique across the whole model**, not per section.
   (`invalid_id`, `duplicate_question_id`)
3. Every LangMap (`title`, `description`, section `title`, question `text`, and `help` when present) is an object of `str -> non-empty str`
   whose keys are within `{en, pt-PT, pt-BR}` and **contains `en`**. (`missing_en`, `unknown_language`, `empty_string`)
4. `ferType` is `null` or one of the 12 keys in `data/fers/fer-types.json` (loaded via `fipm.fer_types.get_fer_types`). (`unknown_fer_type`)
5. `principle` is `null` or one of the whitelist `F1 F2 F3 F4 A1 A1.1 A1.2 A2 I1 I2 I3 R1 R1.1 R1.2 R1.3`. (`unknown_principle`)
6. `scope ∈ {"metadata", "data", null}`; `required`, `allowMultiple`, `hidden` are booleans when present. (`invalid_value`)
7. Limits: ≤ 50 sections, ≤ 300 questions, each text ≤ 4000 chars. (`too_many`, `too_long`)
8. At least one non-hidden question is required **to publish** (`no_visible_questions`), not to save a draft.

## 4. Effects elsewhere

- **Session creation and New FIP.** `GET /api/knowledge-models?status=published` already returns published public models plus the caller's
  own; `FipNew.vue` and `SessionNew.vue` keep using it and now group options as "System", "Mine", "Public" using `isSystem`/`ownerId`.
  `authz.get_readable_published_km` is unchanged, so a draft can never be answered.
- **Progress.** `TOTAL_QUESTIONS = 21` stops being the denominator. `lib/progress.ts` gains
  `visibleQuestionCount(km)` = questions with `hidden !== true`; `FipEditor.vue` and `FipRead.vue` use it from the loaded model,
  `Workspace.vue` and `MatrixView.vue` use `questionCount` from the model summary (API #1), falling back to `TOTAL_QUESTIONS` only when no
  model is loaded. Hidden questions are excluded from both numerator and denominator.
- **Hidden questions in exports.** `exporters.build_export_json` / `build_export_csv` skip questions with `hidden === true` while iterating
  sections — so no padded row and no `answers` entry for them, even if the FIP still stores an answer from before the question was hidden.
  `routers/fips._known_question_ids` keeps returning hidden ids, so patching such a FIP still succeeds (200, no 400).
- **Untagged questions in the matrix.** `buildMatrix` keeps grouping by knowledge-model section (spec 03 §1.2). Additions: a section whose
  `title` LangMap resolves to nothing falls back to the label `matrix.otherGroup` ("Other"); `MatrixRow` gains
  `principleGroup = principle?.[0] ?? 'Other'`, and the per-principle convergence view collects every row with `principle === null` under
  the "Other" group. A row with `ferType === null` renders no FER-type chip; convergence, cells and toggles behave exactly as today.
- **Untagged questions in RDF** (spec 03 §2.3, already the specified behaviour — pin it with a test, no code change expected): the
  declaration node is still `a fip:FIP-Declaration` with `fipmx:declaration-status`, `fipmx:declaration-index` and a `fipmx:question-id`
  literal, but carries **no `fip:refers-to-question`** (the id maps to none of the 21 individuals) and **no `fip:refers-to-principle`**;
  the FER node is `a fip:FAIR-Enabling-Resource` (plus the availability class per spec 03 §6) with **no FER-type class**, because there is no
  `ferType` to map; a question comment is emitted as a node typed **`fipmx:Answer`** with `fipmx:refers-to-question` and
  `fipmx:answer-comment`, and no `fip:` question or principle link. Hidden questions emit nothing at all.
- **CSV and JSON exports are otherwise unaffected**: same 21 columns, same document shape; `principle`, `scope` and `fer_type` are simply
  empty for untagged questions.

## 5. Frontend

**Routes** (`src/router/index.ts`): `/knowledge-models` `KnowledgeModelList` (`requiresAuth: false` — anonymous sees public + system),
`/knowledge-models/new` `KnowledgeModelNew` (auth), `/knowledge-models/:id/:version` `KnowledgeModelRead` (public read view),
`/knowledge-models/:id/:version/edit` `KnowledgeModelEditor` (auth; ownership and `status==="draft"` checked inside the view, which renders
`common.notFound` on 404 and a read-only banner on a published version). `Workspace.vue`'s "My knowledge models" section gains
"New model", per-row Edit / View / Export / Fork / New version / Delete links and a status chip.

**Views.**
- `KnowledgeModelList.vue` — three blocks (Mine, System, Public), each row: title, id@version, status chip, `questionCount`,
  `forkedFrom` note, actions (View, Fork, Edit when own draft, Import button in the header).
- `KnowledgeModelNew.vue` — three cards: from scratch (title + id), fork (a select of readable models), import (file input → parsed JSON
  posted to #6; server `errors` rendered as a list with their `path`).
- `KnowledgeModelRead.vue` — resolved title/description, licence and `AttributionFooter`, changelog, sections and questions read-only with
  badges (principle, scope, FER type, required, hidden), Export JSON, Fork, New version (owner, published).
- `KnowledgeModelEditor.vue` — desktop-first, must not break at 375 px (single column, no drag). Sticky header: model title, `id@version`,
  status chip, `SaveIndicator` (reuse), `TranslationMeter`, Validate, Save, Publish. Body: model metadata block (title, description,
  visibility) then a **sections accordion** (`KmSectionList`); one open section at a time, each head showing the section title, question
  count, up/down buttons and a delete button. Inside: **question cards** (`KmQuestionCard`) with **language tabs en / pt-PT / pt-BR**
  (`KmLangTabs`) over `text` and `help`, and controls for principle, scope, FER type, required, allowMultiple, hide/unhide, split, delete,
  up/down. **Up/down buttons, not drag handles** — phone- and keyboard-friendly, no library, trivially testable; ends are `disabled`.
  A hidden question card is dimmed with a "Hidden" chip and stays editable.
- Saving: the store keeps the parsed content, applies pure ops from `lib/kmContent.ts`, marks dirty and `PUT`s on an explicit Save **and** on
  an 2 s idle debounce; a 409 `content_conflict` shows "This draft changed elsewhere. Reload to see the newer version." with a Reload
  button (no silent merge, mirroring spec 02's last-write-wins honesty). `beforeRouteLeave` flushes.
- `KmPublishDialog.vue` — target version (read-only), a required `notes` textarea (Publish disabled while empty), the validation summary, and
  the reminder that publishing freezes the version.

**Components:** `KmSectionList.vue`, `KmQuestionCard.vue`, `KmLangTabs.vue`, `KmPublishDialog.vue`, `KmImportDialog.vue`,
`KmValidationList.vue`, `TranslationMeter.vue`, `MoveButtons.vue` (`props {canUp, canDown}`, emits `up`/`down`; reusable for sections and
questions). Reused as-is: `SaveIndicator`, `VisibilitySelect`, `AttributionFooter`, `LanguageSwitcher`.

**Store `stores/knowledgeModel.ts`:** state `model`, `content`, `etag`, `dirty`, `saveState`, `errors`, `conflict`; actions `load(id, version)`,
`patchMeta`, `apply(op)` (delegates to `lib/kmContent.ts`), `save()`, `publish(notes)`, `newVersion(bump)`, `fork(target)`, `remove()`,
`reload()`; getters `visibleQuestionCount`, `completeness(locale)` = filled translatable strings / total, per language.
**Lib `lib/kmContent.ts`:** `validateContent`, `hideQuestion`, `unhideQuestion`, `moveQuestion`, `moveSection`, `addQuestion`, `addSection`,
`splitQuestion`, `setFerType`, `deleteQuestion`, `deleteSection`, `setText`, `visibleQuestionCount`, `completeness` — all pure, all vitest-ed.
**API `api/knowledgeModels.ts`:** add `createKnowledgeModel`, `forkKnowledgeModel`, `importKnowledgeModel`, `patchKnowledgeModel`,
`putKnowledgeModelContent(id, version, body, etag)`, `publishKnowledgeModel`, `newKnowledgeModelVersion`, `deleteKnowledgeModel`,
`kmExportJsonUrl`; `getKnowledgeModel` returns the `ETag` alongside the body.

**i18n keys to add** (English; `pt-PT`/`pt-BR` go to the translator agent):
```text
km: title "Knowledge models" · mine "My models" · system "Built-in models" · public "Public models" · new "New model" ·
  fromScratch "Start from scratch" · fork "Fork" · forkOf "Forked from {id} v{version}" · import "Import JSON" · export "Export JSON" ·
  newVersion "New version" · bump "Version increase" · bumpMinor "Minor (1.1.0)" · bumpPatch "Patch (1.0.1)" · bumpMajor "Major (2.0.0)" ·
  draft "Draft" · published "Published" · readOnlyPublished "This version is published and cannot be changed. Create a new version to edit." ·
  readOnlySystem "Built-in models cannot be edited. Fork it to make your own." · edit "Edit" · sections "Sections" · addSection "Add section" ·
  sectionTitle "Section title" · questions "{count} questions" · addQuestion "Add question" · questionId "Question id" ·
  questionText "Question" · help "Help text" · principle "FAIR principle" · scope "Scope" · scopeNone "Not specific" · ferType "Resource type" ·
  ferTypeNone "No resource type" · required "Required" · allowMultiple "Allow several resources" · hide "Hide" · unhide "Unhide" ·
  hidden "Hidden" · hiddenHint "Hidden questions stay in the model but are not asked or exported." · split "Split into metadata / data" ·
  splitHint "Creates two questions, one for metadata and one for data." · moveUp "Move up" · moveDown "Move down" ·
  deleteQuestion "Delete question" · deleteQuestionConfirm "Delete this question? Existing FIPs on published versions are not affected." ·
  deleteModel "Delete model" · deleteModelConfirm "Delete this model version? This cannot be undone." · inUse "This version is used by FIPs
  and cannot be deleted." · publish "Publish" · publishTitle "Publish version {version}" · changelog "What changed" ·
  changelogRequired "Describe what changed before publishing." · publishHint "Publishing freezes this version. Later edits need a new version." ·
  translation "Translations" · translationMeter "{done} of {total} texts in {language}" · missingTranslation "Missing — showing {language}" ·
  validate "Check model" · valid "No problems found." · invalid "{count} problems to fix" · conflict "This draft changed elsewhere. Reload to
  see the newer version." · reload "Reload" · idTaken "That identifier is already in use." · importFailed "This file is not a valid knowledge
  model." · noModels "No models yet."
matrix (add): otherGroup "Other"
```

## 6. Acceptance criteria

**Backend — pytest, `backend/tests/`**

1. `POST /api/knowledge-models/gofair-fip-mini/1.0.0/fork` as a signed-in user returns 201 with `ownerId` = that user, `version` `1.0.0`,
   `status` `draft`, `visibility` `private`, `license` `CC-BY-SA-4.0`, `content.forkedFrom == {"id": "gofair-fip-mini", "version": "1.0.0"}`,
   `content.attribution` equal to the spec 00 §6 string, and `sections` deep-equal to the system model's; the system row's
   `content_sha256`, `owner_id` and `updated_at` are unchanged. A second fork without `newId` gets id `gofair-fip-mini-fork-2`.
2. Edit + publish on that fork: `GET` yields an `ETag`; `PUT …/content` with `If-Match` returns 200 and a different `ETag`;
   `POST …/publish` with `{}` returns 422 and with `{"notes": ""}` 400 `changelog_notes_required`; with real notes returns 200,
   `status="published"` and `changelog[-1] == {"version": "1.0.0", "date": <today UTC>, "notes": <notes>}`; a further `PUT …/content`
   returns 409 `model_published`, while `PATCH` with only `visibility` returns 200.
3. A FIP created on the published fork (`POST /api/fips`) returns 201, and its `export.json` carries
   `questionnaireRef == {"id": <fork id>, "version": "1.0.0", …}` with the **edited** question text resolved, while `export.csv` still has
   exactly the 21 columns of spec 01 §3.2 in order.
4. Hidden question: hide one question in a draft, publish, create a FIP answering two others. `export.csv` contains no row whose
   `question_id` is the hidden one, `export.json` no `answers` entry for it, `GET /api/knowledge-models` reports `questionCount` = visible
   count only, and `PATCH /api/fips/{id}` with an answer whose `questionId` is the hidden question still returns 200.
5. Untagged question: publish a from-scratch model with one question (`principle: null`, `ferType: null`), answer it with a free-text FER and
   a comment, then `GET /api/fips/{id}/export.ttl` — the declaration has no `fip:refers-to-question` and no `fip:refers-to-principle`, has a
   `fipmx:question-id` literal, the FER node carries no `fip:`-namespace FER-type class, and the comment node is typed `fipmx:Answer`.
6. `POST /api/knowledge-models/import` with two questions sharing an id returns 400 `invalid_content` whose
   `errors[0] == {"path": "sections[0].questions[1].id", "code": "duplicate_question_id", …}`; a document missing `en` in one question text
   returns `missing_en` at that path; the unmodified `data/knowledge-models/gofair-fip-mini-1.0.0.json` imports with 201 as a private draft
   owned by the caller, leaving the system row untouched.
7. Delete: `DELETE` a published version referenced by a FIP → 409 `model_in_use` and the row survives; delete a draft → 204 and it is gone;
   `DELETE /api/knowledge-models/gofair-fip-mini/1.0.0` as a non-admin → 403 `system_model_readonly`.
8. Non-owner: a second signed-in user gets **404 `not_found`** from `PUT …/content`, `PATCH`, `POST …/publish`, `POST …/new-version` and
   `DELETE` on the first user's private draft, and 404 from `GET`; an anonymous client gets 401 on all five.
9. Optimistic concurrency: two `PUT …/content` calls with the same `If-Match` → first 200, second **409 `content_conflict`** with the current
   `etag` in the body and the draft holding the first write; a `PUT` with no `If-Match` header → **428 `if_match_required`**;
   `If-Match: "*"` is not accepted as a wildcard.
10. `POST …/new-version`: on the published 1.0.0 with no body → 201 `1.1.0` draft; `bump=patch` → `1.0.1`; `bump=major` → `2.0.0`;
    `version=0.9.0` → 400 `version_not_greater`; a second call while a draft exists → 409 `draft_exists`; on a draft → 409 `not_published`.
11. `validate_content` unit test with a table of fixtures returns the exact `code` and `path` for duplicate question id, unknown `ferType`,
    unknown `principle`, missing `en`, bad `scope` and 301 questions, and returns `[]` for the real
    `data/knowledge-models/gofair-fip-mini-1.0.0.json`; `python -m fipm import-data` still reports all-skipped on a warm DB.
12. `DELETE /api/auth/me` for a user owning one published model referenced by a FIP and one draft → 204; the published row survives with
    `owner_id IS NULL` and `visibility="public"`, the draft row is gone, and the FIP still exports (its `questionnaireRef` resolves).

**Frontend — vitest, `npm run test:unit`**

13. `lib/kmContent.ts`: every op returns a new object without mutating its input; `moveQuestion`/`moveSection` are no-ops at the ends;
    `splitQuestion("F2")` yields `F2-metadata` and `F2-data` in place with copied texts and the right `scope`, and throws on an id already
    ending in `-metadata`; `hideQuestion` sets `hidden: true` and keeps the question in `content`; `visibleQuestionCount` on the real
    `gofair-fip-mini-1.0.0` fixture is 21 and 20 after hiding one; `validateContent` returns the same codes and paths as AC 11's table.
14. `KnowledgeModelEditor.vue` (with a stubbed store): renders one accordion head per section with up/down buttons `disabled` at the ends,
    question cards with three language tabs, a `pt-PT`-missing text shown as the `en` fallback carrying the `missing` class and
    `km.missingTranslation`, a `TranslationMeter` reading "19 of 21 texts in Portuguese (Portugal)", and a `KmPublishDialog` whose Publish
    button is `disabled` until `notes` is non-empty; a 409 conflict state renders `km.conflict` with a Reload button.

**Manual script** (`scripts/manual-km-editor.md`, run in the week-3 dry run): sign in → fork the GO FAIR model → rename it, translate one
question into pt-PT, hide one question, reorder one section, add one untagged question → publish 1.0.0 with a changelog note → create a
session on it → answer it on a 375 px viewport (no horizontal scroll, tap targets ≥ 44 px) → open the matrix (untagged row under "Other")
→ export Turtle and CSV → back in the editor, "New version" → 1.1.0 draft, published 1.0.0 unchanged, delete attempt → 409 message shown.

## 7. Assumptions (facilitators away; revisit at the 12 Sep scope freeze)

- **A1. Desktop-first editor, phone-safe.** The editor targets a laptop (facilitators prepare models before the workshop) but degrades to one
  column at 375 px with no horizontal scroll and no drag interaction — hence up/down buttons everywhere.
- **A2. The GO FAIR system model is never editable in place**, not even by an admin through this API; changing it means editing
  `data/knowledge-models/*.json` and re-running `import-data --force`. Admin write access exists for visibility only.
- **A3. Forks of GO FAIR content carry CC BY-SA 4.0 and the attribution string automatically**, with no opt-out in the UI (PLAN §9.7);
  the licence field of such a fork is read-only in the editor.
- **A4. One draft per model id**, single editor, no collaboration: concurrency is detected (409) and resolved by reloading, never merged.
- **A5. No FIP migration between versions** (PLAN §4, v2). A published version stays answerable forever unless it is deleted, which
  §1 forbids while FIPs reference it.
- **A6. Question ids are free text after a fork.** Renaming a forked id such as `F1-metadata` silently drops the ontology link
  (spec 03 §2.3 falls back to `fipmx:question-id`); the editor warns but does not prevent it.

## 8. Open questions

1. Should a fork be allowed to start at the source's version number (e.g. fork GO FAIR 1.0.0 as `my-fip 1.0.0` — as specified) or at
   `0.1.0` to signal "not yet reviewed"? Facilitator preference; one constant.
2. Cross-section moves and section merging are out of v1. Needed before the workshop, or is reorder-within-section enough?
3. Should hidden questions be exported as `hidden: true` rows in a *model* export (as specified, so a re-import round-trips) or stripped?
4. Does the workshop want a diff view between two published versions (v2 candidate, cheap on top of `lib/kmContent.ts`)?
