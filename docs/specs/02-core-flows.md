# Spec 02 – Core flows: participant, owned FIP, facilitator, read-only view

Status: approved for implementation, 2026-09-08. Covers ROADMAP week 2. Authority: PLAN.md §5, §7. Builds on
`01-foundations.md` (API table, data model, export shapes) and `00-fip-ontology-mapping.md` (status enum,
12 FER types, 21 question ids). Scope: the four flows below plus the minimum API deltas; the comparison
matrix is week 3 and only its route is reserved. No DB change (`SCHEMA_VERSION` stays 1).

## 1. Vocabulary fixed by this spec

- **Sections** are `F`, `A`, `I`, `R` (ids in `gofair-fip-mini-1.0.0.json`), 6/5/6/4 questions = 21.
- **Answered** = the FIP's `answers` entry has ≥ 1 declaration; `status: "none"` counts (the ontology treats
  "no choice yet" as a real declaration). Progress = `answeredCount / 21`, computed client-side.
- **Display name of a FIP** = `community.name`, falling back to the FIP id. `Fip.title` stays unused in v1
  (`POST /api/fips` already writes `None`); no `title` is added to `PATCH /api/fips/{id}`.
- **Statuses**: exactly `current | planned | planned-development | planned-replacement | none`
  (`fipm.config.DECLARATION_STATUSES`); the UI never invents a sixth.
- **Free-text FER** = a declaration with `ferFreeText` set and `ferId` null, stored inline in the `answers`
  JSON, creating **no** row in `fers`; anonymous participants never call `POST /api/fers` (it needs a user).
  `exporters.py` already emits it as `fer_free_text` / `ferFreeText`. Promotion to the catalogue is v2.
- **`resolveLang(map, locale)`** mirrors `exporters.resolve_lang`: exact locale → `pt-PT ⇄ pt-BR` sibling →
  `en` → first value → `null`. One implementation, `src/lib/lang.ts`.

## 2. Participant flow (phone-first, no account)

### 2.1 `/join/:joinCode` — JoinSession.vue (replaces the scaffold)
1. `GET /api/sessions/by-code/{joinCode}` → 404 renders "invalid join code"; `status: "closed"` renders the
   closed message plus a link to any locally known FIP of that session (read-only).
2. Locale: if `localStorage['fip-language']` is absent, set the locale to `session.defaultLanguage` (when
   supported) before first paint; a stored preference or the switcher always wins and is persisted.
3. Renders the session title, the questionnaire title resolved via `resolveLang` from the new
   `questionnaireTitle` field (§5.1), the facilitator name, and the `LanguageSwitcher`. If
   `localStorage['fipm.editToken.<id>']` exists for a FIP of this session, "Continue your FIP" shows above
   the start form.
4. **Start a FIP** (step 2 of the same view, no extra route): `community.name` (required),
   `community.description` (textarea), `community.domain`, `community.dataSteward.orcid` (optional, pattern
   `\d{4}-\d{4}-\d{4}-\d{3}[\dX]`, client-side hint only). Submit → `POST /api/fips`
   `{questionnaireRef: session.questionnaireRef, sessionId, joinCode, language: <current locale>, community,
   answers: []}` → 201. Store `response.editToken` under `localStorage['fipm.editToken.<fip.id>']`
   **before navigating** (it is returned exactly once), then `router.replace('/fips/<id>/edit')`.
   409 `session_closed` → the closed message; 403 `invalid_join_code` → the invalid-code message.

### 2.2 `/fips/:id/edit` — FipEditor.vue (new)
Load sequence — three requests in parallel; a 404 on the first renders "not found":
- `GET /api/fips/{id}` with `X-Edit-Token` if one is stored → the editable state.
- `GET /api/knowledge-models/{qid}/{qversion}` → sections, question texts, help, `ferType`, `allowMultiple`.
- `GET /api/fers?limit=500` → the whole seed catalogue (69 rows) cached as `id → FerOut`. This one request
  serves both the picker (filtered **client-side** by `type` and query, so typing costs no requests and
  survives a flaky hotspot) and label resolution for already-stored `ferId`s; only if `total > 500` does the
  picker fall back to `GET /api/fers?type=&q=&limit=20` per keystroke (debounced 250 ms). An unknown
  `ferId` displays as its IRI.

Edit rights: `canEdit` = a stored edit token for this id **or** `fip.ownerId === me.id`; otherwise the route
redirects to `/fips/:id`. A device without the token sees the read-only view even for a `link`-visible FIP —
the "second device is read-only" rule.

Layout (mobile-first, single column ≤ 640 px; two columns ≥ 900 px with a sticky section rail): a sticky
header with the community name, `ProgressBar` (`answered / 21`), `SaveIndicator` and `LanguageSwitcher`;
then four collapsible section panels `F/A/I/R` (titles from the knowledge model, `F` open by default), each
holding one `QuestionCard` per question in knowledge-model order.

`QuestionCard` shows: the question id badge (`F1-metadata`), the resolved `text`, the resolved `ferType`
label as a chip (from `GET /api/fer-types`, §5.2), a `<details>` collapsible **Help** with the resolved
`help`, then 0..n `DeclarationEditor` rows, an "Add declaration" button (hidden when `allowMultiple` is
false and one declaration exists) and an optional `comment` textarea.

`DeclarationEditor` = `FerPicker` + `StatusSelect` + optional note + remove button.
- `FerPicker`: a combobox over catalogue FERs of the card's `ferType` (label resolved, homepage as a second
  line), a text input that filters them, and a "Use my own wording" toggle switching the row to a plain input
  that writes `ferFreeText` and clears `ferId`. The two are mutually exclusive, matching the `ferId` xor
  `ferFreeText` validator; a row with neither set is dropped from the PATCH payload (it would 422).
- `StatusSelect`: native `<select>`, the five statuses, labels from `declarationStatus.*`, default `current`.
  `planned-replacement` shows a hint to add a second `planned` declaration for the successor (spec 00 §2).
- Note: single-line input written as `note: {"<fip.language>": "<text>"}` (a one-key LangMap).

### 2.3 Autosave, dirty tracking, indicator
`stores/fipEditor.ts` holds `fip`, `km`, `fers`, `dirty`, `saving`, `lastSavedAt`, `lastError`.
- Any mutation sets `dirty = true` and schedules a save **800 ms** after the last change; a save PATCHes `/api/fips/{id}` with `{answers, community, language}`, `answers` replaced wholesale
  (spec 01 §6, last-write-wins), `X-Edit-Token` sent when stored. At most one request in flight; mutations
  during a flight are coalesced and fire once more on completion if still dirty. No diffing, no ETag.
- Flush immediately (not debounced) on: section collapse, `blur` of a text field, `router` leave guard, and
  `pagehide` (`fetch(..., {keepalive: true})` — `sendBeacon` cannot carry the `X-Edit-Token` header).
- Switching the locale while `canEdit` also sets `fip.language` and marks dirty, so exports resolve in the
  language the group actually used.
- Errors: network/5xx → "Not saved — retrying", retry at 2 s, 5 s, 15 s, then "Not saved" + manual **Retry**.
  `403` → "Edit rights lost on this device"; `409 session_closed` (§5.4) → closed banner. Both go read-only
  with the answers left on screen. `SaveIndicator` (`saved | unsaved | saving | error`) is always visible.

### 2.4 Share, export, print
`ShareBox` (a `<details>` labelled "Share"): the absolute FIP URL `${location.origin}/fips/<id>` in a
readonly input with a copy button (`navigator.clipboard`, falling back to select-all), plus a `QrCode` of it.
`ExportButtons` are plain `<a>` links to `/api/fips/<id>/export.json` and `.../export.csv`
(`Content-Disposition` is already `attachment`; they work for any reader of a `link` FIP, so they live on the
read view, reached from the editor via "Preview / print"). Print = the read view + `print.css` (§6.5).

**QR pick:** npm `qrcode-generator@^1.4.4` (MIT, zero transitive deps, ~12 kB, no canvas) wrapped in
`components/QrCode.vue`, which walks the module count and emits **inline `<svg>` `<rect>`s** — scales
crisply, prints, no server round trip, works on the offline laptop/hotspot fallback. No QR endpoint is added;
spec 01's `qrcode[pil]` backend dependency stays unused in v1.

### 2.5 Returning to a FIP
`/fips/:id/edit` on the same device finds `fipm.editToken.<id>` and edits; any other device gets the
read-only view (`link` visibility makes `GET /api/fips/{id}` succeed without the token). Tokens are never
re-issued. A participant who signs in sees **"Save this FIP to my workspace"** in the editor header, calling
`POST /api/fips/{id}/claim` with the token; on 200 the stored token is deleted and the FIP appears in
`/workspace`. Anonymous session FIPs are `link`-visible (assumption A3, §7).

## 3. Owned FIP flow (signed in)

- `/workspace` (rewritten): three lists from `GET /api/me/{fips,sessions,knowledge-models}`. Each FIP row:
  display name, questionnaire id+version, visibility chip, `updatedAt`, progress, Edit / View / Export links.
  "New FIP" → `/fips/new`; "New session" → `/sessions/new`.
- `/fips/new` (FipNew.vue): `GET /api/knowledge-models?status=published` → radio list (title resolved,
  version shown), then the §2.1 community form. Submit → `POST /api/fips` `{questionnaireRef, language,
  community}` with **no** `sessionId` → 201, `ownerId` set, no `editToken`, `visibility` `private`; navigate
  to `/fips/<id>/edit`, the same editor as §2.2.
- Owner extras in the editor header: a `VisibilitySelect` (`private | link | public`) PATCHing `visibility`
  immediately (not debounced), and **Delete** behind a confirm → `DELETE /api/fips/{id}` → 204 →
  `/workspace`. `ShareBox` is hidden while visibility is `private`.

## 4. Facilitator flow (signed in) and read-only view

### 4.1 `/sessions/new` — SessionNew.vue
Fields: `title` (required), knowledge-model version (`<select>` over
`GET /api/knowledge-models?status=published`, value `id@version`), `defaultLanguage` (`en | pt-PT | pt-BR`,
prefilled from the current locale). `POST /api/sessions` → 201 → `/sessions/<id>`.

### 4.2 `/sessions/:id` — SessionDetail.vue
Projector block, readable from the back of a room: the 6-char `joinCode` at
`font-size: clamp(3rem, 14vw, 8rem)`, `letter-spacing: .12em`, tabular monospace; the `joinUrl` under it at
`clamp(1rem, 3vw, 2rem)`; a `QrCode` of `joinUrl` at 256 px; a "Projector mode" toggle collapsing the app
header. Then `SessionFipList` and the buttons **Close session** / **Export all** / **Comparison matrix**.

- `SessionFipList` renders `GET /api/sessions/{id}/fips` (owner-only, full FIPs): display name,
  `answered / 21` bar computed locally, `updatedAt` as relative time, visibility, View link; sorted by
  `createdAt`; empty state "No FIPs yet — share the join code."
- Live refresh: `setInterval` **10 s** (no websockets in v1), started `onMounted`, cleared `onUnmounted`,
  paused while `document.hidden`, skipped while a poll is in flight; a failed poll shows a "reconnecting" dot
  and does not clear the list. ~8 FIPs of full answers is a few tens of kB per poll, acceptable in a room; if
  it is not, add `?summary=1` later.
- **Close session**: confirm → `PATCH /api/sessions/{id}` `{status:"closed"}` → 200, then a "closed" chip;
  anonymous editors get 409 on their next save (§5.4) and fall back to read-only.
- **Export all**: two `<a>` links to the new `/api/sessions/{id}/export.json` and `.csv` (§5.3).
- `/sessions/:id/matrix` is **reserved now**: a route to `SessionMatrix.vue` holding only a heading and
  "Coming in week 3", so the link never 404s. No logic.

### 4.3 `/fips/:id` — FipRead.vue (replaces FipDetail.vue)
Single data source: `GET /api/fips/{id}/export.json` — it already resolves section titles, question texts,
FER labels and notes in the FIP's language, so this view fetches no knowledge model and no FERs. 404 →
"not found or not shared". Layout: community header (name, description, domain, data steward as an ORCID
link, questionnaire id+version+language, `createdAt`/`updatedAt`); answers grouped by section `F/A/I/R` in
questionnaire order, each question showing its id, text, FER-type chip and declarations as
`label (or free text) + status badge + note`; unanswered questions greyed with "Not answered". Status badges
use five distinct colours **and** always their text label (never colour alone); plus `ExportButtons` (JSON,
CSV) and **Print** (`window.print()`). `AttributionFooter` is mandatory here and in the editor: when the
knowledge model's `license` starts with `CC-BY-SA` it shows the `data/knowledge-models/LICENSE` string —
*"FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, Barbara Magagna, Jacintha Schultes / GO FAIR
Foundation, CC BY-SA 4.0."* — a FIP-Ontology (CC0 1.0) credit and the FIP's own `license`; else only the last.

## 5. API additions and changes (complete list; everything else in spec 01 §6 is reused as-is)

Confirmed sufficient, **no change**: `GET /api/fers?type=&q=&source=&limit=&offset=` (anonymous callers
already see only `source="seed"`, `q` matches `label_search`, `total` returned);
`GET /api/knowledge-models/{id}/{version}` (its `content` carries the per-language `title`/`text`/`help`
maps, which the frontend resolves — no `?lang=` variant needed); `GET /api/knowledge-models?status=published`;
`POST /api/fips`; `PATCH`/`DELETE /api/fips/{id}`; `POST /api/fips/{id}/claim`; `GET /api/me/*`;
`GET /api/fips/{id}/export.{json,csv}`; `POST`/`GET`/`PATCH /api/sessions*`; `GET /api/sessions/{id}/fips`.

| # | Change | Auth | Codes |
|---|---|---|---|
| 5.1 | `GET /api/sessions/by-code/{joinCode}`: **add** `questionnaireTitle: LangMap` (the knowledge model's `title`) to `SessionPublicOut`. Purely additive; saves the join screen a ~60 kB knowledge-model fetch just to show a title. | – | 200, 404 |
| 5.2 | **New** `GET /api/fer-types` → `{"items": [{key, iri, principle, label: LangMap, description: LangMap}], "total": 12}` from `data/fers/fer-types.json` via the existing `fipm.fer_types.get_fer_types()`. New router `routers/fer_types.py`, mounted in `main.py`. Needed for the FER-type chip; the file is not bundled into the SPA because `frontend/tsconfig.json` includes `src/**` only. Cache-Control: `public, max-age=3600`. | – | 200 |
| 5.3 | **New** `GET /api/sessions/{id}/export.json` → `{"exportVersion": 1, "generatedAt", "tool", "session": {id, title, status, joinCode, defaultLanguage, questionnaireRef, facilitatorName, createdAt}, "fips": [<the §3.1 FIP export document, verbatim, one per FIP>]}` and **new** `GET /api/sessions/{id}/export.csv` → the 21 columns of spec 01 §3.2 prefixed by `session_id, fip_title` (= `community.name`), all FIPs concatenated under one header row, FIPs ordered by `createdAt`. Both reuse `build_export_json` / `build_export_csv`; both `Content-Disposition: attachment`. | U (owner) | 200, 404 |
| 5.4 | `PATCH`/`DELETE /api/fips/{id}`: in `fips._authorize_fip_write`, when `fip.session_id` is set and that session's `status == "closed"`, reject with **`409 {"detail":"session_closed"}`** unless the caller is the session owner or an admin. Reads are unaffected. This is what makes assumption A4 true. | T | 409 |
| 5.5 | `SessionPatchRequest.status` is already `SessionStatus = Literal["open","closed"]` (422 on anything else). Add `Language = Literal["en","pt-PT","pt-BR"]` in `schemas.py` and use it for `SessionPatchRequest.default_language`, `SessionCreateRequest.default_language`, `FipCreateRequest.language` and `FipPatchRequest.language`, which are plain `str` today. | U | 422 |

No DB migration, no new table, no change to the spec 01 §3.1/§3.2 export shapes.

## 6. Frontend structure

### 6.1 Router (`src/router/index.ts`, rewritten)
`requiresAuth: false` — `/` Home, `/login`, `/register` (unchanged), `/join/:joinCode` JoinSession,
`/fips/:id` FipRead, `/fips/:id/edit` FipEditor (token or ownership checked inside the view, not by the guard).
`requiresAuth: true` — `/workspace` Workspace, `/fips/new` FipNew, `/sessions/new` SessionNew,
`/sessions/:id` SessionDetail, `/sessions/:id/matrix` SessionMatrix. Route `name` = component name.
A `beforeRouteLeave` guard on `FipEditor` flushes a pending save.

### 6.2 Views — under `src/views/`
`FipEditor.vue`, `FipRead.vue` (delete `FipDetail.vue`), `FipNew.vue`, `SessionNew.vue`, `SessionDetail.vue`
and `SessionMatrix.vue` (placeholder) are new; `JoinSession.vue` is rewritten (its scaffold invents a
`{name, isActive}` session shape that does not exist) and `Workspace.vue` rewritten on `/api/me/*`.

### 6.3 Components — new under `src/components/`
`QuestionCard.vue`, `DeclarationEditor.vue`, `FerPicker.vue`, `StatusSelect.vue`, `QrCode.vue`,
`ProgressBar.vue`, `SessionFipList.vue`, `SaveIndicator.vue`, `ShareBox.vue`, `ExportButtons.vue`,
`StatusBadge.vue`, `AttributionFooter.vue`, `VisibilitySelect.vue`. `LanguageSwitcher.vue` **does not exist
yet** — it is inline in `App.vue`; extract it verbatim (no props; reads/writes `localStorage['fip-language']`,
emits `changed`) and use it in `App.vue`, `JoinSession.vue` and `FipEditor.vue`.

### 6.4 Stores, lib, types
- `stores/fipEditor.ts` — §2.3 behaviour; exports `answeredCount(answers)`, `setDeclaration`,
  `addDeclaration`, `removeDeclaration`, `flush()`, `scheduleSave()`. The debounce delay is a module constant
  so tests can drive it with fake timers.
- `stores/session.ts` — `create`, `load(id)`, `fips`, `startPolling()`, `stopPolling()`, `close()`,
  `loadByCode(joinCode)`.
- `lib/lang.ts` — `resolveLang(map, locale, fallback = 'en')`, mirroring `exporters.resolve_lang`.
- `lib/editTokens.ts` — `getToken/setToken/clearToken(fipId)` over `localStorage['fipm.editToken.<fipId>']`,
  every call in try/catch (private-mode Safari throws).
- `api/types.ts` — DTOs: `FipOut`, `KnowledgeModelOut`, `FerOut`, `FerType`, `SessionOut`,
  `SessionPublicOut`, `Answer`, `Declaration`, `FipExportDoc`.
- `package.json`: add dependency `qrcode-generator@^1.4.4`; devDeps `vitest@^1`, `jsdom@^24`,
  `@pinia/testing@^0.1`; script `"test:unit": "vitest run"`; CI's frontend job gains `npm run test:unit`.

### 6.5 Print stylesheet — `src/assets/print.css`, imported by `FipRead.vue`
`@media print`: hide `.app-header`, `.app-nav`, `.user-info` and `.no-print` (share box, export buttons,
language switcher, print button); `body { background:#fff; color:#000; font-size:10pt }`;
`.section, .question-card { break-inside: avoid; page-break-inside: avoid }`; reveal the FIP URL and
questionnaire ref under the community header via `.print-only { display: block }`; status badges get a 1 px
border instead of a fill; `a[href^="http"]::after { content:" (" attr(href) ")" }` inside the community links
block only; `@page { margin: 15mm }`. Target: 21 questions on ≤ 4 A4 pages.

### 6.6 i18n keys to add (English values; `pt-PT` / `pt-BR` go to the translator agent)
```
join: sessionTitle "Workshop session" · questionnaire "Questionnaire" · facilitator "Facilitator" · startFip "Start a FIP" · continueFip "Continue your FIP" · invalidCode "We don't know that join code." · closed "This session is closed. You can still read the FIPs you created."
community: heading "Your community" · name "Community name" · namePlaceholder "e.g. CONFOA 2026 group A" · description "Short description" · domain "Research domain" · domainPlaceholder "e.g. Public health" · dataSteward "Data steward ORCID" · dataStewardPlaceholder "0000-0002-1825-0097" · orcidInvalid "That does not look like an ORCID iD."
editor: title "Questionnaire" · help "Help" · ferType "Resource type" · addDeclaration "Add a resource" · removeDeclaration "Remove" · note "Why? (optional)" · comment "Notes on this question (optional)" · chooseFer "Choose a resource" · searchFer "Search resources" · useFreeText "Use my own wording" · freeTextPlaceholder "Name the resource your community uses" · useCatalogue "Pick from the catalogue" · noFerMatch "No match — use your own wording." · replacementHint "Also add a second resource with status 'Planned' for the replacement." · progress "{answered} of {total} questions answered" · readOnly "Read-only on this device." · claim "Save this FIP to my workspace" · claimed "Saved to your workspace." · preview "Preview / print" · notAnswered "Not answered"
save: saved "Saved {time}" · unsaved "Unsaved changes" · saving "Saving…" · error "Not saved — retrying" · failed "Not saved" · retry "Retry"
declarationStatus: current "Currently used" · planned "Planned" · plannedDevelopment "To be developed" · plannedReplacement "To be replaced" · none "No choice yet"
share: title "Share" · copyLink "Copy link" · copied "Copied" · qrHint "Scan to open this FIP"
visibility: label "Who can see this FIP" · private "Private" · link "Anyone with the link" · public "Public"
sections: F "Findable" · A "Accessible" · I "Interoperable" · R "Reusable"
sessionAdmin: newTitle "New workshop session" · titleLabel "Session title" · knowledgeModel "Questionnaire version" · defaultLanguage "Default language" · create "Create session" · joinCode "Join code" · joinLink "Join link" · fips "FIPs in this session" · noFips "No FIPs yet — share the join code." · lastUpdate "Last update" · close "Close session" · closeConfirm "Close the session? Participants will no longer be able to edit." · closed "Closed" · exportAll "Export all" · matrix "Comparison matrix" · matrixSoon "The comparison matrix arrives in week 3." · hideChrome "Projector mode" · reconnecting "Reconnecting…"
fipRead: notShared "This FIP does not exist or is not shared." · print "Print" · questionnaire "Answers the questionnaire" · license "Licence"
attribution: questionnaire "Questionnaire content: FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, Barbara Magagna, Jacintha Schultes / GO FAIR Foundation, CC BY-SA 4.0." · ontology "FER types and terms: FIP Ontology, CC0 1.0." · answers "This FIP's answers: {license}."
common (add to the existing block): delete "Delete" · deleteFipConfirm "Delete this FIP? This cannot be undone." · copy "Copy" · close "Close" · retry "Retry" · notFound "Not found"
```

## 7. Assumptions (facilitators away; revisit at the 12 Sep scope freeze)

- **A1. One FIP per group.** A group that starts two gets two FIPs and the facilitator sees both; no
  server-side limit, no warning beyond the "Continue your FIP" hint of §2.1 step 3.
- **A2. The edit token is a device token, not an identity.** Losing browser storage loses edit rights; the
  recovery path is the facilitator, who may already write any FIP of their session.
- **A3. Anonymous session FIPs are created with `visibility: "link"`** (already the backend default) so the
  room can compare and groups can share their URL.
- **A4. Closing a session makes its FIPs read-only for anonymous editors but still readable** (§5.4);
  facilitator and admins keep write access, and FIPs claimed out of the session are unaffected.
- **A5. Last-write-wins, no merge.** Two phones on one FIP overwrite each other's `answers`; the 10 s
  facilitator poll is the only convergence signal. Say so in the facilitator script.
- **A6. Progress counts declarations, not quality** (§1).

## 8. Acceptance criteria

**Backend (pytest, `backend/tests/`)**

1. `GET /api/sessions/by-code/{joinCode}` returns 200 with `questionnaireTitle` containing the knowledge
   model's `en`, `pt-PT` and `pt-BR` titles, alongside the existing fields; an unknown code returns 404.
2. `GET /api/fer-types` returns 200, `total == 12`, keys exactly the 12 of spec 00 §3 in file order, each
   item carrying `iri`, `principle` and a `label` with an `en` value; no auth and no cookie required.
3. `GET /api/sessions/{id}/export.json` as the session owner returns 200 with one entry in `fips` per FIP of
   the session, ordered by `createdAt`, each entry validating as a spec 01 §3.1 document (`exportVersion`,
   `questionnaireRef`, 21 `answers`); a different signed-in user gets 404 and an anonymous client gets 401.
4. `GET /api/sessions/{id}/export.csv` returns `text/csv` with exactly one header row whose columns are
   `session_id, fip_title` followed by the 21 columns of spec 01 §3.2 in that order, and one row per
   declaration across all FIPs of the session (unanswered questions still produce one row each).
5. After `PATCH /api/sessions/{id}` `{"status":"closed"}`, a `PATCH /api/fips/{id}` on an anonymous FIP of
   that session with the correct `X-Edit-Token` returns `409 session_closed`, `DELETE` likewise, while
   `GET /api/fips/{id}` and `GET /api/fips/{id}/export.json` still return 200, and the session owner's
   cookie-authenticated `PATCH` on the same FIP returns 200.
6. `PATCH /api/sessions/{id}` with `{"status":"archived"}` and with `{"defaultLanguage":"fr"}` both return
   422; `{"status":"open"}` and `{"defaultLanguage":"pt-BR"}` return 200. Same for `language` on `POST` and
   `PATCH /api/fips`.
7. A full participant round trip in one test: create a session, `POST /api/fips` with `sessionId` +
   `joinCode`, then 21 sequential `PATCH`es each adding one answer, each with the edit token; the final
   `GET /api/fips/{id}` has 21 answer entries and `GET .../export.csv` has 22 lines (header + 21).
8. `PATCH /api/fips/{id}` returns 422 for a declaration carrying both `ferId` and `ferFreeText`, for one
   carrying neither, and for a `status` outside the five allowed values; with `ferFreeText` only it returns
   200 and the export shows `ferFreeText` set and `fer` null.

**Frontend — vitest (`npm run test:unit`)**

9. `lib/lang.ts` `resolveLang`: exact locale wins; `pt-PT` missing falls back to `pt-BR` then `en`; `pt-BR`
   missing falls back to `pt-PT` then `en`; a map with only `de` returns that value; `null`/`{}` returns
   `null`. The same six cases pass identically against `exporters.resolve_lang` (mirrored in the pytest
   suite as a table test) so the two implementations cannot drift.
10. `stores/fipEditor.ts` with fake timers: one mutation sets `dirty` and issues **no** request before
    800 ms and exactly one after; three mutations 200 ms apart issue exactly one request; a mutation during
    an in-flight request issues exactly one follow-up request after it resolves; `flush()` sends immediately
    and clears `dirty`; a rejected request leaves `dirty` true, sets `lastError`, and retries at 2 s;
    `answeredCount` returns 0 for `[]`, counts an answer whose only declaration has `status: "none"`, and
    ignores an answer with `declarations: []`.

**Frontend — manual script (10 minutes, run before the week-2 demo)**

11. On a real phone at **375 px** width: open `/join/<code>`, confirm the session and questionnaire titles
    render in the session's default language, start a FIP with a community name, answer questions F1-metadata
    and R1.1-data (one catalogue FER + one free-text FER, statuses `current` and `planned-replacement`),
    and confirm no horizontal scrolling, every tap target ≥ 44 px, and the sticky header (progress + save
    indicator) visible throughout.
12. The save indicator goes `Unsaved changes → Saving… → Saved HH:MM` within ~2 s of the last keystroke;
    airplane mode shows `Not saved — retrying`; leaving it recovers to `Saved` with no keystroke lost;
    reloading shows the same answers and progress `2 of 21`. Then **Print** on `/fips/<id>` gives a PDF with
    no app header, no export buttons, all 21 questions with their declarations, the attribution footer, and
    ≤ 4 A4 pages.
13. **Second device is read-only:** open the same `/fips/<id>` URL on a second device (or a private window).
    The read view renders with resolved FER labels and status badges; there is no edit affordance; navigating
    directly to `/fips/<id>/edit` redirects to `/fips/<id>`. Back on the first device, editing still works.
14. Facilitator: `/sessions/new` → the session page shows the join code legibly from 8 m (projector mode),
    the QR scans on a phone to the join URL, the new FIP appears in the list within 10 s with the community
    name and `2 / 21`, `Export all` downloads a JSON with one `fips` entry and a CSV of 22 lines (header + 21),
    `Close session` makes the participant's next edit show the closed banner while the read view still
    works, and `/sessions/:id/matrix` renders the week-3 placeholder rather than a 404.

## 9. Open questions

1. Should a FIP in an **open** session be readable by anyone holding the join code (a "see other groups'
   FIPs" list), or only by its own URL? Assumed: only by URL; comparison goes through the facilitator screen.
2. `answeredCount` treats `status: "none"` as answered; facilitators may prefer the projector progress to
   count only non-`none` declarations — a one-line change if so.
3. Free-text FERs are never promoted into the catalogue in v1. Should a signed-in owner get an "add to my
   resources" button (`POST /api/fers`) already in week 3, so workshop input is harvestable?
