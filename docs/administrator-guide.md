# Running FIP Manager — A Guide for Administrators and Facilitators

**FIP Manager** is a small, self-hosted tool for creating, comparing and exporting
[GO FAIR](https://www.gofair.foundation/) **FAIR Implementation Profiles (FIPs)**. It is built
to be run by one person for one community or one event: a facilitator opens a session,
participants fill in profiles on their phones, and the room compares the results side by side
and exports them as JSON, CSV and RDF.

This guide is for the person who **runs an instance** — deploying it, preparing the
questionnaires, facilitating sessions, administering users, and operating it afterwards. For
the people filling in the forms, see the
[Participant Guide](participant-guide.md); for the 30-minute CONFOA workshop runbook, see
[`workshop/facilitator-script.md`](workshop/facilitator-script.md).

> **Scale and shape.** The stack is FastAPI + SQLAlchemy + SQLite and Vue 3 + Vite. It is
> designed to be run from a single container, to survive a conference network, and to work
> offline from a laptop and a hotspot if the venue's Wi-Fi fails.

---

## Table of contents

1. [The pieces, and how they fit](#1-the-pieces-and-how-they-fit)
2. [Who can do what](#2-who-can-do-what)
3. [Deploying an instance](#3-deploying-an-instance)
4. [Configuration reference](#4-configuration-reference)
5. [Preparing the questionnaire (knowledge models)](#5-preparing-the-questionnaire-knowledge-models)
6. [Importing area questionnaires from a document](#6-importing-area-questionnaires-from-a-document)
7. [Running a session](#7-running-a-session)
8. [Comparing the results](#8-comparing-the-results)
9. [The FER catalogue](#9-the-fer-catalogue)
10. [User administration](#10-user-administration)
11. [Exports and RDF](#11-exports-and-rdf)
12. [Moving FIPs to a new questionnaire version](#12-moving-fips-to-a-new-questionnaire-version)
13. [The dashboard](#13-the-dashboard)
14. [The nanopublication network](#14-the-nanopublication-network)
15. [Operating the instance](#15-operating-the-instance)
16. [Command-line reference](#16-command-line-reference)
17. [Troubleshooting](#17-troubleshooting)

---

## 1. The pieces, and how they fit

| Term | What it is |
|---|---|
| **Knowledge model** | The questionnaire itself — sections, questions, help texts, suggested options, in every language. Versioned, and either a **draft** (editable) or **published** (frozen). |
| **Version** | A published knowledge model is immutable. Changes go into a new version; existing FIPs stay on the version they were filled against until migrated. |
| **FER** (FAIR Enabling Resource) | A named technology, service or standard that can be given as an answer. Lives either in the **system catalogue** (global) or **inline** in one knowledge model. |
| **Session** | A facilitated exercise: a join code, one or more questionnaires, and the FIPs produced in it. |
| **Area** | One of several questionnaires offered by a single session, so participants pick the one matching their field. |
| **FIP** | One community's answers. Belongs to a session, to a user's workspace, or to neither (standalone). |
| **Population** | A dashboard concept: the set of FIPs an analysis runs over — a session, this instance's public FIPs, or FIPs ingested from the network. |

Content is **data, not code**: questionnaires, the FER catalogue and translations are JSON
under `data/`. Changing the questions never requires a code change or a redeploy of the
application image.

---

## 2. Who can do what

| Role | Can |
|---|---|
| **Anonymous visitor** | Join a session and fill in a FIP; create a standalone FIP; browse public knowledge models and public FIPs; read the printed questionnaire |
| **Registered user** | All of the above, plus a workspace of their own FIPs, sessions and models; claim anonymous FIPs; set FIP visibility; create and run sessions; fork and publish knowledge models |
| **Admin** | All of the above, plus the admin page: list and search users, issue temporary passwords, promote and merge pending FERs, and edit unowned knowledge-model drafts |

![The personal workspace: my FIPs, my sessions, my knowledge models](images/workspace.png)

There is no separate "facilitator" role — **any registered user can run a session**. Facilitation
is a thing you do, not a permission you are granted.

---

## 3. Deploying an instance

### The quick path

```sh
docker compose up --build
```

### Running it directly

Backend (Python 3.12, [uv](https://docs.astral.sh/uv/)):

```sh
cd backend
uv sync
cp ../.env.example ../.env    # then edit it — see §4
uv run python -m fipm import-data
uv run python -m fipm serve   # http://localhost:8000
```

Frontend (Node 20):

```sh
cd frontend && npm install && npm run dev
```

`FIPM_DB_PATH` and `FIPM_DATA_DIR` default to `<repo-root>/fipm.db` and `<repo-root>/data`,
resolved from the config module's own location rather than the working directory, so
`import-data` and `serve` find the real `data/` whether you run them from the repo root or from
`backend/`.

### Before you let anyone in

- [ ] **Set `FIPM_SECRET_KEY`** to a real random value. The default is `dev-secret-change-me`
      and setting `FIPM_ENV=production` refuses to start with dev secrets in place.
- [ ] **Set `FIPM_BASE_URL`** to the public HTTPS URL. It is used to build join links, QR codes
      and FIP identifiers — see the warning below.
- [ ] **Serve over HTTPS** and leave `FIPM_COOKIE_SECURE=true`.
- [ ] **Create the admin user**: `uv run python -m fipm create-admin --email you@example.org --password '…'`
- [ ] **Load the content**: `uv run python -m fipm import-data`
- [ ] **Set `FIPM_CONTACT_EMAIL` and `FIPM_HOSTING_ORG`** — they appear in the privacy notice,
      which is a promise you are making to participants.
- [ ] **If behind a reverse proxy**, set `FIPM_TRUST_PROXY=true` only once you have verified the
      proxy actually sets `X-Forwarded-For`. Trusting it otherwise lets clients spoof their IP
      and defeat rate limiting.

> **`FIPM_BASE_URL` outlives your hostname.** FIP identifiers are built from it, so moving the
> instance to a different domain later changes the identity of every FIP already created.
> Decide the permanent public URL *before* the first real FIP exists, not after.

---

## 4. Configuration reference

All settings are `FIPM_`-prefixed environment variables, read by `backend/fipm/config.py`; see
`.env.example` for the authoritative list.

### Identity and security

| Setting | Default | Controls |
|---|---|---|
| `FIPM_BASE_URL` | `http://localhost:8000` | Public URL; join links, QR codes, FIP identifiers |
| `FIPM_SECRET_KEY` | `dev-secret-change-me` | Session signing — **must** be changed |
| `FIPM_ENV` | `development` | `production` refuses dev secrets |
| `FIPM_COOKIE_SECURE` | `true` | Require HTTPS for session cookies |
| `FIPM_ALLOWED_ORIGINS` | *(empty)* | CORS allow-list |
| `FIPM_TRUST_PROXY` | `false` | Trust `X-Forwarded-For` — only behind a verified proxy |
| `FIPM_MAX_BODY_BYTES` | 2 MiB | Request body size limit |
| `FIPM_SESSION_TTL_DAYS` | `14` | Facilitated session expiry |

### Storage and content

| Setting | Default | Controls |
|---|---|---|
| `FIPM_DB_PATH` | `./fipm.db` | SQLite file |
| `FIPM_DATA_DIR` | `./data` | Knowledge models and FER catalogue |
| `FIPM_STATIC_DIR` | `./frontend/dist` | Built frontend |
| `FIPM_DEFAULT_LANGUAGE` | `en` | Fallback language |
| `FIPM_ID_PREFIX` | *(empty)* | Prefix for generated IDs |

### Who may do what

| Setting | Default | Controls |
|---|---|---|
| `FIPM_REGISTRATION_OPEN` | `true` | Whether anyone may create an account |
| `FIPM_ANONYMOUS_FIPS` | `true` | Whether FIPs can be created without a session or account |
| `FIPM_REQUIRE_EMAIL_VERIFICATION` | `false` | Email verification gate — **off** for the workshop |
| `FIPM_FEEDBACK_ENABLED` | `true` | The feedback form |

### Privacy notice

| Setting | Default | Controls |
|---|---|---|
| `FIPM_CONTACT_EMAIL` | `contact@example.org` | Shown in `/privacy` |
| `FIPM_HOSTING_ORG` | `the FIP Manager operators` | Shown in `/privacy` |

### Mail

`FIPM_MAIL_BACKEND` defaults to `console` (messages are logged, not sent). For real email set it
to `smtp` and configure `FIPM_MAIL_FROM`, `FIPM_SMTP_HOST`, `FIPM_SMTP_PORT`, `FIPM_SMTP_USER`,
`FIPM_SMTP_PASSWORD`, `FIPM_SMTP_TLS`. Token lifetimes are `FIPM_MAIL_TOKEN_TTL_HOURS` (24) and
`FIPM_RESET_TOKEN_TTL_HOURS` (1).

### Integration and network

| Setting | Default | Controls |
|---|---|---|
| `FIPM_FIODMP_BASE_URL` | `https://fiodmp.fiocruz.br` | DMP linkage |
| `FIPM_EMBED_ALLOWED_ORIGINS` | `https://fiodmp.fiocruz.br` | `frame-ancestors` for the embed view |
| `FIPM_NETWORK_ENABLED` | `true` | Nanopublication network endpoints |
| `FIPM_NANOPUB_QUERY_URL` | `https://query.knowledgepixels.com` | Network query service |
| `FIPM_NETWORK_TIMEOUT_SECONDS` | `10.0` | Per-request timeout |
| `FIPM_NETWORK_CACHE_TTL_SECONDS` | `900` | Response cache |
| `FIPM_NETWORK_MAX_RESPONSE_BYTES` | 8 MiB | Upstream response cap |

### Dashboard

The dashboard has a large number of tuning settings; the ones worth knowing are:

| Setting | Default | Controls |
|---|---|---|
| `FIPM_DASHBOARD_ENABLED` | `true` | Turns the whole dashboard off |
| `FIPM_DASHBOARD_MIN_POPULATION` | `5` | k-anonymity floor — counts are withheld below this when the population contains FIPs the viewer may not open |
| `FIPM_DASHBOARD_DEFAULT_WEIGHTING` | `principle` | Similarity weighting: `principle`, `question` or `letter` |
| `FIPM_DASHBOARD_CLUSTER_MIN_SIM` | `0.6` | Similarity threshold for drawing a cluster edge |
| `FIPM_DASHBOARD_SNAPSHOT_TTL_SECONDS` | `3600` | How long a cached view stays fresh |
| `FIPM_DASHBOARD_CSV_MAX_ROWS` | `100000` | Row cap on dashboard CSV exports |
| `FIPM_DASHBOARD_BACKFILL_ON_STARTUP` | `true` | Build the projection at startup for small instances |

The remaining `FIPM_DASHBOARD_LSH_*`, `_POSTING_*` and `_MAX_CELLS` settings tune the similarity
index and the live/snapshot tier boundaries. Leave them alone unless you are running tens of
thousands of FIPs; `FIPM_DASHBOARD_LSH_BANDS × FIPM_DASHBOARD_LSH_ROWS` must equal
`FIPM_DASHBOARD_LSH_K`.

---

## 5. Preparing the questionnaire (knowledge models)

The knowledge-model editor is in your workspace. You can:

![The knowledge-model catalogue](images/knowledge-model-catalogue.png)

- **Fork** an existing model — the usual starting point. You get an editable draft.
- **Create from scratch**, or **import** a model exported elsewhere.

Within a draft you control, per question:

- **Text and help**, in each language, on language tabs (en, pt-PT, pt-BR, es).
- **FER type** — what kind of resource the question asks for. This is what makes an answer
  type-checkable, so set it deliberately.
- **Suggested FERs** — catalogue resources offered as quick picks (at most 16 per question).
- **Suggested phrases** — free-text wordings offered as quick picks, for practices that are not
  a named product (at most 12 per question). These never enter the FER catalogue.
- **Allow multiple** declarations, and **allow free text** (both on by default).
- **Compact declarations** — collapse status, note and successor behind a "more" toggle. This
  is what keeps the form usable on a phone; leave it on for workshop models.

You can reorder, hide, split and add questions, and the editor validates the model and lists
errors before you publish.

![A published knowledge model](images/knowledge-model-read.png)

> **Publishing is one-way.** A published version is frozen so that FIPs filled against it stay
> meaningful. Corrections go into a new version, with a changelog entry. Plan to publish
> *before* the event, not during it.

Order of options as participants see them: catalogue options, then suggested phrases, then
**"Outro (especificar)"**.

---

## 6. Importing area questionnaires from a document

`scripts/import-workshop-docx.py` turns a Word document of per-area option lists into one draft
knowledge model per area:

```sh
uv run --project backend python scripts/import-workshop-docx.py \
    --docx "docs/workshop/PERFIS DE IMPLEMENTAÇÃO FAIR 2.docx" --bump --report -
```

It writes `confoa-2026-<area>-<version>.json` drafts plus a report of missing questions and
unresolved options — **read the report**. Options that name a catalogue resource become
suggested FERs; descriptive phrases become suggested phrases; the sentinels "Outros", "Não se
aplica" and "Ainda não definido" are handled by the UI rather than becoming options.

Re-running is safe: a changed document produces a new draft version beside the old one, never an
overwrite. Use `--overwrite-draft` only when you deliberately want to replace an unpublished
draft.

> **The drafts are not live until a human publishes them.** Review each one in the editor —
> especially the type-mismatched options the report flags — then publish.

---

## 7. Running a session

**Create** a session from your workspace: give it a title, choose **one or more** questionnaire
versions, optionally label each as an area, and set a default language.

![Creating a session and choosing its questionnaires](images/session-new.png)

The session page is your console during the exercise:

![The session page with its join code and QR code](images/session-detail.png)

- **Join code and QR** — what participants use to get in. **Projector mode** strips the page
  chrome so the code and QR are readable from the back of a room.
- **A live list of FIPs** as they are created, updating without a refresh.
- **Exports** of every FIP in the session, together.
- **The comparison matrix** (see [§8](#8-comparing-the-results)).
- **Close** the session to stop new participants joining, and **delete** it when finished.

![The live list of FIPs in a session](images/session-fip-list.png)

![Projector mode, with the page chrome stripped away](images/projector-mode.png)

> **What deletion does.** Deleting a session cascades to the anonymous FIPs created in it. FIPs
> that participants claimed into their own accounts are detached and survive. Close a session
> when you simply want it to stop accepting joins.

A few things worth knowing before the room fills up:

- **Print a paper fallback.** Every published model has a printable questionnaire at
  `/knowledge-models/{id}/{version}/print`, with fill-in rows. Bring copies.
- **Participants do not need accounts.** Requiring registration at the door is the single
  easiest way to lose ten minutes of a thirty-minute exercise.
- **The join link is `{FIPM_BASE_URL}/join/{joinCode}`.** If the QR fails, participants can type
  the code on the home page.

![The printable paper questionnaire](images/questionnaire-print.png)

---

## 8. Comparing the results

The **comparison matrix** at `/sessions/{id}/matrix` is the view to put on the projector when the
filling-in stops. It shows principle × group, updates live as FIPs change, can be filtered to
current declarations only, and prints. Per-principle convergence shows where the room agreed and
where it did not — which is usually the most productive part of the discussion.

![The comparison matrix: principles by group](images/comparison-matrix.png)

For analysis beyond one session, use the [dashboard](#13-the-dashboard).

---

## 9. The FER catalogue

Answers name **FAIR Enabling Resources**. The catalogue has two tiers:

- **System catalogue** — global, curated, shared across models. Under `data/`.
- **Inline FERs** — defined inside a single knowledge model, for resources specific to it.

When participants write in a resource that is not in the catalogue, it becomes a **pending**
FER. On the admin page you can:

- **Promote** a pending FER into the system catalogue, and
- **Merge** two FERs, replacing every use of one with the other — the fix for the same thing
  written three ways.

> **Curate after the event, not during it.** Promoting is a judgement call about whether
> something is a real, nameable resource, and merging rewrites existing answers. Neither
> benefits from being done in a hurry with a room waiting.

---

## 10. User administration

The admin page (`/admin`, admins only) lists users with their name, email, role, creation date
and how many FIPs, sessions and models they own, and lets you search.

**Password reset** issues a temporary password, shown **once** — copy it before closing the
dialog. The user is forced to change it at next login.

![The admin page: user list and pending FERs](images/admin-page.png)

Also on this page: pending FER promote/merge, and unowned knowledge-model drafts (for example,
those written by the import script), which admins can edit and publish.

---

## 11. Exports and RDF

| Scope | Formats |
|---|---|
| One FIP | JSON, CSV, Turtle, JSON-LD |
| A whole session | JSON, CSV, Turtle |
| A questionnaire | Turtle, JSON-LD, and a printable paper version |
| A dashboard view | CSV |

RDF follows the **FIP ontology** (`https://w3id.org/fair/fip/terms/`), so exports are usable by
any FAIR tooling, not just this instance. Declarations carry their status, so "planned" and
"currently used" stay distinguishable, and `migratedFrom` records where a migrated answer came
from.

> **Outstanding:** the extension vocabulary `https://w3id.org/fipm/ns#` used by the export is
> **not yet registered** at w3id, and the terms page is not yet published. Exports are valid RDF
> and stable in shape, but that namespace does not resolve yet.

CSV exports carry a formula-injection guard, so they are safe to open in a spreadsheet.

---

## 12. Moving FIPs to a new questionnaire version

When you publish a new version of a model, existing FIPs stay on the old one. `/fips/{id}/migrate`
walks a FIP across, showing a diff of old question → new question with what was mapped, added and
removed, and flags where a question's text or FER type changed. Where one old question became
several new ones, you choose how to split its declarations. Exports record `migratedFrom`.

**FIPs created inside a session are pinned** to that session's questionnaire version and cannot
be migrated away from it — the record of what an event actually used stays intact. The migrate
page shows a notice instead of offering the move. Standalone FIPs, and FIPs that are no longer
attached to a session, migrate freely.

---

## 13. The dashboard

The dashboard analyses a **population** of FIPs — a session, this instance's public FIPs, or
FIPs ingested from the nanopublication network — across five views:

| View | Answers |
|---|---|
| **Coverage** | Which FAIR principles this population actually addresses |
| **Adoption** | Which resources are used, and how widely |
| **Similarity** | Which communities resemble each other; clusters and neighbours |
| **Gaps** | Which questions are going unanswered |
| **Evolution** | How the picture changes over time |

![The similarity view: clusters and neighbours](images/dashboard-similarity.png)

Each view exports to CSV and has a print stylesheet.

![The dashboard home with the population picker](images/dashboard-home.png)

Two behaviours to understand before you show it to anyone:

- **k-anonymity.** When a population is smaller than `FIPM_DASHBOARD_MIN_POPULATION` *and*
  contains FIPs the viewer may not open individually, counts are **withheld** rather than shown.
  A withheld count displays as such — it does not display as zero. Viewing your own session is
  deliberately exempt, so a facilitator can always read their own small room.
- **Degraded mode.** If the underlying projection is stale or missing, the dashboard says so
  rather than showing numbers it cannot stand behind. Small instances recompute on the spot;
  larger ones show a banner and the age of the data.

![The coverage view](images/dashboard-coverage.png)

Keep it current with `refresh-dashboard`, and rebuild the projection with `backfill-declarations`
after a bulk import. `check-declarations` verifies the projection still matches the FIPs.

---

## 14. The nanopublication network

With `FIPM_NETWORK_ENABLED=true`, `/network` browses and searches FIP communities published as
nanopublications, maps any network FIP onto this instance's questions (listing questions it
cannot map), and offers **"Use as starting point"** to prefill a new FIP, importing unknown
resources as catalogue FERs marked with source `network`.

Every FIP can also be downloaded as a **zip of unsigned nanopublications** — community, one per
declaration, index and FIP — in the FIP Wizard's shape, with a manifest of what publishing still
requires.

> **This instance does not publish to the network and holds no keys.** Signing needs an ORCID, an
> RSA key, a key declaration and `nanopub-py` or `nanopub-java`. The read side and the
> prepare-for-export side are complete; the publish side is deliberately not.

`ingest-network-fips` pulls network FIPs in as read-only shadow rows for dashboard analysis. They
are ingested facts, never live fetches — the dashboard never calls the network while rendering.

---

## 15. Operating the instance

**Back up the database.** `scripts/backup-db.sh` does a consistent copy of the SQLite file.
Everything a participant produced is in there; `data/` holds only the content you authored. Run
it before any migration or bulk import, and on a schedule once you are live.

**Retention.** Standalone FIPs carry a twelve-month retention promise in the privacy notice.
Nothing enforces it automatically — no scheduler ships with the tool. Run
`purge-standalone-fips` monthly, or the promise in `/privacy` is not being kept.

**Rate limiting** protects login, feedback, standalone FIP creation and saved dashboard
populations. It depends on seeing real client IPs — see `FIPM_TRUST_PROXY` in
[§3](#3-deploying-an-instance).

**Capacity.** Load-tested at 40 and 80 simulated concurrent participants with no errors and p95
under 10 ms on writes, with SQLite in WAL mode. A conference room is not a scale problem;
`scripts/load-test.py` re-runs the check.

**Offline fallback.** The whole stack runs from a laptop and a hotspot. Test this before the
event, with a real phone joining a real hotspot — it is the contingency most likely to be needed
and least likely to have been tried.

---

## 16. Command-line reference

Run as `uv run python -m fipm <command>` from `backend/`.

| Command | Key arguments | Does |
|---|---|---|
| `import-data` | `--force` | Loads `data/` knowledge models and FER catalogue into the database. Idempotent; `--force` overwrites changed models |
| `create-admin` | `--email`, `--password` | Creates a user as admin, or promotes an existing one |
| `serve` | `--host`, `--port`, `--reload` | Runs the API server |
| `purge-standalone-fips` | `--older-than-days` (365), `--dry-run` | Deletes standalone FIPs untouched for N days. **Always dry-run first** |
| `backfill-declarations` | `--batch`, `--questionnaire`, `--since`, `--only-stale`, `--dry-run`, `--progress` | Rebuilds the dashboard projection. Idempotent and batched |
| `check-declarations` | `--sample`, `--all`, `--fix`, `--json` | Verifies the projection matches the FIPs |
| `refresh-dashboard` | `--population`, `--all-saved`, `--views`, `--force`, `--json` | Recomputes cached dashboard snapshots |
| `ingest-network-fips` | `--limit`, `--community`, `--since`, `--json` | Pulls network FIPs in as read-only shadow rows |

---

## 17. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| **Refuses to start in production** | Dev secrets still in place. Set a real `FIPM_SECRET_KEY`. |
| **Join links or QR codes point at localhost** | `FIPM_BASE_URL` is unset or wrong. It is also baked into FIP identifiers — fix before real data exists. |
| **Participants can't sign in, but should be able to** | Check `FIPM_REGISTRATION_OPEN`, and `FIPM_REQUIRE_EMAIL_VERIFICATION` (which needs a working mail backend — the default only logs). |
| **No email arrives** | `FIPM_MAIL_BACKEND` defaults to `console`. Set it to `smtp` and configure the SMTP settings. |
| **Rate limiting blocks or ignores the wrong people** | Client IPs are wrong. Set `FIPM_TRUST_PROXY=true` only behind a proxy you have verified. |
| **Questions or translations don't appear after editing `data/`** | Run `import-data` (`--force` if the model changed). |
| **Dashboard shows a stale-data banner** | Run `backfill-declarations`, then `refresh-dashboard`. |
| **Dashboard withholds counts** | k-anonymity. Expected for small populations containing FIPs the viewer may not open; not an error. |
| **A FIP can't be migrated** | Its model version is pinned. |
| **A resource appears three times under different names** | Merge them on the admin page. |
| **`/network` is empty or off** | `FIPM_NETWORK_ENABLED`, or the upstream query service is unreachable. The rest of the tool is unaffected. |

---

## Attribution

Questionnaire content: FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, Barbara Magagna,
Jacintha Schultes / GO FAIR Foundation, CC BY-SA 4.0. Area pick-lists adapted from "PERFIS DE
IMPLEMENTAÇÃO FAIR 2" (author to be confirmed), used under the same CC BY-SA 4.0 terms.
