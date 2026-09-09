# Spec 05 – v1 completion: admin, privacy, print, feedback, successor FER, facilitator writes

Status: approved for implementation, 2026-09-09. Covers ROADMAP week 4 (admin pages, privacy notice, printed questionnaire, feedback form) plus two
audit gaps pulled into v1: the successor FER of spec 03 §6 and the facilitator write affordance. Authority: PLAN §5 v1, §7 Identity, §8 Risks, §9;
builds on specs 00–04. Two builders work in parallel: **backend** (§1–§5 API) and **frontend** (§1–§6 UI); §7 splits the files. Existing endpoints are
unchanged except `RegisterRequest`, `UserOut`, `Declaration` and the CSV header — all additive; each section's AC numbers point at §8.

**One schema change for all six features.** `SCHEMA_VERSION` 3 → **4**. `users` gains `must_change_password` (Boolean, NOT NULL, default False) and
`privacy_accepted_version` (String, nullable); one new table `feedback` (§4). `create_all()` adds tables but never columns, so `db.init_db()` gains
`_ensure_columns()`: for each expected `(table, column, ddl)`, `PRAGMA table_info(<table>)` then `ALTER TABLE … ADD COLUMN <ddl>` when absent —
idempotent, logged, run before the `schema_version` reconciliation. No other table is altered; no Alembic.

## 1. Admin pages

New router `backend/fipm/routers/admin.py`, prefix `/admin`, mounted in `main.py`, depending on `require_admin_404` (new in `authz.py`): like
`require_admin` but raising `404 not_found` for anonymous and for signed-in non-admins, so `/api/admin/*` never confirms its own existence
(spec 01 §5's leak rule). `FerSource` gains `user-promoted`; `importer.py` still touches only `source="seed"` rows. Managing system knowledge models
needs no endpoint: `authz` already grants admins write on `owner_id IS NULL` models through the spec 04 routes.

| Method | Path | Body / query | Returns | Codes |
|---|---|---|---|---|
| GET | `/admin/users` | `?q&limit=50&offset=0` | `{items,total}`; item = `id, email, displayName, role, language, createdAt, mustChangePassword, privacyAcceptedVersion, fipCount, sessionCount, knowledgeModelCount` | 200, 404 |
| POST | `/admin/users/{userId}/reset-password` | – | `{temporaryPassword}`, returned **once** | 200, 400, 404 |
| GET | `/admin/fers` | `?pending=1&q&limit&offset` | `{items,total}`; `FerOut` + `ownerEmail`, `usageCount`; `pending=1` filters `source="user"` | 200, 404 |
| POST | `/admin/fers/{ferId}/promote` | – | promoted `FerOut` | 200, 404, 409 |
| POST | `/admin/fers/{ferId}/merge` | `{targetFerId}` | `{repointedDeclarations, repointedFips}` | 200, 400, 404, 409 |

- `q` matches `email` or `display_name`, case-insensitively. The three counts come from three `GROUP BY` queries joined in Python (never N+1):
  `fips.owner_id`, `workshop_sessions.owner_id`, `knowledge_models.owner_id`. `usageCount` = declarations referencing the FER, counted in one Python
  pass over `db.query(Fip.answers)` — O(rows), fine at v1 scale; documented, not indexed.
- **Reset password**: `temporaryPassword` = `ids.temp_password()` — 12 chars of Crockford base32 via `secrets.choice` (no I/L/O/U, dictatable over
  the phone). Sets `password_hash`, `must_change_password=True`, then `revoke_all_sessions(db, user_id)`. Own account → `400 cannot_reset_self` (use
  `POST /api/auth/password`). The plaintext appears in the response body and in no log line.
- **Promote**: `owner_id=NULL`, `source="user-promoted"`; an already `seed`/`user-promoted` row → `409 not_promotable`. Label/type/homepage untouched.
- **Merge**: the target must exist with `source in {seed, user-promoted}` (else `409 invalid_merge_target`); `targetFerId == ferId` → `400 same_fer`.
  Rewrite every FIP's `answers` in Python, replacing `ferId` **and** `successorFerId` (§5) equal to the source with the target, commit only changed
  rows, then `db.delete()` the source. `updated_at` bumps on rewritten FIPs — harmless, the poll re-renders. Irreversible; the UI double-confirms.

**`mustChangePassword` enforcement.** `UserOut` gains `mustChangePassword: bool` and `privacyAcceptedVersion: str | None`; `POST /api/auth/password`
clears the flag on success. `require_user` rejects any **non-GET** `/api/*` request from a flagged user with `403 password_change_required`, except
`/api/auth/password` and `/api/auth/logout` — reads stay open so the SPA renders. Frontend: `router.beforeEach` sends every authenticated
navigation except `ChangePassword` to `/account/password` (new route, `requiresAuth: true`, `views/ChangePassword.vue`: current + new password; on
204 refetch `/api/auth/me` and push the original target or `/workspace`). The temporary password is what the user types as "current".

**UI.** Route `/admin` → `views/Admin.vue`, `meta: { requiresAuth: true }`; the view renders `common.notFound` and calls nothing when
`authStore.user?.role !== 'admin'`, and the nav shows "Admin" only for admins. Two panels: **Users** (search box, table of the eight fields, per row
"Reset password" → confirm → dialog with the temporary password in a `readonly` input, copy button, `admin.tempPasswordOnce`); **FER promotions**
(pending list with type, owner email, usage count; per row "Promote" and "Merge into…", the latter opening `FerPicker` filtered to that FER's type
over `GET /api/fers?limit=500`, then a double confirm). AC 1–4, 14.

```text
admin: title "Administration" · users "Users" · search "Search users" · role "Role" · created "Created" · fips "FIPs" · sessions "Sessions" ·
  models "Models" · resetPassword "Reset password" · resetConfirm "Reset this user's password? Their current password and all their sign-ins stop working." ·
  tempPassword "Temporary password" · tempPasswordOnce "Copy it now — it is shown only once. The user must change it at next sign-in." ·
  pendingFers "Resources awaiting promotion" · noPendingFers "No user-contributed resources." · usage "Used in {count} declarations" ·
  promote "Promote to catalogue" · promoteConfirm "Add this resource to the global catalogue?" · owner "Contributed by" · merge "Merge into…" ·
  mergeConfirm "Merge into {label}? Declarations are re-pointed and this resource is deleted. This cannot be undone." ·
  mergeDone "{declarations} declarations in {fips} FIPs re-pointed."
password: mustChangeTitle "Choose a new password" · mustChangeHint "An administrator set a temporary password for your account. Choose your own to continue." ·
  current "Current password" · new "New password" · submit "Change password" · changed "Password changed."
```

## 2. Privacy notice

Content: one `data/i18n/privacy/<lang>.md` per shipped UI locale (`en`, `pt-PT`, `pt-BR`, `es`) plus `data/i18n/privacy/version.json`
(`{"version": "1.0", "date": "2026-09-12"}`) — **one version for every language**, so `privacyAcceptedVersion` is comparable. New
`routers/privacy.py`: `GET /api/privacy?lang=` → `200 {version, date, lang, markdown}`, `Cache-Control: public, max-age=3600`; `lang` resolves
through the usual chain (`pt-PT ⇄ pt-BR`, `es → en`) and anything unknown falls back to `en`; a missing `en` file → `503 privacy_notice_missing`
(fails loudly in CI, not silently in the room).

`RegisterRequest` gains `privacy_accepted_version: str` (required, non-empty); a value ≠ the current file version → `400 privacy_version_mismatch`
(a stale tab re-fetches and re-asks). Stored on the user and echoed by `UserOut`; nothing else reads it in v1.

**UI.** Public route `/privacy` → `views/Privacy.vue`: fetches `GET /api/privacy` for the current locale and renders it with `lib/markdown.ts`, a
~50-line escape-first renderer for the subset the notice uses (`#`–`###`, paragraphs, `-` lists, `**`, `*`, `[text](url)`, `---`) — no new dependency,
no raw HTML ever inserted. Shows `privacy.version` and re-renders on a language switch. Linked from (a) `Register.vue`: a **required** checkbox
`privacy.accept` with an inline link, submit disabled until ticked, the fetched version sent as `privacyAcceptedVersion`;
(b) `JoinSession.vue`: the `privacy.joinNotice` line with the link directly above "Start a FIP" (no checkbox — participants have no account, A2);
(c) `components/SiteFooter.vue`, rendered by `App.vue` under `<router-view>`, holding the privacy link and `appName` (class `no-print`). AC 5–7, 15.

```text
privacy: title "Privacy notice" · version "Version {version}, {date}" · link "Privacy notice" · accept "I have read the privacy notice." ·
  required "Please read and accept the privacy notice." ·
  joinNotice "Your answers are stored by this tool and shared with the workshop facilitator. See the {link}."
```

### 2.1 Draft English notice (`data/i18n/privacy/en.md`; translators produce pt-PT, pt-BR and es)

```markdown
# Privacy notice
Version 1.0 — 12 September 2026. FIP Manager is a research tool operated for the CONFOA 2026 FIP workshop by
the facilitators named below. This notice says what it stores and for how long.
## If you create an account
We store your email address, display name, an argon2id hash of your password (never the password), your
preferred language, and the version of this notice you accepted — only to sign you in and to show you your
own FIPs, sessions and knowledge models. No marketing, no third parties, no analytics. There is no email
password reset in this version: an administrator sets a temporary password.
## If you take part in a workshop without an account
No account, name or email is needed. Your group's answers are stored with the workshop session and are
visible to the facilitator and to anyone with the FIP's link. Your browser keeps an edit token so your
device can keep editing that FIP; we use no tracking cookies.
## Content you enter
Community name, description, research domain, an optional ORCID iD and your answers are part of the FIP and
appear in its JSON, CSV and RDF exports. Do not enter personal data about other people.
## How long we keep it
Workshop session data is kept until the facilitator deletes the session, and in any case no longer than 12
months after the workshop. Accounts and the FIPs you own are kept until you delete them; deleting your
account removes it and anonymises the FIPs it leaves behind, so workshop results and FIP links stay usable.
## Your rights and contact
You can read, change, export or delete your data in the app at any time. For access, correction or erasure
requests, or any question about this notice, write to l.o.boninodasilvasantos@utwente.nl.
```

## 3. Printed questionnaire fallback (PLAN §8 "Room Wi-Fi fails")

No API change: `GET /api/knowledge-models/{id}/{version}` is the only call. Public route `/knowledge-models/:id/:version/print` →
`views/KnowledgeModelPrint.vue` (`requiresAuth: false`; 404 renders `common.notFound`), with `?declarations=1|2|3` (default 3) behind a `no-print`
`<select>` so a facilitator can shorten the handout. Only questions with `hidden !== true` are rendered (spec 04 §4); every text goes through
`resolveLang(_, locale)`, so the language switcher drives the printout.

1. **Title page** — model title + `id@version`, the section list, `print.instructions`, and ruled hand-fill lines for group/table number, community
   name, short description, research domain, data steward ORCID and date; then a page break.
2. **Per section** — the section title as a running heading, then per question: the question-id badge, the question text, the FER-type label as
   `print.ferType`, and the resolved `help` printed in full (never a `<details>`).
3. **Per question** — `declarations` identical numbered blocks, each a ruled `print.resource` line, a row of five 3.5 mm tick boxes labelled with the
   five `declarationStatus.*` texts, and a ruled `editor.note` line; after the last block, one ruled `editor.comment` line.
4. **Footer** — the two `attribution.*` strings plus `print.footerTool`, `position: fixed; bottom: 0` so it repeats on every sheet; no page numbers.

New `src/assets/print-questionnaire.css`, imported by the view: `@page { size: A4 portrait; margin: 14mm }`; hides `.app-header`, `.app-nav`,
`.site-footer`, `.no-print`; `body { background:#fff; color:#000; font-size:10pt }`; `break-inside: avoid` on `.question, .decl-block` and
`break-before: page` on `.section`; ruled lines `border-bottom:1px solid #000; height:6mm`; tick boxes 3.5 mm with a 1 px black border. On screen the
same DOM shows with a Print button calling `window.print()`. Target ≈ 12 A4 pages at 3 blocks, ≈ 6 at 1. Entry points: the action rows of
`KnowledgeModelRead.vue` and of `SessionDetail.vue` (building the link from `session.questionnaireRef`) each gain a `router-link`. AC 8, 16.

```text
print: questionnaire "Print questionnaire" · handoutTitle "FIP questionnaire — paper fallback" · group "Group / table" · date "Date" ·
  resource "Resource" · declarationsPerQuestion "Resources per question" · ferType "Resource type" ·
  footerTool "Filled-in sheets are typed into FIP Manager after the session." ·
  instructions "Tick one status per resource. Leave a block empty if your community has none."
```

## 4. Feedback form

New table `feedback`: `id` str(26) pk (`secrets.token_hex(13)`), `session_id` FK `workshop_sessions.id ON DELETE SET NULL` nullable, `fip_id` FK
`fips.id ON DELETE SET NULL` nullable, `q1`/`q2`/`q3` Integer NOT NULL, `comment` Text nullable, `language` String, `created_at`; index on
`session_id`. **Anonymous by construction**: no `user_id`, no IP, no edit token stored — the client IP is used by the rate limiter and discarded.
New config `FIPM_FEEDBACK_ENABLED: bool = True`. **The three questions are the `feedback.q1`–`q3` strings below**, on a 1–5 Likert scale (1 = strongly
disagree, 5 = strongly agree), with the free text `feedback.comment`; that block is their authoritative English wording.

| Method | Path | Auth | Essentials | Codes |
|---|---|---|---|---|
| POST | `/feedback` | – | `{q1,q2,q3, comment?, sessionId?, fipId?, language?}`; scores `Field(ge=1, le=5)`, comment ≤ 2000 chars → `201 {"status":"recorded"}` | 201, 403, 404, 422, 429 |
| GET | `/sessions/{id}/feedback` | U (owner/admin) | `{responses, questions:[{key, mean, counts:{"1".."5"}}], comments:[{text, createdAt}]}`; `mean` 2 dp, `null` at 0 responses | 200, 404 |
| GET | `/sessions/{id}/feedback.csv` | U (owner/admin) | `session_id, created_at, q1, q2, q3, comment`; BOM, CRLF, `_write_csv_row` formula guard, `attachment` | 200, 404 |

CSRF applies as to every write (spec 01 §4). Rate limit **5 per hour per client IP** in the same in-process limiter → `429` + `Retry-After`. A
`sessionId`/`fipId` that does not resolve → `404 not_found`; both may be omitted (feedback from a printed-handout room). With
`FIPM_FEEDBACK_ENABLED=false` the POST returns `403 feedback_disabled` while both GETs keep working, so collected data stays readable; the session
routes reuse `sessions._get_owned_session`.

**UI.** `components/FeedbackForm.vue` (props `sessionId?`, `fipId?`): three radio groups of five with the two anchor labels shown once, a textarea,
submit → thank-you state. After a `201` it writes `localStorage['fipm.feedback.<sessionId ?? fipId ?? "global">'] = 'done'` (try/catch) and stays
hidden on that device; there is deliberately no server-side de-duplication, and a `403 feedback_disabled` hides the form entirely. It sits (a) in
`FipEditor.vue` as a `<details>` under `ExportButtons`, once `answeredCount > 0 && store.saveState === 'saved'`, and (b) on `SessionDetail.vue`, which
also renders `components/FeedbackSummary.vue`: response count, a 1–5 bar row plus mean per question, the comments, and an `<a>` to the CSV. AC 9–11, 17.

```text
feedback: title "Two minutes of feedback?" · intro "Anonymous. It helps us improve the tool and the workshop." ·
  q1 "The questionnaire was easy to understand." · q2 "The tool was easy to use on my device." ·
  q3 "I understand better now what a FAIR Implementation Profile is." · comment "What should we change? (optional)" ·
  scaleLow "Strongly disagree" · scaleHigh "Strongly agree" · submit "Send feedback" · thanks "Thank you." ·
  error "Feedback could not be sent." · summaryTitle "Feedback" · responses "{count} responses" · mean "Average {mean}" ·
  noResponses "No feedback yet." · comments "Comments" · exportCsv "Export feedback (CSV)"
```

## 5. Successor FER on planned-replacement declarations (closes spec 03 §6)

`schemas.Declaration` gains `successor_fer_id: str | None = None` and `successor_free_text: str | None = None` inside the `answers` JSON — **no DB
change, fully backwards compatible** (absent keys read as `None`; old FIPs validate and export unchanged). A `_successor_rules` validator beside
`_fer_xor` enforces: at most one of the two set (`successor_xor`), and both `None` unless `status == "planned-replacement"`
(`successor_requires_planned_replacement`); violations are `422`.

- **RDF** (`rdf.py`, superseding the "does **not** auto-emit" sentence of spec 03 §2.3): for a `planned-replacement` declaration with a successor,
  call `_emit_fer` with `{"ferId": successorFerId, "ferFreeText": successorFreeText}` and `status="current"` so the successor is typed
  `fip:Available-FAIR-Enabling-Resource`, then add `fip:declares-planned-use-of <successor>` **on the same declaration node**, next to
  `fip:declares-planned-replacement-of` — the spec 00 §2 ontology note. Nothing extra when no successor is set.
- **CSV**: `CSV_HEADER` gains `successor_fer_id, successor_fer_label` **at the end** (23 columns; `SESSION_CSV_HEADER` becomes 25 by splicing, no code
  change). The label is the `fers` row's label resolved in the FIP's language, else the successor free text, else `""`. Supersedes the "21 columns"
  wording of spec 01 §3.2 / §9.11.
- **JSON export** (spec 01 §3.1): each declaration gains `"successor": {id, label, type, homepage} | null`, enriched exactly like `fer`, and
  `"successorFreeText": string | null`. `POST /api/fips/import` maps `successor.id` → `successorFerId` and `successorFreeText` back, so spec 01
  AC 10's round trip still holds.
- **Editor**: `DeclarationEditor.vue` renders a second `FerPicker` labelled `editor.successor` on its own row **only** while
  `declaration.status === 'planned-replacement'`, mapping its `{ferId, ferFreeText}` payload to `{successorFerId, successorFreeText}`.
  `stores/fipEditor.setDeclaration` clears both fields whenever a status change moves away from `planned-replacement`, so no `422` can ever be saved.
  The old `editor.replacementHint` string is replaced by `editor.successorHint`.
- **Matrix**: `MatrixChip` gains `successorLabel: string | null`, resolved in `lib/matrix.ts` like `label`; `MatrixCell.vue` appends
  `matrix.successor` to the chip's `title`/`aria-label` and shows it under the chip when the note is toggled. `FipRead.vue` shows `→ label` after the
  status badge. AC 12–13, 17.

```text
editor: successor "Replaced by" · successorHint "Name the resource that will replace it."
matrix: successor "→ replaced by {label}"
```

## 6. Facilitator write affordance (no API change)

The backend already lets a session owner write any FIP of their session, before and after close (`fips._authorize_fip_write`); only the UI was missing.

- `SessionFipList.vue` gains a prop `canOpen?: boolean`; when true each row also renders an **Open** `router-link` to `/fips/{id}/edit` beside
  **View**. `SessionDetail.vue` passes it (that view is owner-only, so always true there).
- `stores/fipEditor.ts` gains `facilitatorWrite` (ref, default false). In `load()`, when
  `fip.sessionId && authStore.isAuthenticated && !getToken(fip.id) && fip.ownerId !== authStore.user?.id`, probe `GET /api/sessions/{fip.sessionId}`
  once: `200` → `true`, anything else → false. That endpoint is owner/admin-only and already 404s otherwise, so it *is* the permission check.
  `canEdit` becomes `owner || storedToken || facilitatorWrite`, which also stops `FipEditor.init()` from bouncing the facilitator to the read view.
- `FipEditor.vue` shows `editor.facilitatorBanner` while `facilitatorWrite` is true; claim, visibility and delete stay gated on real ownership, and
  a closed session still blocks anonymous and non-owner writes exactly as before. AC 14, 17.

```text
sessionAdmin: open "Open"
editor: facilitatorBanner "You are editing as the facilitator."
```

## 7. Work split

**Backend (pytest):** `db` (`SCHEMA_VERSION`, `_ensure_columns`), `models` (two `User` columns, `Feedback`), `ids.temp_password`,
`authz.require_admin_404`, `routers/{admin,privacy,feedback}.py` + the two session feedback routes and `main.py` mounts, `schemas`, `exporters.py`,
`rdf.py`, `config.feedback_enabled`, the `require_user` guard, `data/i18n/privacy/*`. **Frontend (vitest + one manual pass):**
`views/{Admin,ChangePassword,Privacy,KnowledgeModelPrint}.vue`, `components/{SiteFooter,FeedbackForm,FeedbackSummary}.vue`, `lib/markdown.ts`,
`assets/print-questionnaire.css`, and edits to `Register.vue`, `JoinSession.vue`, `App.vue`, `SessionDetail.vue`, `SessionFipList.vue`, `FipEditor.vue`,
`FipRead.vue`, `DeclarationEditor.vue`, `MatrixCell.vue`, `lib/matrix.ts`, `stores/fipEditor.ts`, `router/index.ts`, `i18n/en.json`.

## 8. Acceptance criteria

**Backend (pytest, `backend/tests/`)**

1. `GET /api/admin/users` returns `404 not_found` for anonymous and for a signed-in non-admin, and `200` for an admin whose items carry
   `fipCount`/`sessionCount`/`knowledgeModelCount` equal to the rows actually owned; `?q=` matches email and display name case-insensitively.
2. `POST /api/admin/users/{id}/reset-password` returns a 12-char `temporaryPassword`; the old password then fails login and the temporary one succeeds,
   every pre-existing `auth_sessions` row of that user is gone, and the same call on the admin's own id returns `400 cannot_reset_self`.
3. A user with `mustChangePassword` gets `403 password_change_required` on `PATCH /api/fips/{id}` but `200` on `GET /api/auth/me`;
   `POST /api/auth/password` succeeds, clears the flag, and the same `PATCH` then returns `200`.
4. `POST /api/admin/fers/{id}/promote` sets `ownerId=null` and `source="user-promoted"` and makes the FER visible to an anonymous `GET /api/fers`; a
   second promote → `409 not_promotable`. `.../merge` re-points every `ferId` **and** `successorFerId` equal to the source across all FIPs, deletes
   the source row, reports the counts, and rejects a `source="user"` target with `409 invalid_merge_target`.
5. `GET /api/privacy?lang=pt-PT` and `?lang=es` return that language's markdown, `?lang=de` and no `lang` return `en`, and every response carries the
   `version` of `data/i18n/privacy/version.json`.
6. `POST /api/auth/register` without `privacyAcceptedVersion` returns `422`, with a wrong version `400 privacy_version_mismatch`, and with the
   current version `201` — stored on the user and echoed by `GET /api/auth/me`.
7. Startup and `import-data` on a DB created at `SCHEMA_VERSION` 3 add the two `users` columns and the `feedback` table with no data loss, and
   change nothing on a second run.
8. `POST /api/feedback` with scores in 1–5 returns `201` and stores no user id or IP; `0` or `6` → `422`; a 6th post from one IP inside an hour →
   `429` with `Retry-After`; an unknown `sessionId` → `404`; with `FIPM_FEEDBACK_ENABLED=false` → `403 feedback_disabled`.
9. `GET /api/sessions/{id}/feedback` returns `404` for a non-owner and, for the owner, the exact counts, 2-dp means and free texts of the posted rows
   (`responses: 0`, `mean: null` when empty); `feedback.csv` returns the six columns with a BOM and CRLF.
10. Deleting a session (or a FIP) leaves its feedback rows with `sessionId`/`fipId` `NULL`, and its FIPs' feedback stays exportable from the CSV route.
11. A declaration with `successorFerId` and `status != "planned-replacement"` returns `422`, as does one with both successor fields; a
    `planned-replacement` declaration with neither still saves.
12. `export.ttl` of a `planned-replacement` declaration with a successor carries, on the **same** declaration node, both
    `fip:declares-planned-replacement-of` and `fip:declares-planned-use-of`, and types the successor `fip:Available-FAIR-Enabling-Resource`; a FIP
    stored before this change serialises byte-identically to before.
13. `export.csv`'s header is exactly the 21 spec-01 columns plus `successor_fer_id, successor_fer_label` (23; session CSV 25), the label resolves in
    the FIP's language, and `export.json` → `POST /api/fips/import` round-trips both successor fields.

**Frontend (vitest unit + one manual pass)**

14. Manual: a non-admin visiting `/admin` sees `common.notFound` with no `/api/admin/*` request in the network log and no "Admin" nav link, while an
    admin sees the user table, resets a password and gets the temporary password once in a dialog with a working copy button. A facilitator uses "Open"
    on `SessionDetail`, lands in the editor with the `editor.facilitatorBanner` banner, edits, and the change saves — also after close.
15. `Register.vue`: submit stays disabled until the privacy checkbox is ticked and the POST body carries the version from `GET /api/privacy` (vitest,
    mocked API). `/privacy` renders headings, lists and links and escapes an injected `<script>` tag as text (`lib/markdown.ts` unit test), and a
    language switch re-renders it in `pt-BR`.
16. Manual: `/knowledge-models/gofair-fip-mini/1.0.0/print` prints from Chrome as A4 portrait with the title page, every non-hidden question with its
    help text, three declaration blocks of five tick boxes, the attribution footer on every sheet, no app chrome and no question split across a page
    break; `?declarations=1` roughly halves the page count; the switcher changes the printed language.
17. `FeedbackForm` posts once and stays hidden on reload of the same device (vitest, stubbed `localStorage`); `buildMatrix` returns
    `successorLabel` for a `planned-replacement` chip and `null` otherwise and `MatrixCell` puts it in the chip's `title` (vitest);
    `DeclarationEditor` shows the second picker only for `planned-replacement` and clears both successor fields when the status changes away.

## 9. Assumptions (facilitators away; revisit at the 12 Sep scope freeze)

- **A1. Retention** is exactly as §2.1 states: session data until the facilitator deletes the session and in any case ≤ 12 months after the workshop;
  accounts and owned FIPs until the user deletes them, deletion anonymising rather than removing FIPs (spec 01 §10.3 — the notice now says so).
  Nothing enforces the 12 months in code: it is an operator promise plus a calendar reminder.
- **A2. Anonymous participants tick nothing.** No account, name or email is collected, so the notice link plus `privacy.joinNotice` on the join
  screen is the whole obligation; only registration records consent.
- **A3. The three feedback questions and their English wording are as written in §4**, unchanged for the workshop; changing them later means new keys,
  not re-scaled old rows (there is no question-version field).
- **A4. Temporary passwords are 12 random Crockford-base32 characters, shown once**, delivered out of band, forcing a change at next sign-in (no SMTP,
  no reset links — PLAN §7).
- **A5. One privacy-notice version across all languages**: a translation fix that does not change meaning reuses the version, a substantive change
  bumps it, and v1 does not re-prompt existing users.
- **A6. One successor per declaration.** Replacing one resource with two means a second `planned-replacement` declaration.
- **A7. Merge is irreversible** and re-points by `ferId` only; free-text declarations naming the same resource are untouched.

## 10. Open questions for the facilitators

1. Contact point in the notice: L. O. Bonino's UT address (assumed) or a Fiocruz/ICTIC one once hosting is decided (PLAN §9.3)?
2. Should the feedback form also appear on `FipRead.vue` (for a group that closed the editor), or are the editor and session pages enough?
3. Is the 12-month retention ceiling right (A1), or should session data go once the report is written? And may an admin promote a FER whose IRI does not resolve?

## Reconciliation note (9 Sep 2026, orchestrator)

Spec 06 (DMP linkage) is implemented before this spec and appends three CSV columns (`dmp_url`, `dmp_section`, `dmp_question`) to the FIP export, making 24. This spec's two successor columns (`successor_fer_id`, `successor_fer_label`) are appended **after** those, so the final FIP CSV header has 26 columns and the session CSV 28 (session_id, fip_title + 26). Spec 01 §3.2 and §9.11 describe the original 21 columns, which remain the first 21 in the same order.
