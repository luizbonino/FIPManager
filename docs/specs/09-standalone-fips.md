# Spec 09 – Standalone FIPs

Status: implemented, 2026-09-09. Author: builder.

## 0. Goal

Anyone can fill in a FIP independently — no workshop session, no account. `POST /api/fips` already had
two paths (session participant, signed-in user); the third path, an anonymous caller with neither, used to
400 `session_id_or_login_required`. It now creates an ownerless, sessionless FIP with a fresh edit token,
exactly the way a session participant's anonymous FIP already worked, minus the session.

## 1. API behaviour

`POST /api/fips` with no `sessionId` and no signed-in cookie:

- `visibility` defaults to `"link"` when omitted, same default as the session path.
- `visibility: "private"` → **400 `private_requires_account`**, on both `POST` and `PATCH` (the same rule
  applies to a session FIP's `PATCH`, for the same reason — see below). A private FIP is
  owner/admin-only-readable (`authz.can_read`); the edit-token holder is *not* locked out by this —
  `_get_readable_fip`/`_authorize_fip_write` check the token after `can_read` regardless of visibility, so a
  private ownerless FIP would still be readable/writable by whoever holds the token. The actual reason for
  the rejection: with no owner, the FIP becomes unreadable by *anyone else* — no facilitator, no admin
  listing, nothing — and unrecoverable dead data the moment the token is lost, since `private` also blocks
  the one recovery path (an admin or the session owner reading it to help). Rejected outright, not silently
  downgraded to `link`, so the caller's explicit choice is never silently overridden.
- Otherwise: a FIP row with `owner_id = NULL`, `session_id = NULL`, a fresh edit token (only its hash is
  stored; the plaintext is returned once as `editToken`, never again — same contract as every other
  edit-token FIP).
- `check_email_verification_gate` does not run: it gates a *signed-in* user's write to `visibility="public"`,
  and there is no user here.
- Subject to `FIPM_ANONYMOUS_FIPS` (§3) and a per-IP rate limit (§4).

Every other endpoint already authorizes off `owner_id`/`session_id`/the edit token rather than assuming a
session exists, so a standalone FIP (`owner_id IS NULL AND session_id IS NULL`) needed no further code
changes once creation was in place (see §5 for what was checked).

## 2. Authorization table

| FIP kind | `owner_id` | `session_id` | Read | Write |
|---|---|---|---|---|
| Owned | set | usually NULL | owner, admin, or `visibility` public/link | owner, admin, or the owning session's facilitator if claimed out of one |
| Session (anonymous) | NULL | set | session facilitator/admin, or `visibility` public/link, or `X-Edit-Token` | session facilitator/admin, or `X-Edit-Token` (frozen once the session closes, unless facilitator/admin) |
| **Standalone (new)** | NULL | NULL | `visibility` public/link (never `private`), or `X-Edit-Token` | **admin (no token needed — `_authorize_fip_write`'s ownerless branch returns early for `user.role == "admin"`), or `X-Edit-Token`** — no facilitator, and never frozen by a session close since there is none |

Claiming (`POST /fips/{id}/claim`, token holder must be signed in) turns a standalone FIP into an owned one
exactly like it already did for a session FIP: `owner_id` set, `edit_token_hash` cleared, `session_id` stays
NULL throughout. This is the durable path — see §6.

## 3. Config

`FIPM_ANONYMOUS_FIPS` (`Settings.anonymous_fips`, default `true`). When `false`, the anonymous-standalone
branch returns **403 `anonymous_fips_disabled`**; session participants (who present a `joinCode`) and
signed-in users are unaffected either way. Documented in `.env.example` next to `FIPM_REGISTRATION_OPEN`.

## 4. Rate limit

`fipm.auth.check_anonymous_fip_rate_limit`: 30 standalone creations per hour per client IP (proxy-aware via
`client_ip`, same `FIPM_TRUST_PROXY` opt-in as every other limiter) → **429 `rate_limited`** with
`Retry-After`. Only this branch is limited — a session participant creating many FIPs in one room, or a
signed-in user, never hits it. Shares the process-wide `RateLimiter` in `fipm.auth`; `reset_rate_limits()`
clears its bucket along with every other limiter's (it clears the whole underlying dict, not per-limiter).

## 5. Lifecycle check (spec brief §4)

Read, not guessed, across `authz.py`, `routers/fips.py`, `routers/admin.py`, `exporters.py`, `rdf.py`,
`migration.py`, `routers/embed.py`, `routers/me.py`, `routers/auth.py`'s account deletion:

| Path | Outcome |
|---|---|
| `_authorize_fip_write` | Already correct: the ownerless branch (covers both standalone and session-anonymous FIPs) grants an admin write access with no token at all before it ever reaches `check_edit_token` (`if user is not None and user.role == "admin": return`, `routers/fips.py` ~161-162); a non-admin caller falls through to `check_edit_token`. The session-closed freeze is behind `if fip.session_id is not None`, so it never applies to a standalone FIP. No change needed for standalone FIPs specifically — this admin exemption already existed for every ownerless FIP. |
| Claim | Already correct: `if fip.session_id is not None` guards the closed-session check; nothing else assumes a session. No change. |
| `GET`/exports (JSON/CSV/TTL/JSON-LD) | `_get_readable_fip` and `exporters.build_export_json`/`fip_graph` never touch `session_id`. No change. |
| Embed | Reuses `_get_readable_fip`. No change. |
| Migration endpoints | `_get_fip_for_migration` reuses `_authorize_fip_write`; `migrate_fip`'s session-pin check is behind `if fip.session_id is not None`. No change. |
| Admin listing | `routers/admin.py` has no FIP-listing endpoint at all — only aggregate counts by `owner_id`. Nothing to filter. No change. |
| `GET /me/fips` | Filters by `Fip.owner_id == user.id`; a standalone FIP is invisible until claimed, which is the intended "not listed anywhere" behaviour (§6). No change. |
| Account deletion (`DELETE /auth/me`) | Filters by `Fip.owner_id == user.id` regardless of `session_id`; a claimed-then-deleted standalone FIP (`session_id` NULL, `visibility` non-private) is anonymised (`owner_id = NULL`) and — since claiming already cleared `edit_token_hash` — becomes permanently read-only, matching how an owned-with-no-session FIP already behaved. No change. |

No code changes were needed in this area beyond FIP creation itself: the existing write/read/claim/export
paths were already written against `owner_id`/`session_id` independently rather than assuming one implies
the other.

## 6. Tests

`backend/tests/test_standalone_fips.py` (13 tests): anonymous creation (201, `editToken`, `ownerId`/
`sessionId` null, `visibility: "link"`); `visibility: "public"` allowed; `visibility: "private"` → 400;
PATCH with/without/wrong `X-Edit-Token`; anonymous GET; claim by a signed-in token holder then the stale
token 403s while the new owner's cookie works; JSON/CSV/TTL exports; `FIPM_ANONYMOUS_FIPS=false` → 403
(env + `get_settings.cache_clear()`, the existing pattern from `test_ac_07_3_verification_gate.py`); rate
limit exceeded → 429 with `Retry-After` (module-level constant monkeypatched to 2 so the test stays fast);
a session join and a signed-in creation both still succeed once that same (monkeypatched-small) anonymous
cap is exhausted; `DELETE` requires the edit token (403 without/wrong, 204 with); `PATCH
visibility: "private"` → 400 `private_requires_account` for both a standalone FIP and a session-anonymous
one (review fix: the rule now applies identically to `POST` and `PATCH`).

Review-fix additions: `backend/tests/test_admin_fip_stats.py` (2 tests) — `GET /api/admin/stats` 404s for
anonymous/non-admin, 200s for an admin with `ownedFips`/`standaloneFips`/`sessionFips` counts that move by
exactly one each when one of each kind is created. `backend/tests/test_cli_purge_standalone_fips.py`
(4 tests) — `purge-standalone-fips --dry-run` counts an aged (`updated_at` pushed back 400 days) standalone
FIP without deleting it, a real run deletes it, a recently-edited standalone FIP is left alone, and an aged
owned FIP / aged session-anonymous FIP are both left alone regardless of age.

`cd backend && uv run pytest -q`: 464 → 473 (spec 09 v1) → 483 passed (review-fix round: +4 in
`test_standalone_fips.py`, +2 in `test_admin_fip_stats.py`, +4 in `test_cli_purge_standalone_fips.py`).
`uv run ruff check .` / `uv run ruff format --check .`: clean.

## 7. Decisions

- Standalone FIPs default to `visibility: "link"` and are **not listed anywhere** — not in `GET /me/fips`
  (no owner), not in any admin listing (none exists), nowhere. The only path back to a standalone FIP is
  the edit link (`/fips/{id}` plus the `editToken`) kept in the creator's browser or shared by them.
- Claiming into an account is the durable path: the moment it matters enough to not lose, sign in and
  claim it. This mirrors how a session FIP already worked — the edit token was always the sole bearer
  credential until claimed.
- `private` is rejected outright rather than silently downgraded to `link`, so the caller's explicit choice
  is never silently overridden — they get a 400 telling them why, matching this codebase's general
  preference (see `check_email_verification_gate`) for an explicit error over a silent substitution.

## 8. Frontend

An edit token today lives only in `localStorage` (`frontend/src/lib/editTokens.ts`, keyed
`fipm.editToken.<fipId>`), so a standalone FIP's creator has no way to move it to another device or hand it
to a colleague other than by sharing the token itself. The frontend now offers an **edit link**:
`/fips/{id}/edit?token=<editToken>`. On load, `FipEditor.vue`'s `init()` calls
`adoptTokenFromQuery(id, route.query)`, which stores `?token=...` via the same `setToken()` that
`FipNew.vue`/`JoinSession.vue` already call right after creation, then returns it so the caller
(`FipEditor.vue`) immediately strips `token` from the URL with `router.replace` — the plaintext never
lingers in the address bar, browser history, or anywhere it could be logged or accidentally re-shared once
adopted. No backend change: this is purely a client-side convenience wrapper around the existing
`GET`/`PATCH` `X-Edit-Token` contract.

## 9. Retention runbook

The privacy notice promises a standalone FIP (`owner_id IS NULL AND session_id IS NULL` — never a session
FIP, which stays reachable through its session's room/facilitator) is deleted 12 months after its last
edit. No scheduler ships with v1 (spec brief: anything not needed for the CONFOA workshop is v2) — an
operator runs this by hand, monthly:

```sh
uv run python -m fipm purge-standalone-fips --older-than-days 365 --dry-run   # count only, deletes nothing
uv run python -m fipm purge-standalone-fips --older-than-days 365             # actually deletes
```

Inside the shipped container (see `Dockerfile`'s `CMD`, which already runs `python -m fipm import-data` on
boot the same way) the `uv run` prefix is dropped: `python -m fipm purge-standalone-fips [...]`, e.g. via
`docker compose exec <service> python -m fipm purge-standalone-fips --older-than-days 365`.

`--older-than-days` defaults to 365 (the promised 12 months); `--dry-run` prints the count that would be
deleted without deleting anything, for a before/after sanity check. Matches are on `Fip.updated_at`, the
column already bumped by every `PATCH` (`onupdate=_now`, `fipm/models.py`) — "last edit", not "creation".

Deletion is a plain row delete, the same one `DELETE /api/fips/{id}` (`routers/fips.py::delete_fip`)
already does: no bespoke cleanup helper exists or is needed, because the only foreign key referencing
`fips.id` is `Feedback.fip_id`, declared `ondelete="SET NULL"` (`fipm/models.py`) and enforced by SQLite
itself (`PRAGMA foreign_keys=ON`, `fipm/db.py`) — previously collected feedback survives with `fip_id`
cleared to `NULL`, never cascaded away. `GET /api/admin/stats` (`AdminFipStatsOut`) reports
`standaloneFips`/`sessionFips`/`ownedFips` counts so an admin can see the purge candidate volume before
running the command.
