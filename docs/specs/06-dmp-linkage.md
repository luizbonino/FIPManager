# Spec 06 – DMP linkage (FioDMP), embed view and prefill stub

Status: draft for v2, 2026-09-09. Covers ROADMAP "Oct–Dec 2026 · v2 – Integration" bullets 2–4. Authority: PLAN §3 (FioDMP findings), §5 v2,
§6 (integration design and mapping table). Builds on `01-foundations.md` §2.2 (`relatedDMPs`, `dmpEvidence`), §3.1/§3.2 (export shapes), §5
(authz), §6 (API); `03-matrix-and-rdf.md` §2 (`dcso:DMP`, `fipmx:` terms). Companion deliverable for ICTIC/Fiocruz:
`docs/integration/fiodmp-api-contract.md` + `fiodmp-openapi.yaml`. **No DB migration**: `SCHEMA_VERSION` stays 1 — `fips.related_dmps` and the
per-declaration `dmpEvidence` are existing JSON. Two amendments to earlier specs: three CSV columns and two new `fipmx:` terms (both §2.4).

## 1. `relatedDMPs` — linking a FIP to plans

### 1.1 Normalisation and validation (`backend/fipm/dmp.py`, new module)

One helper, used by every write path: `normalise_related_dmps(entries: list[dict]) -> list[dict]`, raising `HTTPException(422, detail=<code>)`.
Validation lives here and **not** in Pydantic field validators, so failures keep the API-wide `{"detail": "<snake_case_code>"}` shape
(spec 01 §6) instead of Pydantic's error array.

| Rule | Code (422) |
|---|---|
| ≤ 10 entries per FIP | `dmp_too_many` |
| `url` present, ≤ 2048 chars, absolute, scheme exactly `https`, host non-empty, no userinfo, no whitespace or control chars | `dmp_url_invalid` |
| normalised URLs unique within the FIP | `dmp_url_duplicate` |
| `version` a string ≤ 20 chars if present | `dmp_version_invalid` |

Normalisation: trim; lowercase scheme and host; drop a default port, a fragment and an empty query; strip a trailing `/`. If the result
matches `^https://(www\.)?<fiodmp_host>/(publico/)?(?P<id>[A-Za-z0-9]{4,16})$` (host from `FIPM_FIODMP_BASE_URL`, default
`https://fiodmp.fiocruz.br`), the entry becomes `{"url": "https://fiodmp.fiocruz.br/<ID upper>", "version": …, "system": "FioDMP",
"dmpId": "<ID upper>"}`; anything else keeps its normalised URL and gets `"system": "other"` and no `dmpId`. `system` and `dmpId` are
**derived server-side and ignored on input** (a client-sent `system` is overwritten) — the store is the only place that decides what a
FioDMP URL is. Stored shape stays the spec 01 §2.2 object plus the optional `dmpId` key (additive, round-trips through export/import).

Call sites: `POST /api/fips`, `PATCH /api/fips/{id}` (both already receive `related_dmps`) and `POST /api/fips/import` (`fip.relatedDMPs` of
the imported document). `RelatedDmp` gains `dmp_id: str | None = None`, `system` stays free-text on input, and the router replaces the whole
list with the helper's output before commit.

### 1.2 Editor UI

There is no `CommunityForm.vue` today: the community form is duplicated in `views/FipNew.vue` and `views/JoinSession.vue`, and `FipEditor.vue`
only shows `community.name` in its header. This spec does **not** refactor that; it adds one component and one host:

- **`components/DmpLinkList.vue`** — props `{ entries, readOnly }`, emits `update`. A row per entry: `<input type="url">` (placeholder
  `https://fiodmp.fiocruz.br/KQU5N0C`), a short `<input>` for `version`, a derived system badge (`FioDMP` = filled chip, `other` = outline),
  and a remove button. "Add a DMP link" is `disabled` at 10 entries with the hint `dmp.maxReached`. Client-side mirror of §1.1 in
  **`lib/dmp.ts`** (`normaliseDmpUrl`, `detectSystem`, pure, unit-tested) shows `dmp.urlInvalid` inline on blur before any request; the
  server's normalised list replaces local state from the PATCH response, so the badge and casing always come from the backend.
- **Host:** a new `<details class="section dmp-section">` "Related DMPs" placed directly above the questionnaire sections in
  `FipEditor.vue`, inside the existing `@blur.capture="onFieldBlur"` wrapper. Writes go through a new store action
  `setRelatedDmps(entries)` next to `setCommunity`, reusing the 800 ms autosave and the existing `relatedDmps` field of the PATCH payload
  (spec 02 §3 lists `relatedDMPs` as patchable already; `stores/fipEditor.ts` must add it to `performSave`'s payload).

### 1.3 Read view
`FipRead.vue` adds a `relatedDMPs` block to the community `<dl>`: one `<a :href target="_blank" rel="noopener">` per entry showing `dmpId`
(FioDMP) or the host + path (other), a `FioDMP` badge when `system === 'FioDMP'`, and `v{version}` when stored. Printed, not `.no-print` (the
printed FIP must carry the plan URL). Same block, read-only, in the embed view (§3).

### 1.4 i18n keys (English; pt-PT / pt-BR via the translator agent)
```text
dmp: heading "Related data management plans" · add "Add a DMP link" · url "Plan URL" · version "Version" · system "System" · fiodmp "FioDMP" ·
  other "Other" · remove "Remove" · maxReached "At most 10 plans per FIP." · urlInvalid "Use a full https:// URL of a plan." ·
  duplicate "That plan is already linked." · none "No plans linked." · evidence "Evidence in DMP" · evidencePlan "Plan" ·
  evidenceSection "Section" · evidenceQuestion "Question or field" · evidenceHint "Where in the plan is this answer written down?" ·
  sectionOther "Other" · prefill "Prefill from this plan"
```

## 2. `dmpEvidence` — per-declaration evidence

### 2.1 Shape
`DmpEvidence` becomes `{dmpIndex: int, section: str | None, questionRef: str | None}`. The object as a whole is optional; `dmpIndex` is
required whenever it is present, and is the 0-based position in this FIP's `relatedDMPs`, not a URL — a plan whose URL is corrected in one
place stays linked from every declaration. **Legacy read:** no FIP can carry evidence yet (v1 never exposed the field), but `schemas.py`
already ships `{url, questionRef}`, so readers (`exporters.py`, `rdf.py`, `fips/import`) accept both — an object with `url` and no `dmpIndex`
exports that URL verbatim with no section; writers only ever produce the new shape.

### 2.2 Validation (same module and codes as §1.1)

| Rule | Code (422) |
|---|---|
| evidence present while the FIP has no `relatedDMPs` (after applying the same request) | `dmp_evidence_without_dmp` |
| `dmpIndex` missing, not an int, negative, or ≥ `len(relatedDMPs)` | `dmp_evidence_index_invalid` |
| `section` ≤ 40 chars, `questionRef` ≤ 120 chars | `dmp_evidence_invalid` |

Evidence is validated **after** the request's `relatedDMPs` are normalised, in the same transaction, so a PATCH that removes a plan while a
declaration still cites it fails with `dmp_evidence_index_invalid` rather than leaving a dangling index. An all-empty object is stored `null`.

### 2.3 Editor UI
`DeclarationEditor.vue` gains a `<details class="evidence">` with summary `dmp.evidence`, rendered **only** when
`store.fip.relatedDmps.length > 0` (no DMP linked → no evidence UI at all): a `<select>` of the linked plans (option label = `dmpId` or host
plus `v{version}`), a `<select>` for `section` offering `A`–`G` (the FioDMP section letters, PLAN §3) plus `dmp.sectionOther` revealing a
free-text input, and an `<input>` for `questionRef` (placeholder `C.3`). Changes go through the existing
`store.setDeclaration(questionId, index, { dmpEvidence })`; clearing the plan select clears the object. `FipRead.vue` shows a stored evidence
under its declaration as `dmp.evidence`: plan link · section · questionRef.

### 2.4 Exports

- **JSON (spec 01 §3.1)** — `dmpEvidence` is resolved at export time so a consumer never needs the index: `{"dmpIndex": 0, "dmpUrl":
  "https://fiodmp.fiocruz.br/KQU5N0C", "dmpSystem": "FioDMP", "dmpVersion": "13", "section": "C", "questionRef": "C.3"}`. `exportVersion`
  stays `1` (the key existed and was always empty); `POST /api/fips/import` round-trips it to the stored shape by matching `dmpUrl` against
  the imported `relatedDMPs`, falling back to `dmpIndex`.
- **CSV (spec 01 §3.2)** — three columns **appended** after `comment`, so every existing column index is unchanged:
  `…, comment, dmp_url, dmp_section, dmp_question`. `CSV_HEADER` grows to 24 entries and the session export keeps its two-column prefix.
  `tests/test_ac11_export_csv.py` asserts `len(header) == 21`; that literal becomes 24 (one-line fixture change).
- **RDF (spec 03 §2.3)** — a declaration with evidence gets `fipmx:dmp-evidence` → the DMP's IRI (the normalised `relatedDMPs` URL, already a
  `dcso:DMP` node carrying `fipmx:dmp-version` and `fipmx:dmp-system` from spec 03), plus `fipmx:dmp-section` and the existing
  `fipmx:dmp-question-ref` as plain literals on the declaration. The existing declaration-level `prov:wasDerivedFrom` to the same IRI is
  kept: `prov:` is what a generic consumer understands, `fipmx:dmp-evidence` is what says "this is the *justification* for this declaration".
  **Amends spec 03 §2.1's closed term list** with `dmp-evidence` and `dmp-section`; both are in the fixed `FIPM_EXT_NS`
  (`https://w3id.org/fipm/ns#`), and both go into the §2.6 JSON-LD context as `dmpEvidence` (`"@type": "@id"`) and `dmpSection`.

```turtle
this:decl-F2-0 a fip:FIP-Declaration ; fip:declares-current-use-of <https://www.dublincore.org/specifications/dublin-core/dcmi-terms/> ;
    fipmx:dmp-evidence <https://fiodmp.fiocruz.br/KQU5N0C> ; fipmx:dmp-section "C" ; fipmx:dmp-question-ref "C.3" ; prov:wasDerivedFrom <https://fiodmp.fiocruz.br/KQU5N0C> .
<https://fiodmp.fiocruz.br/KQU5N0C> a dcso:DMP ; fipmx:dmp-version "13" ; fipmx:dmp-system "FioDMP" .
```

## 3. Embed view — `GET /fips/{id}/embed`

Server-rendered HTML for an `<iframe>` in FioDMP (or any allowed host); **not** under `/api`, so the URL is quotable next to the FIP URL.

- **Module:** `backend/fipm/embed.py` — `render_embed(doc, fip, settings, lang) -> str`, pure and unit-testable — plus
  `backend/fipm/routers/embed.py` (`APIRouter()`, no prefix) included in `main.py` **with the other routers**, i.e. before the
  `@app.get("/{path:path}")` SPA catch-all is defined; otherwise the catch-all swallows it.
- **Data:** `exporters.build_export_json(db, fip, settings)` — it already resolves question texts, FER labels, notes and the questionnaire ref
  with the `pt-PT ⇄ pt-BR → en` fallback and pads unanswered questions. The embed adds no resolution logic of its own.
- **Auth:** the read rule of spec 01 §5 — `_get_readable_fip`, moved verbatim from `routers/fips.py` to a shared helper: owner, admin and
  session owner by cookie, `X-Edit-Token` still honoured, and for an anonymous caller only `visibility` `link` or `public`. `private` → **404**
  as a 12-line HTML stub with the same headers (never a JSON body: the response is framed).
- **Body:** `<h1>` community name; description and research domain when present; a meta line "questionnaire title (id vX.Y.Z, language)"; the
  answered count `n / 21`; a `<table>` of every questionnaire question in model order — question id badge, principle, FER label(s) (catalogue
  label, free text, or "—") and a status badge per declaration, with the five `--color-status-*` values inlined as hex (the SPA's CSS variables
  are not available here); the §1.3 DMP list; `<a>` "View the full FIP" → `{base_url}/fips/{id}`; and the attribution footer — the three
  `attribution.*` strings, the questionnaire one only when the model's `license` starts with `CC-BY-SA` (mirrors `AttributionFooter.vue`).
  Fixed strings come from `EMBED_STRINGS: dict[str, dict[str, str]]` in `embed.py` (`en`, `pt-PT`, `pt-BR`, ≈12 keys); language = `?lang=` when
  it is one of the three, else the FIP's `language`, else `en`.
- **No JS, no external requests:** one `<style>` in `<head>`, no `<script>`, no images, no web fonts (system font stack). Responsive:
  `max-width: 46rem`, `table { width: 100% }`, a `@media (max-width: 420px)` rule hiding the principle column. Every interpolated value passes
  through `html.escape(..., quote=True)`: community names and free-text FERs are user content and this page is framed by a third party, so
  escaping is the security boundary (AC 7).
- **Headers:**
  - `Content-Type: text/html; charset=utf-8`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.
  - `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors <list>`.
  - `X-Frame-Options: SAMEORIGIN` **only** when the list is exactly `'self'` (the header cannot express an allow-list; when an external
    origin is allowed it is omitted and CSP alone governs — documented, and the reason the default below is not "same origin only").
  - `Cache-Control: public, max-age=300` for `public`/`link`, `private, no-store` otherwise.
- **Config:** `FIPM_EMBED_ALLOWED_ORIGINS`, comma-separated, default `https://fiodmp.fiocruz.br`; `'self'` is always prepended; `*` alone means
  `frame-ancestors *`; empty means `'self'` only. `Settings.embed_allowed_origins_list` mirrors `allowed_origins_list`.
  `FIPM_FIODMP_BASE_URL` (§1.1) is separate: it identifies plans, not framers.

### 3.1 What FioDMP reads from `GET /api/fips/{id}`

Exact fields FioDMP needs, all already in `FipOut`: `id`, `visibility`, `questionnaireId`, `questionnaireVersion`, `community`
(`name`, `description`, `domain`), `language`, `license`, `relatedDmps`, `updatedAt`. Two cheap additions:

- `embedUrl: str` — `f"{settings.base_url}/fips/{id}/embed"`, built in `_out()`.
- `summary: {answeredQuestions: int, totalQuestions: int | null, declarations: int, byStatus: {<status>: int}}` — `answeredQuestions` = answers
  with ≥ 1 declaration (spec 02 §1), `byStatus` keyed by the five `DECLARATION_STATUSES` (zeros included), `totalQuestions` from the FIP's
  knowledge model or `null` if that row is missing. `_out()` takes an optional `total_questions`; `GET /api/fips/{id}` pays one extra
  primary-key `db.get(KnowledgeModel, …)`, the other handlers already hold the row.

A cross-origin `fetch` from FioDMP is **not** enabled in v2: `/api/fips/{id}` sends no `Access-Control-Allow-Origin`. FioDMP either fetches
server-side (recommended, and how the contract doc specifies it) or embeds the iframe; CORS for the FioDMP origin is a one-line follow-up.

## 4. Prefill stub — `POST /api/fips/{id}/prefill-from-dmp`

Body `{dmpUrl}`; auth = the FIP **write** rule (`_authorize_fip_write`, so owner / admin / session owner / `X-Edit-Token`), CSRF as any
`/api` POST. The URL goes through §1.1 (bad URL → 422 `dmp_url_invalid`); then the endpoint always returns **501**, a `JSONResponse` whose
body keeps a string `detail` so existing error handling works:

```json
{"detail": "fiodmp_api_unavailable", "dmpUrl": "https://fiodmp.fiocruz.br/KQU5N0C", "system": "FioDMP",
 "requires": {"endpoint": "GET /api/plans/{id}", "format": "RDA DMP Common Standard (maDMP) 1.1 JSON",
   "reference": "https://github.com/RDA-DMP-Common/RDA-DMP-Common-Standard", "contract": "docs/integration/fiodmp-api-contract.md"},
 "message": "FioDMP exposes no machine-readable plan export yet; the FIP→DMP link works by URL today."}
```

No frontend in v2.0 — the ICTIC demo calls it from `/docs`. When FioDMP ships the API this handler becomes the real prefill, and the
`dmp.prefill` key (§1.4) gets its button in `DmpLinkList.vue`.

## 5. Acceptance criteria

**Backend — pytest, `backend/tests/`**
1. `PATCH /api/fips/{id}` with `relatedDmps` `[{"url": "https://www.fiodmp.fiocruz.br/publico/kqu5n0c/", "version": "13", "system": "x"}]` stores
   `{"url": "https://fiodmp.fiocruz.br/KQU5N0C", "version": "13", "system": "FioDMP", "dmpId": "KQU5N0C"}`; a generic
   `https://example.org/plan?x=1#f` stores that URL minus the fragment, `system: "other"`, no `dmpId`.
2. 422 `{"detail": …}` for: `http://…` and `javascript:alert(1)` → `dmp_url_invalid`; 11 entries → `dmp_too_many`; the same plan twice in
   different casings → `dmp_url_duplicate`; a 30-char `version` → `dmp_version_invalid`.
3. `dmpEvidence` `{"dmpIndex": 0, "section": "C", "questionRef": "C.3"}` round-trips through PATCH and GET; `dmpIndex: 1` with one linked plan →
   422 `dmp_evidence_index_invalid`; a PATCH dropping `relatedDmps` to `[]` while evidence stands → 422 `dmp_evidence_without_dmp`; evidence
   with all fields empty is stored as `null`.
4. `export.json` resolves that evidence to `{dmpIndex, dmpUrl, dmpSystem, dmpVersion, section, questionRef}`, `POST /api/fips/import` of the
   document recreates the stored shape, and a legacy `{"url": …, "questionRef": …}` stored object still exports and imports.
5. `export.csv`: `CSV_HEADER` has 24 entries ending `dmp_url, dmp_section, dmp_question`, the first 21 unchanged and in order, and the
   evidence-carrying declaration's row holds the normalised URL, `C` and `C.3`.
6. `export.ttl`: the declaration has exactly one `fipmx:dmp-evidence` → `https://fiodmp.fiocruz.br/KQU5N0C`, that IRI is typed `dcso:DMP` with
   `fipmx:dmp-system "FioDMP"`, and `fipmx:dmp-section` / `fipmx:dmp-question-ref` literals are present; a FIP without evidence emits none of
   the three predicates.
7. `GET /fips/{id}/embed`: 200 `text/html` for `public` and `link` anonymously, 404 `text/html` for `private` anonymously, 200 for its owner's
   cookie and for a valid `X-Edit-Token`; the body holds no `<script` and a community name of `<img src=x onerror=alert(1)>` appears only as
   `&lt;img …`.
8. Embed content: 21 question rows in knowledge-model order, the `n / 21` count matching the stored answers, the questionnaire id and version,
   the linked plan's URL, an `href` of `{base_url}/fips/{id}`, the CC BY-SA questionnaire credit (KM licence `CC-BY-SA-4.0`), and `?lang=pt-BR`
   switching the fixed labels while `?lang=zz` falls back to the FIP's language.
9. Embed headers: by default `Content-Security-Policy` contains `frame-ancestors 'self' https://fiodmp.fiocruz.br` and no `X-Frame-Options`;
   with `FIPM_EMBED_ALLOWED_ORIGINS=""` it contains `frame-ancestors 'self'` **and** `X-Frame-Options: SAMEORIGIN`; a `public` FIP gets
   `Cache-Control: public, max-age=300`, a `private` one `private, no-store`.
10. `GET /api/fips/{id}` returns `embedUrl` and a `summary` whose `answeredQuestions`, `declarations` and `byStatus` (all five statuses, zeros
    included) match the fixture and whose `totalQuestions` is 21; `POST /api/fips/{id}/prefill-from-dmp` returns 501 with
    `detail == "fiodmp_api_unavailable"` and `requires.endpoint == "GET /api/plans/{id}"`, 422 for a non-https `dmpUrl`, 403 for an anonymous
    caller with no edit token.

**Frontend — vitest** — 11. `lib/dmp.ts` reproduces the §1.1 normalisation table (FioDMP with/without `www`, `/publico/`, trailing slash,
lowercase id; a generic URL; a rejected `http://`); `DmpLinkList.vue` renders the filled `FioDMP` badge, the outline badge otherwise, and
disables "Add" at 10 entries; `DeclarationEditor.vue` renders no `dmp.evidence` block when `relatedDmps` is empty, and a plan `<select>` with
one option when a plan is linked. **Manual** (v2 dry run): a local `.html` with `<iframe src="…/fips/<id>/embed" height="600">` renders framed
with no console errors, and the same iframe from a non-allowed origin is blocked by the browser.

## 6. Open questions

1. Re-check a plan URL with an HTTP HEAD at save time to catch typos? Costs an outbound request; default answer: no, pattern only.
2. `dmpEvidence` is one object per declaration; two plans justifying one declaration would need a list — cheap now, awkward later. Keep one?
3. Does FioDMP frame third-party content at all, or would ICTIC rather render `GET /api/fips/{id}` in their own Blade templates? The embed is
   built either way; the answer decides whether `frame-ancestors` matters (meeting question, contract doc §7).
