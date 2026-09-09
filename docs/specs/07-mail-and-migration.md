# Spec 07 – Mail-backed account flows and FIP migration between model versions

Status: draft for v2, 2026-09-09. Two v2 items needing no external decision (PLAN §5 v2: "email verification and self-service
password reset once SMTP is configured"; "FIP migration between knowledge-model versions (DSW-style), with a diff view").
Authority: `01-foundations.md` §2 (tables), §4 (auth), §5 (authz), §6 (API), §7 (config); `04-knowledge-model-editor.md` §1
(lifecycle, immutable published versions) and §2 (ids, hidden, split); `03-matrix-and-rdf.md` §2 (RDF shapes); PLAN §4, §7.
Nothing here is needed on 6 Oct: **both features are off or invisible by default** (`FIPM_MAIL_BACKEND=console`,
`FIPM_REQUIRE_EMAIL_VERIFICATION=false`; the migration banner appears only once a newer *published* model version exists).

## 0. Shared schema change (`SCHEMA_VERSION = 1 -> 2`)

One bump covers both features. New table + three nullable columns, all additive:

| Change | Shape |
|---|---|
| new table `email_tokens` | `id` str(64) pk = sha256 hex of the token, `user_id` fk users.id ON DELETE CASCADE, `purpose` str `verify_email\|password_reset`, `email` str (address the token was issued for), `created_at`, `expires_at`, `used_at` nullable; index `(user_id, purpose)`, index `expires_at` |
| `users.email_verified_at` | `DateTime(timezone=True)` nullable |
| `fips.migrated_from` | JSON nullable — `{"id","version","at"}`, the version migrated **from** on the last migration |
| `fips.orphaned_answers` | JSON nullable list, §4.4 |

`db.init_db()` keeps `create_all()` (which makes `email_tokens`) and gains one guarded step: for each of the three columns,
`PRAGMA table_info(<table>)` and, if absent, `ALTER TABLE <table> ADD COLUMN <col> <type> NULL`. Still no Alembic (spec 01 §1); the
guard is idempotent, runs before the `schema_version` upsert, and is the only hand-written DDL. A v1 DB upgrades in place.

## 1. Mail backend (`backend/fipm/mail.py`)

| Var | Default | Notes |
|---|---|---|
| `FIPM_MAIL_BACKEND` | `console` | `console \| smtp`; unknown value → refuse to start |
| `FIPM_MAIL_FROM` | `FIP Manager <no-reply@localhost>` | RFC 5322 address, used as `From` |
| `FIPM_SMTP_HOST` / `FIPM_SMTP_PORT` | unset / `587` | required when backend is `smtp` (else refuse to start) |
| `FIPM_SMTP_USER` / `FIPM_SMTP_PASSWORD` | unset | omitted → unauthenticated relay |
| `FIPM_SMTP_TLS` / `FIPM_SMTP_TIMEOUT` | `starttls` / `10` | `starttls \| ssl \| none`; timeout in seconds |
| `FIPM_REQUIRE_EMAIL_VERIFICATION` | `false` | §2 gate |
| `FIPM_MAIL_TOKEN_TTL_HOURS` / `FIPM_RESET_TOKEN_TTL_HOURS` | `24` / `1` | token lifetimes |

`send_mail(to, subject, text, html=None) -> None` builds an `EmailMessage` (`text/plain; charset=utf-8`, `html` as an alternative
part when given) and dispatches per backend: **console** logs one INFO record on logger `fipm.mail` (`MAIL to=… subject=…` plus the
indented body) — so with no SMTP an admin reads the verification or reset link out of `docker compose logs fipm`, the documented
fallback next to spec 05's admin temporary-password path; **smtp** uses `smtplib.SMTP`/`SMTP_SSL`. Startup logs one WARNING when
`FIPM_ENV=production` and the backend is `console` ("account mail only reaches the log; links are readable by anyone with log access").

`render_mail(template, lang, ctx) -> (subject, text)` reads `data/i18n/mail/{lang}/{template}.txt`, whose **first line** is
`Subject: …` with the body after one blank line; placeholders are `{name}` filled by `str.format(**ctx)` (keys `displayName`,
`link`, `appName`, `baseUrl`, `expiresHours`). Language resolution reuses the UI chain `pt-PT ⇄ pt-BR → en`, extended with
`es → en`; all four directories `en`, `pt-PT`, `pt-BR`, `es` exist from the first commit (an untranslated file may be a copy of
`en`, never missing — absence is a test failure, not a runtime surprise). Templates in v2: `verify-email.txt` and
`password-reset.txt`; an optional sibling `{template}.html` is passed as `html` when present.

Every send runs in a FastAPI `BackgroundTasks` callback wrapped in `try/except Exception` that logs and swallows: mail must never
turn a 201/202 into a 500, and the caller must not learn from timing whether a mailbox exists.

## 2. Email verification

- On `POST /api/auth/register`, after the user row commits, issue a `verify_email` token and queue the mail; the response is
  unchanged (201 + cookie). `UserOut` gains `emailVerifiedAt: str | null` and `GET /api/auth/me` also returns
  `verificationRequired: bool` (the setting), so the SPA knows whether to nag.
- Token: `ids.new_token()` (32 random bytes, urlsafe), **only the sha256 hex is stored** as `email_tokens.id`; the plaintext lives
  in the mail and nowhere else. TTL 24 h, single use (`used_at`); issuing a new token of a purpose deletes that user's earlier
  unused ones of the same purpose. Link: `{FIPM_BASE_URL}/verify?token=…`.
- `POST /api/auth/verify-email {token}` (no auth — the token is the credential): look up `hash_token(token)`; unknown, used, or
  `email` no longer matching `users.email` → 400 `invalid_token`; expired → 410 `token_expired` (a distinct code only so the UI can
  offer "send a new link"; the token is a secret, so no enumeration surface). Success: set `email_verified_at` and `used_at`,
  return 200 `UserOut`. Replays are 400, by design.
- **Gate rule (one line):** while `FIPM_REQUIRE_EMAIL_VERIFICATION=true`, an unverified user may do everything except make content
  world-listed — any write that would set `visibility="public"` on a FIP, knowledge model or FER returns **403
  `email_verification_required`**. It is the smallest rule that stops spam in the public listings while leaving sign-in, `private`
  and `link` work, sessions and session-joining untouched, so flipping the flag mid-course never breaks a room.
- `POST /api/auth/verify-email/resend` (U) → 202 always, even when already verified (no state leak, no mail then). Rate limit via
  `auth.RateLimiter`: 3/hour per user id, 10/hour per client ip → 429 with `Retry-After`. Changing the account email (spec 05)
  clears `email_verified_at`; the stored `email_tokens.email` invalidates outstanding tokens automatically.

## 3. Password reset

- `POST /api/auth/password-reset/request {email}` → **always 202, empty body**, whether the address exists, is malformed or is
  already mid-reset. Only on a match: issue a `password_reset` token (TTL 1 h, single use, same hashing) and queue
  `password-reset.txt` with link `{FIPM_BASE_URL}/reset-password?token=…`. Rate limit 3/hour per lowercased email and 10/hour per
  ip; **over-limit also returns 202** (no 429 — a 429 keyed on an email is itself an enumeration oracle): the limiter drops and
  logs the mail instead.
- `POST /api/auth/password-reset/confirm {token, newPassword}` → 204. Validation: token unknown/used/email-mismatch → 400
  `invalid_token`; expired → 410 `token_expired`; `newPassword` outside 10–128 chars → 400 (`RegisterRequest`'s validator, reused).
  Effects, in one transaction: argon2id rehash of the password, `used_at` set, **every** `auth_sessions` row of that user deleted
  (including the caller's — a reset means "I may have been compromised", so it logs out every device; the SPA then shows the login
  form), and `email_verified_at` set if it was null (completing a reset proves control of the mailbox).
- With `FIPM_MAIL_BACKEND=console` the reset link appears in the log, so a self-hosted single-facilitator deployment can use this
  flow without SMTP; spec 05's admin temporary-password path stays the no-mail-at-all route, unchanged.
- Frontend: `/forgot-password` (`ForgotPassword.vue`, email field → always the same "check your inbox" panel); `/reset-password`
  (`ResetPassword.vue`, reads `?token=`, new password + confirm, on 204 routes to `/login` with a flash, on 410 links back to
  `/forgot-password`); `/verify` (`VerifyEmail.vue`, posts the token on mount, renders success / expired / invalid).
  `Login.vue` already has `auth.forgotPassword` — point it at `/forgot-password`. `Workspace.vue` shows a dismissible "Confirm your
  email address" banner with a Resend button when `verificationRequired && !emailVerifiedAt`.

## 4. FIP migration – semantics

A FIP answering model `X` version `V` may migrate to a version `W` of the **same model id** `X` that is `published` (spec 04 §1),
readable by the caller and strictly greater than `V` by semver. **Same id only in v2**: crossing a fork would mean mapping
`forkedFrom` lineage and diverging question ids at once, so v2 offers "a model's own successors" and cross-fork stays open (§10.1).

**Session FIPs are pinned.** If `fip.session_id IS NOT NULL` and the target differs from that session's `questionnaire_version`,
`POST …/migrate` returns **409 `session_version_pinned`**. Rationale: the matrix and the session-wide export align every FIP of a
session by question id *within one model version* (spec 03 §1.2), so one group moving to 1.1.0 would drop columns from the room's
matrix and produce a session CSV whose rows no longer share a questionnaire. Claiming keeps `session_id` (spec 01 §5), so the
escape hatch is a facilitator-level "migrate the whole session" — open question §10.2.

### 4.1 Diff algorithm (`backend/fipm/migration.py`, mirrored in `frontend/src/lib/migration.ts`)

Input: the two `content` documents and the FIP's `answers`. Iterate the **target** in section/question order, then the source's
leftovers. A question id carrying at least one declaration or a non-empty comment counts as "answered".

| Status | Detection | Effect on answers |
|---|---|---|
| `unchanged` | id in both, visible in target | answer kept verbatim |
| `added` | id only in target | no answer created |
| `removed` | id answered but absent from the **target** (whether or not it was in the source — covers FIPs that already drifted) | answer moved to `orphanedAnswers`, or re-assigned per decision |
| `hidden` | id in both, `hidden === true` in target | answer kept in `answers`, not exported (spec 04 §4) |
| `split` | id absent from target while both `<id>-metadata` and `<id>-data` are present in the target and absent from the source | decision: copy the answer to both (default), one, or neither (then it orphans) |

Non-exclusive flags on an `unchanged`/`hidden` item: `text-changed` when the **`en`** `text` differs after whitespace
normalisation (`en` is mandatory per spec 04 §3.3, so both sides always exist); `fer-type-changed` and `scope-changed` likewise —
declarations are kept either way (a FER reference is a free IRI, never re-typed), the flag only lets the review page say "this
question now asks for a different kind of resource". `required`, `allowMultiple` and `principle` are not diffed in v2 (§10.3).

### 4.2 Diff JSON (`diffVersion: 1`)

```json
{"diffVersion": 1, "generatedAt": "2026-11-02T10:00:00Z",
 "from": {"id": "gofair-fip-mini", "version": "1.0.0"},
 "to":   {"id": "gofair-fip-mini", "version": "1.1.0", "changelog": [{"version": "1.1.0", "date": "…", "notes": "…"}]},
 "counts": {"unchanged": 18, "added": 2, "removed": 1, "hidden": 1, "split": 1,
            "textChanged": 3, "ferTypeChanged": 1, "answersKept": 17, "answersOrphaned": 1, "decisionsRequired": 2},
 "items": [
   {"status": "unchanged", "oldQuestionId": "F1-metadata", "newQuestionId": "F1-metadata", "oldText": "…en…", "newText": "…en…",
    "oldFerType": "identifier-service", "newFerType": "registry", "flags": ["text-changed", "fer-type-changed"],
    "answered": true, "declarationCount": 2, "decision": null},
   {"status": "added", "oldQuestionId": null, "newQuestionId": "R1.3-data", "newText": "…", "answered": false, "decision": null},
   {"status": "split", "oldQuestionId": "F2", "newQuestionId": null, "splitInto": ["F2-metadata", "F2-data"], "answered": true,
    "declarationCount": 1, "decision": {"kind": "splitCopies", "options": ["F2-metadata", "F2-data"], "default": ["F2-metadata", "F2-data"]}},
   {"status": "removed", "oldQuestionId": "A2", "newQuestionId": null, "oldText": "…", "answered": true,
    "decision": {"kind": "orphanReassign", "options": ["A2-metadata", "F4-data"], "default": null}},
   {"status": "hidden", "oldQuestionId": "F3", "newQuestionId": "F3", "flags": [], "answered": true, "decision": null}]}
```
`orphanReassign.options` are the target's **unanswered, non-hidden** ids whose `ferType` equals the removed question's (or all
unanswered non-hidden ids when it had none), keeping the picker short and type-honest. Texts are raw `en`; the frontend resolves
the display language itself from the loaded models.

### 4.3 API

| Method | Path | Auth | Request → Response | Codes |
|---|---|---|---|---|
| GET | `/api/fips/{id}/migration-targets` | same as write | `{"current": {"id","version"}, "items": [{"id","version","title","changelog","publishedAt"}], "total": n}` — published, readable, semver-greater versions of the same model id, ascending; `[]` when none | 200, 403, 404 |
| GET | `/api/fips/{id}/migration-preview?to={version}` | same as write | the §4.2 document; unreadable/absent/non-published target → 404 `target_not_found`; not greater → 400 `version_not_greater` | 200, 400, 403, 404 |
| POST | `/api/fips/{id}/migrate` | same as write | `{"to": "1.1.0", "decisions": {"splitCopies": {"F2": ["F2-metadata"]}, "orphanReassign": {"A2": "A2-data"}}}` → 200 the updated FIP | 200, 400, 403, 404, 409 |

Authorization is exactly `PATCH /api/fips/{id}` (owner, admin, or a valid `X-Edit-Token`); unreadable → 404, readable but not
writable → 403 (spec 01 §5). `POST …/migrate` **recomputes the diff server-side** and validates the decisions against it, so the
preview is advisory and a stale tab cannot smuggle a decision past the current state: a key that is not a decidable item → 400
`unknown_decision`; a `splitCopies` target outside that item's `splitInto`, or an `orphanReassign` target hidden, absent or already
answered in `W` → 400 `invalid_decision`; missing decisions take the §4.2 defaults (split → both, removed → orphan). Effects, one
transaction: `questionnaire_version = W`, `answers` rewritten in target order, `orphaned_answers` extended, `migrated_from =
{"id": X, "version": V, "at": <now>}`, `updated_at` refreshed. Target equal to the current version → 409 `already_on_version`.

### 4.4 `orphanedAnswers` storage

```json
[{"questionId": "A2", "questionText": {"en": "…"}, "declarations": [ …spec 01 §2.2… ], "comment": "…",
  "fromVersion": "1.0.0", "at": "2026-11-02T10:00:00Z"}]
```
Append-only, never re-injected into `answers`: re-assignment happens at migrate time via `orphanReassign`, after which the entry
stays as the record of where the answer came from. The migrate page shows the list read-only.

## 5. Frontend

- `MigrationBanner.vue` on `FipEditor.vue` and `FipRead.vue`, only for a caller who may write and only when `migration-targets` is
  non-empty: "A newer version of this questionnaire is available (1.1.0)." + `Review changes` → `/fips/:id/migrate`; on a pinned
  session FIP it renders the pinned explanation and no button.
- Route `/fips/:id/migrate` → `FipMigrate.vue` (`requiresAuth: false`; write rights checked in the view, like `FipEditor`): a
  target select when several, then a diff table **old question | new question | status badge | decision control**, ordered
  `split`/`removed` first, then `added`, flagged rows, then `unchanged`/`hidden` behind a "show unchanged (18)" toggle. Split →
  radios (both / metadata / data / none); removed → a select of `options` plus "keep as orphaned answer". A summary line ("17
  answers kept, 1 orphaned, 2 decisions"), a `Migrate` button that is never blocked (defaults are valid, just shown explicitly),
  and a confirm dialog naming the target version and saying migration cannot be undone. One column at 375 px (the table collapses
  to stacked cards), reusing `StatusBadge.vue`.
- `api/fips.ts`: `getMigrationTargets(id)`, `getMigrationPreview(id, to)`, `migrateFip(id, body)`. No new store — the view holds
  the preview and the decision map; `lib/migration.ts` holds the pure diff + apply functions (vitest), tested against the same
  fixtures as the backend.
- New i18n block `migration:` (`bannerTitle`, `bannerBody "A newer version of this questionnaire is available ({version})."`,
  `review`, `pinned`, `targetLabel`, `statusUnchanged|Added|Removed|Hidden|Split`, `flagTextChanged`, `flagFerTypeChanged`,
  `splitBoth|Metadata|Data|None`, `reassign`, `keepOrphaned`, `summary`, `migrate`, `confirmTitle`, `confirmBody`, `done`,
  `alreadyOnVersion`, `showUnchanged`, `orphanedTitle`, `orphanedHint`) plus `auth:` additions (`verifyTitle|verifySent|verifyOk|
  verifyExpired|verifyInvalid|resend|verifyBanner`, `forgotTitle|forgotSent|forgotSubmit`, `resetTitle|resetSubmit|resetOk|
  resetExpired`). English here; `pt-PT`/`pt-BR`/`es` go to the translator agent.

## 6. Exports

- **JSON** (`exportVersion: 2`; readers of 1 are unaffected, and `POST /api/fips/import` accepts 1 and 2): `fip.migratedFrom`
  (object or null) and a top-level `orphanedAnswers` array whose declarations are FER-enriched exactly like `answers`. Import
  preserves both.
- **CSV** is unchanged — the 21 columns of spec 01 §3.2, only the current questionnaire's questions; orphaned answers are
  deliberately not rows, having no `question_id` in the model the file conforms to.
- **RDF**, minimal and honest: the FIP node keeps `dcterms:conformsTo <…/knowledge-models/X/W>` and gains
  `fipmx:migrated-from <…/knowledge-models/X/V>` (one term added to the spec 03 §2.1 `fipmx:` list). Orphaned answers become
  **Turtle comment lines** in the prepended header block (`# orphaned answer A2: <DOI> (current)`), not triples, so they appear in
  neither the graph nor the JSON-LD. `prov:wasRevisionOf` between FIP *states* is rejected: a FIP has one IRI and no per-state IRI
  exists, so the triple would assert a revision relation between a resource and itself.

## 7. Acceptance criteria — mail flows (pytest unless marked)

1. Register with `FIPM_MAIL_BACKEND=console`: 201, `emailVerifiedAt` null, exactly one INFO record on `fipm.mail` containing
   `{FIPM_BASE_URL}/verify?token=`, and `hash_token(token) == email_tokens.id` (64 hex) while no column holds the plaintext.
2. `POST /api/auth/verify-email` with that token → 200 and `emailVerifiedAt` set; the same token again → 400 `invalid_token`; a
   token whose `expires_at` is moved into the past → 410 `token_expired`; a random token → 400 `invalid_token`.
3. With `FIPM_REQUIRE_EMAIL_VERIFICATION=true`, an unverified user gets 403 `email_verification_required` from `POST /api/fips`
   with `visibility="public"` and from a `PATCH` to `public`, but 201/200 for `private`/`link` and may create and answer a session;
   after verification the public write succeeds. With the flag `false` nothing is blocked and no spec 01/02/04 test changes.
4. `POST /api/auth/verify-email/resend` → 202 for an unverified user, 202 with **no** mail for a verified one, 429 with
   `Retry-After` on the 4th call within an hour.
5. `POST /api/auth/password-reset/request` → 202 for a known address (one mail logged, link contains `/reset-password?token=`) and
   202 with no mail and no `email_tokens` row for an unknown or malformed one; bodies and codes are byte-identical across the
   three, and the 4th call for one address is still 202 with no mail.
6. `POST /api/auth/password-reset/confirm` with a valid token and a 12-char password → 204; the old password then fails login
   (401) and the new one succeeds; **every** pre-existing `auth_sessions` row is gone (a cookie captured before the reset returns
   401 on `GET /api/auth/me`); `email_verified_at` is set although no verify link was clicked.
7. Reset token: replay → 400 `invalid_token` with the password unchanged; past its 1 h TTL → 410 `token_expired`; issuing a second
   reset token deletes the first unused one (row count 1).
8. `render_mail` renders both templates in all four languages with no `KeyError` and a non-empty subject each; a `pt-PT` user with
   only `pt-BR` present gets the `pt-BR` file; a missing language file fails the suite (all four directories exist).
9. `FIPM_MAIL_BACKEND=smtp` with no `FIPM_SMTP_HOST` refuses to start; against a stub server one `sendmail` call carries the
   `FIPM_MAIL_FROM` sender, the recipient and a `text/plain; charset=utf-8` part; an SMTP exception is logged, the response stays
   201/202.
10. *(vitest)* `ForgotPassword.vue` renders the same panel for any submitted address; `ResetPassword.vue` disables Submit until
    both fields match at ≥10 chars and renders `auth.resetExpired` with a `/forgot-password` link on 410; `Workspace.vue` shows
    the verify banner only when `verificationRequired && !emailVerifiedAt`.

## 8. Acceptance criteria — migration

11. Fork `gofair-fip-mini`, publish 1.0.0, create a FIP with answers on three questions, then `new-version` → 1.1.0 with one `en`
    text edited, one question added, one deleted, one hidden and one answered question split; publish 1.1.0.
    `GET …/migration-targets` lists exactly `1.1.0` with its changelog entry, and returned `[]` before 1.1.0 was published.
12. `GET …/migration-preview?to=1.1.0` returns `diffVersion: 1` with AC 11's statuses assigned correctly, the edited question
    `unchanged` with `flags: ["text-changed"]`, `counts.decisionsRequired == 2`, and `orphanReassign.options` holding only
    unanswered non-hidden target ids.
13. `POST …/migrate` with no `decisions` applies the defaults: the split answer lands under **both** new ids, the deleted
    question's answer is in `orphanedAnswers` with `fromVersion "1.0.0"`, `questionnaireRef.version == "1.1.0"`, `migratedFrom ==
    {"id": …, "version": "1.0.0", "at": …}`, and the hidden question's answer is still in `answers`.
14. `splitCopies {"F2": ["F2-metadata"]}` puts the answer on `F2-metadata` only and not in `orphanedAnswers`; an empty list orphans
    it; `orphanReassign {"A2": "A2-data"}` places the declarations on `A2-data` and still records the `orphanedAnswers` entry.
15. Rejections: current version → 409 `already_on_version`; a draft or lower version → 400 `version_not_greater`; another model id
    → 404 `target_not_found`; a decision key on an `unchanged` question → 400 `unknown_decision`; an `orphanReassign` target that
    is hidden or already answered → 400 `invalid_decision`. In every rejected case the FIP row is unchanged (same `updated_at`).
16. A FIP with `session_id` set → 409 `session_version_pinned` on migrate while `migration-targets`/`migration-preview` still
    return 200; after `POST /api/fips/{id}/claim` it keeps `session_id` and stays pinned — the pin is the session's, not the owner's.
17. Authorization: a second signed-in user gets 404 on all three endpoints for a private FIP and 403 for a `link` FIP; an
    anonymous caller with the right `X-Edit-Token` on a session-less anonymous FIP may migrate, as may the owner and an admin.
18. After migration `export.json` has `exportVersion 2`, `fip.migratedFrom`, `orphanedAnswers` with enriched FER labels and no
    `answers` entry for the hidden or removed question; re-importing that document yields a FIP whose `answers`, `orphanedAnswers`,
    `migratedFrom` and `questionnaireRef` equal the original's; `export.csv` still has exactly the 21 columns.
19. `export.ttl` contains `dcterms:conformsTo <…/gofair-fip-mini/1.1.0>`, `fipmx:migrated-from <…/gofair-fip-mini/1.0.0>`, one
    `# orphaned answer` comment line and **no** `prov:wasRevisionOf`; the JSON-LD carries no orphaned-answer node.
20. *(vitest)* `lib/migration.ts` computes the same statuses, flags and counts as the backend on a shared fixture pair (under
    `frontend/src/lib/__fixtures__/`), never mutates its inputs, and yields an all-`unchanged` diff for identical documents.
    `FipMigrate.vue` with a stubbed preview renders one row per item, unchanged rows behind the toggle, split radios defaulting to
    both, and a confirm dialog naming the target version.


## 9. Assumptions (facilitators away; both features are post-workshop)

- **A1. Nothing here runs during CONFOA:** `console` mail and `FIPM_REQUIRE_EMAIL_VERIFICATION=false` are the defaults and no
  newer `gofair-fip-mini` version will be published before 6 Oct, so the banner cannot appear in the room.
- **A2. Verification gates only public listing**, never sign-in — an unverified account is a fully working private workspace, so a
  mistyped address cannot destroy someone's output. **A3.** A reset logs out every device, including the one doing it.
- **A4. Mail is best-effort:** a failed send never fails the request and is visible only in the log; spec 05's admin
  temporary-password path stays the guaranteed route back into an account.
- **A5. Migration is forward-only and not undoable:** no "migrate back", no stored diff, and `migrated_from` keeps only the last
  hop (1.0.0 → 1.1.0 → 1.2.0 records 1.1.0); exports made before a migration remain the historical record.
- **A6. One FIP at a time** — no bulk or session-wide migration in v2. **A7. `en` is the diff language**, so a translation-only
  `pt-BR` change raises no flag and needs no review: the answer stays valid.

## 10. Open questions

1. Migration across forks (a FIP on `gofair-fip-mini` 1.0.0 → a facilitator's `confoa-fip` 1.0.0): same diff machinery, but needs
   a policy on which forks are offered (lineage via `content.forkedFrom`?) and on attribution when the licences differ.
2. A facilitator-level "migrate this whole session to version W" (the pin's escape hatch): one endpoint, one confirm, N diffs —
   worth it only if a session outlives its model version, which the workshop will tell us.
3. Should `required`, `allowMultiple` or `principle` changes appear as diff flags? They change no stored answer, so v2 ignores them.
4. Should an orphaned answer be re-assignable **after** migration (a small editor on `FipRead`/`FipEditor`), or only during
   migration as specified?
5. The From address and DKIM/SPF depend on the hosting decision (PLAN §9.3); until it lands `smtp` is tested against a local relay
   only, and a bounced mail is invisible to the tool (no bounce handling in v2).
