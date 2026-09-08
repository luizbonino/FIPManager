# Spec 01 – Foundations: repo scaffold, data model, auth, API

Status: approved for implementation, 2026-09-08. Covers ROADMAP week 1 + the API side of week 2.
Authority: PLAN.md §4 (data model), §5 (v1 scope), §7 (architecture), §9 (open decisions).
Companion spec: `docs/specs/00-fip-ontology-mapping.md` (declaration-status enum; written in parallel).

## 1. Repository layout

```
backend/
  pyproject.toml            # uv-managed, requires-python = ">=3.12,<3.13"
  fipm/
    __init__.py  __main__.py        # `python -m fipm <cmd>` -> cli.main()
    config.py     # Settings (pydantic-settings), env prefix FIPM_
    db.py         # engine, SessionLocal, Base, init_db(), get_db() dependency
    models.py     # SQLAlchemy 2.x DeclarativeBase models (§2)
    schemas.py    # Pydantic v2 request/response models
    ids.py        # short_id(), join_code(), new_token(), hash_token()
    auth.py       # argon2id hashing, login/logout, cookie session, CSRF, rate limiter
    authz.py      # require_user/require_admin, can_read/can_write, edit-token checks
    importer.py   # load data/ into the DB idempotently
    exporters.py  # FIP -> export JSON, FIP -> CSV
    cli.py        # import-data, create-admin
    routers/__init__.py health.py auth.py me.py knowledge_models.py fers.py fips.py sessions.py
    main.py       # FastAPI app, router mounting, SPA static mount
  tests/          # pytest; conftest.py builds an in-memory/temp-file SQLite app+client
frontend/         # Vue 3 + Vite + TypeScript + vue-i18n, `npm run build` -> frontend/dist
data/
  knowledge-models/gofair-fip-mini-1.0.0.json
  fers/seed.json
  i18n/{en,pt-PT,pt-BR}.json          # UI strings; frontend imports these at build time
Dockerfile  docker-compose.yml  .github/workflows/ci.yml  README.md  .gitignore  LICENSE (MIT)
docs/  scripts/  .claude/
```

- Python deps (`backend/pyproject.toml`): fastapi, uvicorn[standard], sqlalchemy>=2.0, pydantic>=2, pydantic-settings, argon2-cffi, python-multipart, rdflib (week 3, add now), qrcode[pil] (week 2). Dev: pytest, pytest-cov, httpx, ruff. Lock with `uv lock`; run with `uv run`.
- Ruff config in pyproject: `line-length = 100`, rules `E,F,I,UP,B`.
- **No Alembic in v1.** `db.init_db()` calls `Base.metadata.create_all()` and then upserts `schema_version`. If the stored version is lower than `fipm.db.SCHEMA_VERSION`, log a warning and continue (v1 makes only additive changes); if higher, refuse to start.
- Dockerfile: stage 1 `node:20-alpine` builds `frontend/`; stage 2 `python:3.12-slim`, `uv sync --frozen`, copies `frontend/dist` to `/app/static`. Entrypoint: `python -m fipm import-data && uvicorn fipm.main:app --host 0.0.0.0 --port 8000`.
- docker-compose: one service `fipm`, port 8000, volume `fipm-data:/data`, env `FIPM_DB_PATH=/data/fipm.db`, healthcheck on `/api/health`.
- `main.py` serves the SPA: `/api/*` routers first, then `StaticFiles(directory=settings.static_dir)` at `/assets`, and a catch-all `GET /{path:path}` returning `index.html` (SPA history fallback) for any non-`/api` path. Missing `static_dir` (dev) must not crash startup.
- CI (`.github/workflows/ci.yml`), one workflow, three jobs on push + PR: `backend` (`uv sync`, `ruff check`, `ruff format --check`, `pytest -q`), `frontend` (`npm ci`, `npm run type-check`, `npm run build`), `docker` (`docker build .`).

## 2. Data model (SQLAlchemy tables)

All timestamps are `DateTime(timezone=True)`, UTC, server-side default via Python `datetime.now(UTC)`.
JSON columns use `sqlalchemy.JSON`. A `LangMap` is a JSON object `{"en": "...", "pt-PT": "...", "pt-BR": "..."}`.

| Table | Columns | Keys / indices |
|---|---|---|
| `users` | `id` str(26) pk, `email` str unique (stored lowercased), `password_hash` str, `display_name` str, `role` str `user\|admin`, `language` str default `en`, `created_at`, `updated_at` | unique index `ix_users_email` |
| `auth_sessions` | `id` str(64) pk = sha256 hex of the cookie token, `user_id` fk users.id ON DELETE CASCADE, `created_at`, `expires_at`, `last_seen_at` | index on `user_id`, index on `expires_at` |
| `knowledge_models` | `id` str pk-part, `version` str pk-part (semver), `owner_id` fk users.id nullable, `visibility` str, `status` str `draft\|published`, `license` str, `source` str, `title` JSON LangMap, `description` JSON LangMap, `changelog` JSON, `content` JSON (the whole file document, §3), `content_sha256` str, `created_at`, `updated_at` | composite pk `(id, version)`; index `(owner_id, status)`; index `(status, visibility)` |
| `fips` | `id` str pk (short id, §2.1), `owner_id` fk nullable, `session_id` fk workshop_sessions.id nullable, `edit_token_hash` str(64) nullable, `visibility` str, `questionnaire_id` str, `questionnaire_version` str, `title` str nullable, `community` JSON, `related_dmps` JSON list, `answers` JSON list, `language` str, `license` str default `CC0-1.0`, `created_at`, `updated_at` | index `(owner_id, updated_at)`; index `(session_id, created_at)`; FK `(questionnaire_id, questionnaire_version)` -> knowledge_models |
| `fers` | `id` str pk (IRI), `label` JSON LangMap, `label_search` str (lowercased, all labels joined by `\|`), `type` str, `homepage` str nullable, `owner_id` fk nullable, `source` str `seed\|user\|nanopub`, `created_at` | index `(type, label_search)`; index `owner_id` |
| `workshop_sessions` | `id` str pk (short id), `join_code` str(6) unique, `owner_id` fk users.id NOT NULL, `questionnaire_id`, `questionnaire_version`, `default_language` str, `title` str, `status` str `open\|closed`, `created_at`, `updated_at` | unique index `ix_sessions_join_code`; index `(owner_id, created_at)` |
| `schema_version` | `id` int pk (always 1), `version` int, `applied_at` | – |

`SCHEMA_VERSION = 1`. Python enums (`Role`, `Visibility`, `KMStatus`, `SessionStatus`, `FerSource`) are `str, Enum` used in Pydantic schemas; **stored as plain `String` columns**, never native DB enums.

**Declaration status is a plain `String` inside the `answers` JSON.** The allowed values come from `docs/specs/00-fip-ontology-mapping.md`; until that lands, the API validates against `fipm.config.DECLARATION_STATUSES` (single module-level tuple, initial value `("current", "planned", "considered", "none")`) so finalising the enum is a one-line change plus one test fixture.

### 2.1 Identifier schemes (`ids.py`)

- `short_id()` -> `settings.id_prefix + code`, where `code` is 8 chars of Crockford base32 (`0123456789ABCDEFGHJKMNPQRSTVWXYZ`, no I/L/O/U) drawn from `secrets.randbits(40)`. Default `FIPM_ID_PREFIX=""`; e.g. `FIPM_ID_PREFIX="fip-"` yields `fip-7Q2M8XKD`. Collisions: retry the insert up to 5 times on `IntegrityError`.
- `join_code()` -> 6 chars of the same alphabet (uppercase, human-dictatable).
- `new_token()` -> `secrets.token_urlsafe(32)`; `hash_token(t)` -> `hashlib.sha256(t.encode()).hexdigest()`. Used for both edit tokens and auth-session cookies (high-entropy secrets need no KDF). Compare with `secrets.compare_digest` on the hashes.
- User ids: `secrets.token_hex(13)` (26 chars). FER ids are the IRIs themselves.

### 2.2 `answers` JSON shape (stored on the FIP)

```json
[{"questionId": "F1-metadata",
  "declarations": [{"ferId": "https://w3id.org/np/doi", "ferFreeText": null,
                    "status": "current", "note": {"en": "..."},
                    "dmpEvidence": {"url": "...", "questionRef": "C.3"}}],
  "comment": "free text"}]
```
`ferId` xor `ferFreeText` must be set (validator). `ferId` need not resolve to a row in `fers` (free IRIs are allowed); when it does, exports enrich it. `community` shape: `{"name", "description", "links": [], "domain", "dataSteward": {"orcid", "name"}}`. `relatedDMPs`: `[{"url", "version", "system": "FioDMP"}]`.

## 3. Content file shapes (`data/`)

**Knowledge model** — fixed, do not change (the GO FAIR file is being produced against it):

```json
{"id": "gofair-fip-mini", "version": "1.0.0", "status": "published",
 "license": "CC-BY-4.0", "source": "GO FAIR FIP mini-questionnaire",
 "title": {"en": "..."}, "description": {"en": "..."},
 "changelog": [{"version": "1.0.0", "date": "2026-09-08", "notes": "..."}],
 "sections": [{"id": "findable", "title": {"en": "..."},
   "questions": [{"id": "F1-metadata", "principle": "F1", "scope": "metadata",
     "text": {"en": "..."}, "help": {"en": "..."}, "ferType": "identifier-service",
     "required": true, "allowMultiple": true}]}]}
```
`scope` ∈ `metadata | data | null`. `principle`, `ferType`, `help` may be `null` (from-scratch models). Filename convention `<id>-<version>.json`.

**FER seed** (`data/fers/seed.json`): `[{"id": "<IRI>", "label": {"en": "DOI"}, "type": "identifier-service", "homepage": "https://...", "source": "seed"}]`.

### 3.1 FIP export JSON (self-describing)

`GET /api/fips/{id}/export.json` — question texts resolved in the FIP's language with fallback `pt-PT ⇄ pt-BR → en`:

```json
{"exportVersion": 1, "generatedAt": "2026-10-06T09:00:00Z",
 "tool": {"name": "FIP Manager", "baseUrl": "https://..."},
 "fip": {"id": "7Q2M8XKD", "url": "<baseUrl>/fips/7Q2M8XKD", "language": "pt-BR",
         "license": "CC0-1.0", "visibility": "link", "createdAt": "...", "updatedAt": "...",
         "community": {...}, "relatedDMPs": [...]},
 "questionnaireRef": {"id": "gofair-fip-mini", "version": "1.0.0",
                      "title": "…resolved…", "source": "…"},
 "answers": [{"sectionId": "findable", "sectionTitle": "…resolved…",
   "questionId": "F1-metadata", "questionText": "…resolved…", "principle": "F1",
   "scope": "metadata", "ferType": "identifier-service",
   "declarations": [{"fer": {"id": "...", "label": "DOI", "type": "...", "homepage": "..."},
                     "ferFreeText": null, "status": "current", "note": "…resolved…",
                     "dmpEvidence": null}],
   "comment": null}]}
```
Answers are emitted in questionnaire order; unanswered questions are included with `declarations: []`. Round trip: `POST /api/fips/import` accepts this document verbatim and recreates an equal FIP (new id, `answers`, `community`, `relatedDMPs`, `language`, `license`, `questionnaireRef` preserved; the referenced knowledge-model version must exist).

### 3.2 FIP export CSV

`GET /api/fips/{id}/export.csv` — UTF-8 with BOM, `\r\n`, one row per declaration (a question with no declarations still gets one row with empty declaration fields). Header, in order:

`fip_id, fip_url, language, license, questionnaire_id, questionnaire_version, community_name, section_id, section_title, question_id, question_text, principle, scope, fer_type, declaration_index, fer_id, fer_label, fer_free_text, status, note, comment`

Session-wide export (week 3) reuses the same columns and prepends `session_id, fip_title`.

### 3.3 `python -m fipm import-data`

Idempotent; also run by the container entrypoint before uvicorn. Steps:
1. `init_db()`.
2. Bootstrap admin from `FIPM_ADMIN_EMAIL` / `FIPM_ADMIN_PASSWORD` if both set: create with `role=admin` if the email is absent; if present, ensure `role=admin` and **never** overwrite the password.
3. Knowledge models: for every `data/knowledge-models/*.json`, validate against §3, then upsert by `(id, version)` with `owner_id=NULL`, `visibility="public"`. If a row exists with the same `content_sha256`, skip. If the hash differs: skip with a warning unless `--force`, then overwrite.
4. FERs: upsert by `id` for rows with `source="seed"` (label/type/homepage refreshed). Never touch rows with `source="user"`.
5. Print a summary line per category (`created/updated/skipped`) and exit 0. Re-running changes nothing and reports all-skipped.
`cli.py` also provides `create-admin --email --password`.

## 4. Authentication (`auth.py`)

- Registration: `POST /api/auth/register` with email, password (≥10 chars, ≤128), display name, optional language. argon2id via `argon2.PasswordHasher()` defaults (`time_cost=3, memory_cost=65536, parallelism=4`). Email normalised to lowercase; duplicate returns `409`.
- **Decision (PLAN §9 item 5): open registration with a rate limit.** Gate it behind `FIPM_REGISTRATION_OPEN` (default `true`) so invite-only is a config flip, not a code change.
- Login creates an `auth_sessions` row (`expires_at = now + FIPM_SESSION_TTL_DAYS`, default 14) and sets cookie `fipm_session` = plaintext token: `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` from `FIPM_COOKIE_SECURE` (default `true`; compose sets `false` for plain-HTTP laptop use), `Max-Age` = TTL. Logout deletes the row and clears the cookie. On each authenticated request, refresh `last_seen_at` at most once per 5 minutes; expired rows are rejected and deleted lazily.
- Password rehash: if `ph.check_needs_rehash`, update the stored hash on successful login. `POST /api/auth/password` requires the current password and revokes all other sessions of that user.
- **CSRF:** a middleware rejects `POST/PUT/PATCH/DELETE` on `/api/*` with `403 {"detail":"csrf_failed"}` unless the `Origin` header (or, if absent, `Referer`) has a scheme+host+port matching `FIPM_BASE_URL` or an entry of `FIPM_ALLOWED_ORIGINS`. If both headers are absent the request is rejected. Exempt: nothing (the SPA is same-origin and always sends `Origin`).
- **Rate limiter:** in-process, `dict[key, deque[timestamp]]`, monotonic clock, pruned on access. Limits: failed login 10 per 15 min per `(email, client_ip)` and 30 per 15 min per ip; register 5 per hour per ip. Over limit -> `429` with `Retry-After`. Single-process deployment is assumed; documented as such in the README.
- Login failures return an indistinguishable `401 {"detail":"invalid_credentials"}` for unknown email and wrong password.
- Timing: always run `ph.verify` against a dummy hash when the user is absent.

## 5. Authorization (`authz.py`)

Principals: `anonymous`, `user`, `admin`, plus two capability tokens — a session join code and a per-FIP edit token.

- `require_user()` / `require_admin()` FastAPI dependencies read the cookie; failure -> `401` (`403` for the admin check).
- Read: owner or admin always; `visibility="public"` and `"link"` readable by anyone who has the URL; `"private"` returns **`404`** (not `403`) to non-owners so ids do not leak. Public listings only ever include `visibility="public"` plus the caller's own rows.
- Write on an owned object: owner or admin only, else `404`/`403` per the read rule above.
- Anonymous FIP in a session: `edit_token_hash` set, `owner_id` NULL. Writes require header `X-Edit-Token`; missing or wrong -> `403 {"detail":"edit_token_required"}`. The plaintext token is returned **once**, in the `POST /api/fips` response body as `editToken`, and never again by any endpoint.
- Creating a FIP inside a session requires the correct `joinCode` in the request body and `session.status == "open"`; a closed session -> `409 {"detail":"session_closed"}`, a wrong code -> `403`. Session owner may write any FIP of their session without the edit token.
- `POST /api/fips/{id}/claim`: signed-in user + valid `X-Edit-Token` on an unowned FIP -> sets `owner_id`, clears `edit_token_hash`, keeps `session_id` and `visibility`. Already-owned -> `409`.
- Knowledge models: system rows (`owner_id IS NULL`) are read-only except for admins; published versions are immutable for everyone (edits create a new version).
- FERs: `source="seed"` read-only except admin; a user may create `source="user"` FERs, visible to that user and inside any FIP that references them.

## 6. REST API

Prefix `/api`. Auth column: `–` public, `U` signed-in user, `A` admin, `T` edit token, `C` join code. All errors `{"detail": "<snake_case_code>"}`. Bodies are camelCase (Pydantic `alias_generator=to_camel`, `populate_by_name=True`). Lists return `{"items": [...], "total": n}`.

| Method | Path | Auth | Essentials | Codes |
|---|---|---|---|---|
| GET | `/health` | – | `{status, version, schemaVersion, time}` | 200 |
| POST | `/auth/register` | – | email, password, displayName, language? -> user; logs in | 201, 400, 409, 429, 403(closed) |
| POST | `/auth/login` | – | email, password -> user + Set-Cookie | 200, 401, 429 |
| POST | `/auth/logout` | U | – | 204 |
| GET | `/auth/me` | U | current user | 200, 401 |
| POST | `/auth/password` | U | currentPassword, newPassword | 204, 401, 400 |
| DELETE | `/auth/me` | U | currentPassword; anonymises FIPs (`ownerId=NULL`), deletes sessions | 204, 401 |
| GET | `/me/fips` | U | own FIPs, `?q&limit&offset` | 200 |
| GET | `/me/sessions` | U | own sessions | 200 |
| GET | `/me/knowledge-models` | U | own model versions | 200 |
| GET | `/knowledge-models` | – | published+public, plus own if signed in; `?status&q` | 200 |
| GET | `/knowledge-models/{id}/versions` | – | version list with changelog | 200, 404 |
| GET | `/knowledge-models/{id}/{version}` | – | full content (§3) | 200, 404 |
| POST | `/knowledge-models` | U | create empty *(week 3)* | 201 |
| POST | `/knowledge-models/{id}/{version}/fork` | U | *(week 3)* | 201 |
| POST | `/knowledge-models/import` | U | JSON body per §3 *(week 3)* | 201, 400 |
| PATCH | `/knowledge-models/{id}/{version}` | U | draft only *(week 3)* | 200, 409 |
| POST | `/knowledge-models/{id}/{version}/publish` | U | *(week 3)* | 200, 409 |
| GET | `/fers` | – | `?type&q&source&limit&offset`; seed + own | 200 |
| POST | `/fers` | U | id(IRI), label, type, homepage? -> `source="user"` | 201, 409 |
| POST | `/fips` | – / U / C | body: questionnaireRef, language?, community?, answers?, visibility?, sessionId?+joinCode? -> FIP + `editToken` when anonymous | 201, 400, 403, 404, 409 |
| POST | `/fips/import` | U | export doc (§3.1) -> new FIP | 201, 400, 404 |
| GET | `/fips/{id}` | – / U / T | per §5 read rule | 200, 404 |
| PATCH | `/fips/{id}` | U / T | partial: community, answers, relatedDMPs, language, license, visibility | 200, 403, 404 |
| DELETE | `/fips/{id}` | U / T | – | 204, 403, 404 |
| POST | `/fips/{id}/claim` | U + T | -> FIP now owned | 200, 403, 404, 409 |
| GET | `/fips/{id}/export.json` | – / U / T | §3.1, `Content-Disposition: attachment` | 200, 404 |
| GET | `/fips/{id}/export.csv` | – / U / T | §3.2, `text/csv` | 200, 404 |
| GET | `/fips/{id}/export.ttl` | – / U / T | *(week 3, rdflib)* | 200, 501 |
| POST | `/sessions` | U | title, questionnaireRef, defaultLanguage -> session + joinCode + joinUrl | 201, 400, 404 |
| GET | `/sessions/{id}` | U(owner) | full session | 200, 404 |
| PATCH | `/sessions/{id}` | U(owner) | title, status, defaultLanguage | 200, 404 |
| GET | `/sessions/{id}/fips` | U(owner) | all FIPs of the session | 200, 404 |
| GET | `/sessions/by-code/{joinCode}` | – | public metadata: id, title, status, questionnaireRef, defaultLanguage, facilitatorName | 200, 404 |

`joinUrl` = `{FIPM_BASE_URL}/join/{joinCode}`. `PATCH /fips/{id}` replaces `answers` wholesale when the key is present (last-write-wins; no per-answer merge in v1).

## 7. Configuration (env, `FIPM_` prefix, `config.py`)

| Var | Default | Notes |
|---|---|---|
| `FIPM_BASE_URL` | `http://localhost:8000` | used in exports, join links, CSRF check |
| `FIPM_DB_PATH` | `./fipm.db` | SQLite file; URL built as `sqlite:///{path}` |
| `FIPM_SECRET_KEY` | dev value + warning | required in prod (refuse to start if default and `FIPM_ENV=production`) |
| `FIPM_ID_PREFIX` | `""` | prepended to FIP/session short ids |
| `FIPM_ADMIN_EMAIL` / `FIPM_ADMIN_PASSWORD` | unset | first-admin bootstrap |
| `FIPM_DEFAULT_LANGUAGE` | `en` | fallback when no `Accept-Language` match |
| `FIPM_DATA_DIR` | `./data` | importer source |
| `FIPM_STATIC_DIR` | `./static` | built SPA |
| `FIPM_SESSION_TTL_DAYS` | `14` | auth cookie + row lifetime |
| `FIPM_COOKIE_SECURE` | `true` | `false` for the laptop/hotspot fallback |
| `FIPM_ALLOWED_ORIGINS` | `""` | comma-separated extras for the CSRF check |
| `FIPM_REGISTRATION_OPEN` | `true` | PLAN §9 item 5 |
| `FIPM_ENV` | `development` | `production` tightens the checks above |

SQLite pragmas on connect: `journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout=5000`. Engine with `check_same_thread=False`; sync `Session` per request via dependency.

## 8. Explicit assumptions (facilitators unavailable; revisit at the 12 Sep scope freeze)

1. **One FIP per group, not per participant.** A workshop session holds a handful of FIPs; the edit token is a *group device* token, and the group is told to keep the tab open / share the FIP URL. No per-participant identity, no concurrent-edit merge (last write wins).
2. **Declaration statuses mirror FIP-ontology terms one-to-one.** The column is a free `String`; the authoritative enum lives in `docs/specs/00-fip-ontology-mapping.md` and is exposed for validation as one tuple in `config.py`. No DB migration is needed when it is finalised.
3. **Hosting is undecided, therefore everything is env-driven.** No hard-coded domain, no absolute URL in the frontend bundle (the SPA calls relative `/api/...`); exported FIP URLs are rendered from `FIPM_BASE_URL` at export time, so a later domain move only changes one variable.
4. Single backend process (the in-process rate limiter and SQLite assume it). Horizontal scaling is v2.
5. No SMTP in v1: no email verification, no self-service reset; admins reset passwords.

## 9. Acceptance criteria

1. `POST /api/auth/register` with a fresh email returns 201, sets an `HttpOnly; SameSite=Lax` `fipm_session` cookie, and stores an argon2id hash (`$argon2id$` prefix, plaintext absent from the row); a second register with the same email (any case) returns 409.
2. `POST /api/auth/login` with the right password returns 200 and a working cookie; with a wrong password returns 401 `invalid_credentials`; 11 consecutive failures for one email return 429. `GET /api/auth/me` returns the user with the cookie and 401 without it; after `POST /api/auth/logout` the same cookie returns 401.
3. Starting the app with `FIPM_ADMIN_EMAIL`/`FIPM_ADMIN_PASSWORD` set creates exactly one user with `role="admin"`; restarting with a changed password variable leaves the stored hash unchanged and the role still `admin`.
4. `python -m fipm import-data` on an empty DB loads every `data/knowledge-models/*.json` and `data/fers/seed.json`; running it a second time changes no row (`updated_at` values identical, all counts reported as skipped) and exits 0.
5. A signed-in user can `POST /api/fips` with `questionnaireRef` and no `sessionId`, gets 201 with an 8-char base32 id (plus `FIPM_ID_PREFIX`), `ownerId` = that user, and **no** `editToken` in the response; the FIP appears in `GET /api/me/fips`.
6. An anonymous client can `POST /api/fips` with a valid `sessionId` + `joinCode` for an `open` session: 201, `ownerId` null, `sessionId` set, and `editToken` present exactly once; the same call against a `closed` session returns 409 and a wrong `joinCode` returns 403.
7. `PATCH /api/fips/{id}` on that anonymous FIP returns 403 `edit_token_required` without the `X-Edit-Token` header, 403 with a wrong token, and 200 with the correct one; no endpoint ever returns the token again.
8. Visibility: a `private` FIP returns 404 for a different signed-in user and for an anonymous client, 200 for its owner; changing it to `link` makes the same anonymous `GET` return 200; `GET /api/knowledge-models` never lists another user's private model.
9. `POST /api/fips/{id}/claim` by a signed-in user presenting the correct edit token returns 200 with `ownerId` set and `editTokenHash` cleared; a subsequent `PATCH` with the (now void) token returns 403 while the owner's cookie works; claiming an already-owned FIP returns 409.
10. `GET /api/fips/{id}/export.json` returns the §3.1 shape with `questionnaireRef` and question texts resolved in the FIP's language (a `pt-PT` FIP whose question lacks `pt-PT` falls back to `pt-BR`, then `en`); feeding that document to `POST /api/fips/import` yields a new FIP whose `answers`, `community`, `relatedDMPs`, `language`, `license` and `questionnaireRef` equal the original's.
11. `GET /api/fips/{id}/export.csv` returns `text/csv` whose header is exactly the 21 columns of §3.2 in that order, with one row per declaration and one row for each unanswered question.
12. A state-changing request without `Origin`/`Referer`, or with a foreign `Origin`, returns 403 `csrf_failed`; the same request with the app's own `Origin` succeeds. `GET` requests are unaffected.
13. `GET /api/health` returns 200 `{status:"ok", version, schemaVersion, time}` with no auth and no cookie required.
14. CI is green: `ruff check`, `ruff format --check` and `pytest` pass in the backend job, `npm run type-check && npm run build` passes in the frontend job, and `docker build .` succeeds. The built image, run with only `FIPM_DB_PATH` set, imports `data/`, serves `GET /` as the SPA `index.html` (200, `text/html`) and `GET /api/health` as 200.

## 10. Open questions for the facilitators

1. Session join by code alone (`/join/{joinCode}` with no session id) is exposed read-only via `GET /api/sessions/by-code/{joinCode}`; creating a FIP still needs `sessionId` + `joinCode`. Confirm that a 6-char code is acceptable friction versus a QR-only flow.
2. Should an anonymous session FIP default to `visibility="link"` (assumed here, so the group can share its URL and the room can compare) or `private` to the session?
3. Account deletion anonymises the user's FIPs rather than deleting them (assumed, to keep workshop output and FIP URLs stable). Needs a line in the privacy notice.
