# Spec 13 – FIP dashboard: a scale-first design

Status: approved for implementation, 11 Sep 2026. Implements `12-understanding-assurance-dashboard.md` §C
(the five views the project lead asked for) under one explicit requirement from the lead: *"the numbers may
increase significantly so the application should be prepared to deal with this."* Scale is therefore the
primary constraint of this spec, not an afterthought — every mechanism below states the order of magnitude it
holds to, and what takes over above it.

Authority: PLAN §4–§5. Builds on `03-matrix-and-rdf.md` (the convergence key, reused verbatim),
`08-workshop-picklists.md` (`notApplicable`, multi-questionnaire sessions and *areas*),
`11-nanopub-network.md` (the network proxy and `network_origin`), `12-…` §A/§B (the understanding and
assurance fields this projection carries columns for before they exist). **Not here:** spec 12 §A/§B
themselves; they land as content and editor changes and this dashboard reads whatever they produce.

## 0. The three scale points, and what each mechanism is designed for

| | today (CONFOA, 6 Oct 2026) | plausible 2027 | upper design point |
|---|---|---|---|
| FIPs in one population | ~40 | 10k | 100k |
| FER catalogue | 138 | 10k | 10k |
| Knowledge-model versions | ~7 | 1k | 1k |
| Sessions | 1 | hundreds | thousands |
| Derived rows (`fip_cells`) | ~840 | 210k | 2.1M |
| Derived rows (`fip_declarations`) | ~700 | 205k | 2.05M |

Target: **p95 < 500 ms server time per view at the upper end**, on SQLite today and Postgres later with no
rewrite. The design achieves that by a three-tier rule, stated once and referred to throughout:

| Tier | Condition | Path | p95 target |
|---|---|---|---|
| **T1 live** | effective population ≤ `FIPM_DASHBOARD_LIVE_MAX_CELLS` (default 250 000 `fip_cells` rows, ≈ 12k FIPs) | one aggregate query over the projection, per request | < 150 ms |
| **T2 snapshot** | above T1 | a stored `dashboard_snapshots` row, one PK fetch + JSON body | < 30 ms |
| **T3 refuse** | above T1, no fresh snapshot, cost estimate above `FIPM_DASHBOARD_SYNC_MAX_CELLS` (default 600 000) | `202 snapshot_pending` + `Retry-After`, background refresh | n/a |

Nothing in this spec is O(n²) at request time, and nothing aggregates over a JSON column.

## 1. The derived projection

### 1.1 Why, and the one decision that shapes everything

`Fip.answers` is a JSON column. Every view in spec 12 §C2 is an aggregate over the *inside* of that column.
`json_extract` over 100k rows is a full scan of 100k wide, JSON-bearing pages, it is SQLite-only, and it
cannot be indexed usefully. So: a **write-maintained, normalised projection**, read by column, never by JSON
path, in any hot path.

**D1 — two fact tables, not one.** The brief sketched a single `fip_declarations` carrying both
per-declaration facts (`fer_key`, `status`) and per-answer facts (`not_applicable`). Rejected: that table has
a mixed grain, and every coverage/gaps query over it would either double-count a cell with two `current`
declarations or need a `DISTINCT` subquery, which is exactly the per-request cost we are trying to remove.
Instead:

- **`fip_cells`** — grain **(fip_id, question_id)**, one row per question of the FIP's own questionnaire,
  answered or not. This is the *cell* of the matrix. It makes coverage and gaps single `GROUP BY`s with no
  join, no `DISTINCT`, and no outer join against a question list.
- **`fip_declarations`** — grain **(fip_id, question_id, decl_index)**, one row per stored declaration. This
  is what adoption, evolution, the inverted index and similarity read.

**D2 — no denormalised `visibility`/`owner_id` on the fact tables.** The brief suggested denormalising them
for index-only filtering. Rejected on security grounds: a denormalised visibility is a *cached authorization
decision*. If the projection lags one `PATCH /api/fips/{id}` that flips `public` → `private`, a public
aggregate leaks that FIP's answers, and the leak is invisible. Instead the population is resolved in a
separate first phase against the **authoritative `fips` table** (§2), behind covering indexes, and the fact
tables are semi-joined on `fip_id` (their leading PK column). Authorization then has exactly one home and
can never be stale. The cost is one extra index-only scan of ≤100k narrow rows (~10–25 ms at the upper end),
which is why T2 exists. The things that *are* denormalised are the ones that are expensive to derive and
carry no authorization meaning: they live on `fip_facets`, one row per FIP.

### 1.2 `fip_facets` — one row per FIP

```
fip_facets
  fip_id                   TEXT  PK
  source                   TEXT  NOT NULL   -- 'local' | 'network'  (§5.4)
  questionnaire_id         TEXT  NOT NULL
  questionnaire_version    TEXT  NOT NULL
  area_key                 TEXT  NULL       -- 'questionnaire_id@version'; the session's ref label resolves at read time (spec 08 §3.3)
  language                 TEXT  NOT NULL
  question_count           INT   NOT NULL   -- questions in this FIP's questionnaire
  answered_questions       INT   NOT NULL   -- >=1 declaration OR notApplicable (spec 08 §2.2)
  not_applicable_questions INT   NOT NULL
  declaration_count        INT   NOT NULL
  current_declarations     INT   NOT NULL
  token_count              INT   NOT NULL   -- size of the similarity token set (§4.2)
  migrated_from_id         TEXT  NULL       -- from fips.migrated_from, flattened (spec 07 §4.3)
  migrated_from_version    TEXT  NULL
  fip_created_at           DATETIME NOT NULL
  fip_updated_at           DATETIME NOT NULL   -- copy of fips.updated_at at projection time
  projected_at             DATETIME NOT NULL   -- when this projection was written
  projection_epoch         INT   NOT NULL      -- dashboard_meta['projection_epoch'] at projection time
```

`fip_updated_at` vs `fips.updated_at` is the staleness detector (§1.7). `projection_epoch` catches the other
staleness: a knowledge-model edit changed a question's `principle`/`scope`/`ferType`/`hidden`, so the
projection is wrong even though the FIP did not change.

Indexes: `ix_facets_source_updated (source, fip_updated_at)`, `ix_facets_km (questionnaire_id,
questionnaire_version)`, `ix_facets_epoch (projection_epoch)`, `ix_facets_stale (projected_at)`.

### 1.3 `fip_cells` — the matrix cell, materialised

```
fip_cells
  fip_id            TEXT  NOT NULL   -- PK part 1
  question_id       TEXT  NOT NULL   -- PK part 2
  question_index    INT   NOT NULL   -- position in knowledge-model order, so views never re-derive order
  principle         TEXT  NULL       -- 'A1'   = sub_principle up to the first '.'
  sub_principle     TEXT  NULL       -- 'A1.1' = question.principle verbatim
  principle_group   TEXT  NOT NULL   -- 'A', or 'Other' when question.principle is NULL (matrix.ts's principleGroup)
  principle_known   BOOLEAN NOT NULL -- sub_principle in rdf.KNOWN_PRINCIPLE_IDS
  scope             TEXT  NULL       -- 'metadata' | 'data' | NULL  (the brief's "target"; named `scope` to match question.scope and matrix.ts)
  fer_type          TEXT  NULL       -- question.ferType, one of the 12 in data/fers/fer-types.json
  cell_state        TEXT  NOT NULL   -- see below, exactly one value
  decl_count        INT   NOT NULL
  current_count     INT   NOT NULL
  planned_count     INT   NOT NULL   -- planned + planned-development + planned-replacement
  none_count        INT   NOT NULL
  not_applicable    BOOLEAN NOT NULL
  max_assurance     TEXT  NULL       -- spec 12 §B3, highest over this cell's declarations; NULL until B3 lands
  coherence_flags   INT   NOT NULL DEFAULT 0   -- spec 12 §A3; 0 until A3 lands
  type_mismatch_ack BOOLEAN NOT NULL DEFAULT 0 -- spec 12 §A2; false until A2 lands
  PRIMARY KEY (fip_id, question_id)
```

`cell_state`, one of exactly six, derived once at projection time so no view ever writes a `CASE` over
declarations:

| value | meaning |
|---|---|
| `current` | ≥1 `current` declaration (the only state that counts as "the community does this today") |
| `planned` | no `current`, ≥1 `planned` / `planned-development` / `planned-replacement` |
| `none` | declarations exist and all are `none` (spec 02 §1: a deliberate "we use nothing") |
| `not-applicable` | `answer.notApplicable === true` (spec 08 §2.2 — answered, no chips) |
| `unanswered` | the question exists in this FIP's questionnaire and has no answer entry, or an entry with no declarations |
| `absent` | reserved: the question is not in this FIP's own questionnaire. Never written today (a FIP has exactly one questionnaire; `absent` is a *session matrix* concept, spec 08 §3.3) but kept in the enum so a cross-questionnaire population renders the same three-way distinction the matrix already makes |

Precedence is exactly that order, so the six are mutually exclusive and `SUM` over them equals the FIP count.
`hidden: true` questions (spec 04 §4) produce **no** `fip_cells` row at all, matching the RDF export.

Indexes:

```
PRIMARY KEY            (fip_id, question_id)                     -- the semi-join, and per-FIP scoring
ix_cells_q_state       (question_id, cell_state, fip_id)         -- coverage/gaps: leading group keys, fip_id for the semi-join
ix_cells_subp_state    (sub_principle, cell_state, fip_id)       -- coverage rolled up to the 12 principle codes
ix_cells_fertype_state (fer_type, cell_state, fip_id)            -- the FER-type cut of coverage
```

All four are covering for their query: nothing in coverage or gaps touches the table heap.

### 1.4 `fip_declarations` — one row per declaration

```
fip_declarations
  fip_id             TEXT  NOT NULL   -- PK part 1
  question_id        TEXT  NOT NULL   -- PK part 2
  decl_index         INT   NOT NULL   -- PK part 3; the stored order, = the RDF export's fipmx:declaration-index
  principle          TEXT  NULL
  sub_principle      TEXT  NULL
  principle_group    TEXT  NOT NULL
  scope              TEXT  NULL
  fer_type           TEXT  NULL       -- the *question's* expected type
  fer_key            TEXT  NOT NULL   -- THE CONVERGENCE KEY (§1.5)
  fer_id             TEXT  NULL       -- the catalogue/network FER IRI, or NULL for free text
  free_text_hash     TEXT  NULL       -- rdf._free_text_hash(text), 16 hex chars, or NULL for a catalogue FER
  status             TEXT  NOT NULL   -- one of config.DECLARATION_STATUSES
  successor_fer_key  TEXT  NULL       -- same key rule, from successorFerId/successorFreeText (spec 05 §5)
  assurance_level    TEXT  NULL       -- spec 12 §B3: 'declared' | 'evidenced' today; NULL when unknown
  has_note           BOOLEAN NOT NULL
  PRIMARY KEY (fip_id, question_id, decl_index)
```

Indexes:

```
PRIMARY KEY               (fip_id, question_id, decl_index)
ix_decl_ferkey_q_fip      (fer_key, question_id, fip_id)      -- THE INVERTED INDEX (§4.3); also adoption's group key
ix_decl_status_ferkey_fip (status, fer_key, fip_id)           -- adoption filtered by status, evolution
ix_decl_q_status_ferkey   (question_id, status, fer_key, fip_id)
ix_decl_succ              (successor_fer_key, fip_id)         -- evolution's successor pairs
ix_decl_fer_id            (fer_id, fip_id)                    -- "which FIPs declare FER X" from a FER page
```

Every index above is covering for the query that uses it. `fer_key` is deliberately the *leading* column of
the inverted index: candidate generation (§4.3) is a range scan on one value per key.

### 1.5 The convergence key — reused, not reinvented

```
fer_key = fer_id  if the declaration has a ferId
        = 'text:' + normalise(fer_free_text)  otherwise
```

`normalise` is NFC → strip → collapse internal whitespace → casefold, i.e. **exactly**
`frontend/src/lib/matrix.ts::normaliseFreeText` and **exactly** the normalisation inside
`backend/fipm/rdf.py::_free_text_hash`. The projection calls a new
`fipm.projection.convergence_key(declaration) -> str` which delegates its free-text branch to a new
`rdf.normalise_free_text(text) -> str` refactored **out of** `_free_text_hash` (which then becomes
`sha256(normalise_free_text(t))[:16]`), so there is one normalisation in the backend and a test asserts the
frontend's against it over a fixture table of tricky inputs (combining accents, NBSP, Turkish dotless ı,
CRLF). A declaration carrying neither a FER nor text (a bare `none`) gets `fer_key = 'none:' + status`,
again matching `matrix.ts`. **No third identity rule may be introduced anywhere in this spec.**

### 1.6 Keeping it in step with `Fip.answers`

**D3 — one ORM-level hook, not eight call sites.** `fipm/projection.py` registers, on `SessionLocal`:

- `after_flush`: collect the ids of every `Fip` in `session.new | session.dirty | session.deleted` into
  `session.info["fipm_projection_dirty"]` / `"…_deleted"`. Also collect `KnowledgeModel` ids whose `content`
  changed, into `"…_epoch_bump"`.
- `before_commit`: for each dirty id, `reproject_fip(session, fip_id)`; for each deleted id,
  `unproject_fip(session, fip_id)`; if any epoch bump, increment `dashboard_meta['projection_epoch']` and
  enqueue the affected questionnaire ref in `dashboard_meta['reprojection_backlog']` (a JSON list read by
  the CLI — **not** reprojected inline; 100k FIPs cannot be reprojected inside a KM save). Re-entrancy is
  guarded by a flag in `session.info`, and a `projection_suspended()` context manager turns the hook off for
  the backfill CLI, which writes in bulk instead.

Rationale: a future router, a CLI command or `importer.py` cannot forget it, the whole projection lands
**inside the caller's transaction** (so a rolled-back FIP write leaves no projection rows), and there is one
place to test. The known writers it covers today: `routers/fips.py` `create_fip`, `patch_fip`, `import_fip`,
`delete_fip`, `create_fip_from_network`, `claim_fip`, the migration apply, and `routers/sessions.py`
`delete_session`.

**Bulk paths bypass ORM events** and must call the projection explicitly. There are exactly two today, both
`Query.delete(synchronize_session=False)`:

- `cli.py::_cmd_purge_standalone_fips` — collect the ids first, `unproject_fip` each, then delete.
- `routers/sessions.py::delete_session` deletes anonymous FIPs one by one via `db.delete()`, so the hook
  already covers it; the `session_id = None` detach path is a normal `dirty` update and is covered too.

A test greps the diff for `synchronize_session=False` on `Fip` and fails on any new occurrence without an
adjacent `unproject_fip`.

Cost per FIP write: 21 `fip_cells` + ~27 `fip_declarations` + 1 `fip_facets` + 1 `fip_signatures` + 32
`fip_signature_bands` ≈ 82 rows, written as five `DELETE` + five `executemany` `INSERT`s. Budget: **< 10 ms
added to a FIP PATCH**, asserted by a test (§8, AC-14). Holds at every scale — it is per-FIP work, not
per-population.

### 1.7 CLI: backfill, and the consistency check

```
python -m fipm backfill-declarations [--batch 500] [--questionnaire ID@VERSION] [--since ISO8601]
                                     [--only-stale] [--fips-from FILE] [--dry-run] [--progress]
python -m fipm check-declarations    [--sample N | --all] [--fix] [--json]
```

`backfill-declarations` is **idempotent** — it is delete-then-insert per FIP, inside `projection_suspended()`,
committing every `--batch` FIPs so a 100k-FIP run can be interrupted and resumed. `--only-stale` selects
`fips` whose `id` has no `fip_facets` row, or whose `updated_at > fip_facets.fip_updated_at`, or whose
`fip_facets.projection_epoch < dashboard_meta['projection_epoch']`, or whose questionnaire ref is in
`reprojection_backlog`; it clears the backlog entry it has drained. Throughput target: **≥ 400 FIPs/s**
(≈ 4 min for 100k), single-threaded, WAL already on. `--progress` prints one line per batch.

`check-declarations` recomputes cells, declarations, facets and the signature for a random sample (default
1000) or all FIPs and diffs them against the stored rows, plus four whole-table invariants:

1. every `fips.id` with a readable questionnaire has a `fip_facets` row (`source='local'`);
2. no `fip_facets`/`fip_cells`/`fip_declarations`/`fip_signatures`/`fip_signature_bands` row for a
   nonexistent `fips.id` unless `source='network'` (§5.4);
3. per FIP, `COUNT(fip_cells) = fip_facets.question_count` and
   `COUNT(fip_declarations) = fip_facets.declaration_count`;
4. per FIP, `COUNT(fip_signature_bands) = FIPM_DASHBOARD_LSH_BANDS`.

Exit 0 clean, 1 on any mismatch (printing the first 20), `--fix` reprojects them. `--json` for cron.

### 1.8 Stale or missing projection: degrade, never lie

Every dashboard request resolves its population first (§2), then counts the members that are stale or
unprojected with **one** query over `fip_facets` joined to the population CTE. Then:

| situation | behaviour |
|---|---|
| nothing stale | normal path |
| stale/missing, and effective population ≤ `FIPM_DASHBOARD_FALLBACK_MAX_FIPS` (default 200) | compute the view **on the fly** from `fips.answers`, in Python, calling the *same* `projection.project_answers()` that writes the tables (one code path, so the two can't disagree); response carries `"degraded": true, "degradedReason": "projection_stale", "staleFips": n`; `Cache-Control: no-store`, no snapshot written, no ETag |
| stale/missing, population > 200 | `409 {"detail":"projection_stale","staleFips":n,"totalFips":m,"hint":"python -m fipm backfill-declarations --only-stale"}` |
| the projection tables are entirely empty and `fips` is non-empty | same `409`, `detail:"projection_missing"` |

The rule in one sentence: **small populations degrade to slow-but-correct; large populations refuse; nothing
ever returns a number computed from a partial projection.** A mixed answer is the one outcome this design
treats as a bug.

### 1.9 Postgres compatibility rules (binding on the builders)

- Everything is SQLAlchemy Core (`select()`, `func.count()`, `case()`), never `text()` with dialect SQL, in
  any query that runs per request.
- **No JSON1 anywhere in a hot path.** `json_extract`, `->>`, `json_each` are forbidden outside the
  projection writer and the §1.8 fallback.
- No `INSERT OR REPLACE`, no `INSERT … ON CONFLICT` (delete-then-insert instead), no `GROUP_CONCAT` /
  `string_agg` (concatenate in the Python layer after the aggregate), no `PRAGMA` outside `db.py`.
- `COUNT(DISTINCT x)`, `SUM(CASE WHEN … )`, `HAVING`, window-free CTEs only — all portable.
- Signatures are `LargeBinary`; band hashes are `BigInteger` masked to 62 bits so they are positive and
  representable on both.
- Index names ≤ 63 characters (Postgres's identifier limit). The names in §1.3/§1.4 are all ≤ 26.
- Datetimes are `DateTime(timezone=True)` with UTC-aware Python values, like every existing model.

`db.py` gains one thing beyond the version bump: **`_ensure_indexes()`**. `Base.metadata.create_all()` creates
missing *tables* but, for a table that already exists, does not create newly declared indexes — so the four
new covering indexes on the pre-existing `fips` table (§2.2) would silently never appear on an upgraded
database. `_ensure_indexes()` issues `CREATE INDEX IF NOT EXISTS` for a declared list, after
`_ensure_columns()`, before the `schema_version` bump, with the same duplicate-tolerant error handling.

## 2. Populations: definition, resolution, authorization

### 2.1 A population is a saved, shareable query

```json
{"version": 1,
 "include": [
   {"kind": "session",       "id": "s_abc"},
   {"kind": "public"},
   {"kind": "network"},
   {"kind": "questionnaire", "id": "gofair-fip-mini", "version": "2.0.0"},
   {"kind": "area",          "sessionId": "s_abc", "id": "gofair-fip-mini-bio", "version": "1.0.0"},
   {"kind": "mine"}
 ],
 "exclude": [{"kind": "session", "id": "s_test"}],
 "updatedAfter": "2026-01-01T00:00:00Z",
 "updatedBefore": null}
```

Semantics: **union of `include`, minus union of `exclude`, intersected with the date range, intersected with
what the viewer may read.** `include` and `exclude` each hold 1–20 terms. Six term kinds, no more — an
unknown `kind` is `400 invalid_population`, never ignored.

Canonicalisation: sort each term list by `(kind, id, version, sessionId)`, drop duplicates, drop nulls,
serialise with `json.dumps(…, sort_keys=True, separators=(",", ":"))`. `spec_hash = sha256(canonical)`.

`dashboard_populations(hash TEXT PK, owner_id TEXT NULL, label TEXT, spec JSON NOT NULL, auth_scope TEXT NOT
NULL, created_at, last_used_at)` with `ix_dashpop_owner (owner_id, created_at)`. `POST
/api/dashboard/populations` saves one (idempotent on `hash`); `GET /api/dashboard/populations` lists the
viewer's own plus every `auth_scope='pub'` one. Every view accepts **either** `?population=<hash>` **or** an
inline `?pop=<urlsafe-base64 of the canonical JSON>` capped at 2 KB, so a facilitator can share a URL without
first saving anything. Three shorthands expand server-side: `?pop=session:<id>`, `?pop=public`,
`?pop=network`.

### 2.2 Resolution, and the security predicate

Phase 1, one query, index-only, against the **authoritative `fips` table** (D2):

```sql
WITH pop AS (
  SELECT f.id AS fip_id, f.updated_at
  FROM fips f
  WHERE (  /* include, OR-ed */
           (:inc_public      = 1 AND f.visibility = 'public')
        OR (f.session_id IN :inc_sessions)
        OR ((f.questionnaire_id, f.questionnaire_version) IN :inc_km_refs)
        OR (:inc_mine = 1 AND f.owner_id = :viewer_id)
       )
    AND NOT ( (f.session_id IN :exc_sessions)
           OR ((f.questionnaire_id, f.questionnaire_version) IN :exc_km_refs) )
    AND (:after  IS NULL OR f.updated_at >= :after)
    AND (:before IS NULL OR f.updated_at <  :before)
    AND (  /* THE SECURITY PREDICATE — never omitted, never denormalised */
           f.visibility = 'public'
        OR (:viewer_id IS NOT NULL AND f.owner_id = :viewer_id)
        OR (:viewer_id IS NOT NULL AND f.session_id IN :viewer_owned_sessions)
        OR :viewer_is_admin = 1
       )
  UNION ALL
  SELECT n.fip_id, n.fetched_at FROM network_fips n WHERE :inc_network = 1
)
```

New covering indexes on `fips` (created by `_ensure_indexes()`, §1.9):

```
ix_fips_pop_vis  (visibility, updated_at, id, session_id, owner_id, questionnaire_id, questionnaire_version)
ix_fips_pop_sess (session_id, updated_at, id, visibility, owner_id)
ix_fips_pop_km   (questionnaire_id, questionnaire_version, updated_at, id, visibility, owner_id, session_id)
ix_fips_pop_own  (owner_id, updated_at, id, visibility, session_id)
```

They are wide on purpose: `SELECT f.id` behind a narrow index still needs a heap lookup, and the `fips` heap
page carries the whole `answers` JSON — the single most expensive page in the database. Covering them keeps
population resolution off the heap entirely. Cost: 4 × 100k × ~90 B ≈ 36 MB.

Authorization rules, stated flatly:

- **private** FIPs enter a population only for their owner or an admin.
- **link** FIPs are **excluded from every population** except the owner's own (`mine`), the session
  population of a session the viewer owns, and admin scope. A link FIP is *unlisted*, and folding it into a
  public aggregate publishes it. (Recorded as assumption A4; this is stricter than `authz.can_read`, which
  lets anyone read a link FIP *by id*. Being in an aggregate is not the same as being fetchable by id.)
- **public** FIPs enter any population.
- Anonymous session FIPs (`owner_id IS NULL`) reach the session owner through `session_id`.
- An anonymous viewer has `viewer_id = NULL`, so only the `visibility='public'` and `network` branches fire.

### 2.3 The population hash includes the authorization scope

A snapshot key derived from the spec alone would let a snapshot computed for an owner be served to a stranger.
So:

```
auth_scope = 'pub'          when every include/exclude term is 'public' or 'network'
           = 'u:<owner_id>' when any term is 'mine', 'session' or 'area'
           = 'admin'        when the viewer is an admin AND the resolved set differs from the 'pub' set
population_hash = sha256(canonical_spec + '|' + auth_scope)[:32]
```

`auth_scope='pub'` populations are the interesting case: identical for every viewer, so one snapshot serves
everybody — which is exactly the 2027 workload (the network and public populations). Owner-scoped snapshots
are per-user and therefore rarer and smaller. A test asserts that two viewers with different rights on the
same spec never read each other's snapshot row.

### 2.4 k-anonymity

```
FIPM_DASHBOARD_MIN_POPULATION  (default 5)
```

Rule: let `k_hidden` be the number of FIPs in the effective population that the viewer **could not read
individually** via `GET /api/fips/{id}` (i.e. not public, not owned, not in an owned session, viewer not
admin). If `0 < effective_count < K` **and** `k_hidden > 0`, refuse:

```
403 {"detail": "population_too_small", "minimum": 5}
```

`count` is echoed **only** when `k_hidden == 0`. An empty effective population is `200` with all-zero
aggregates and `"fipCount": 0` — not a 403, so a stranger cannot distinguish "your query matched nothing"
from "it matched something you may not see".

Honest note on what this buys: with today's visibility rules the predicate in §2.2 already removes every FIP
the viewer cannot read individually, so `k_hidden` is 0 and the threshold **almost never binds** — the
facilitator's 3-FIP workshop session keeps working, which is the requirement. K is defence in depth for the
two ways that changes: (a) any future population term that admits a FIP the viewer cannot open (an
organisation scope, a consortium scope, spec 12 §B4 assessment aggregates); (b) **differencing** — the
`exclude` list makes `public MINUS (public ∧ area=X)` expressible, so the count is taken **after** exclusions
and the same threshold applies to the difference. Additionally, and independently of K: **no aggregate
response ever names a FIP the viewer cannot read individually.** Views that name FIPs (similarity neighbours,
cluster representatives, evolution's per-FIP rows) filter their *output* through the same
`readable_individually` predicate, not merely the population predicate. A test covers both.

## 3. The five views as contracts

Common to all five: `GET`, read-only, `optional_user` (anonymous callers get the public/network populations),
`503 dashboard_disabled` when `FIPM_DASHBOARD_ENABLED=false`. Common query parameters: `population` /
`pop` (§2.1), `updatedAfter`, `updatedBefore`. Common response envelope:

```json
{"population": {"hash": "…", "authScope": "pub", "fipCount": 9412, "label": "All public FIPs"},
 "tier": "live" | "snapshot",
 "computedAt": "2026-09-11T10:00:00Z",
 "degraded": false,
 "etag": "W/\"coverage-3f9a…-a1b2-17-2026091110-9412\"",
 "data": { … per view … }}
```

ETag: `W/"<view>-<population_hash[:12]>-<params_hash[:8]>-<projection_epoch>-<max_updated_at>-<fip_count>"`.
`If-None-Match` → `304`. `Cache-Control: private, max-age=0, must-revalidate` (`public` when
`authScope='pub'`).

### 3.1 Coverage — `GET /api/dashboard/coverage`

Params: `groupBy=question|subPrinciple|principle|group` (default `subPrinciple`), `scope=metadata|data|any`,
`includeAssurance=0|1`.

**`groupBy` is a presentation parameter, not an aggregation parameter** (amended 11 Sep 2026, §11.1). The
aggregate below always runs at the **finest, per-question grain**, and the response's `rows` are **always
per-question**, whatever `groupBy` says — each row carrying its own `questionId`, `subPrinciple`, `principle`
and `principleGroup`, i.e. every rollup key at once. `groupBy` then decides only what the *handler* does
with those rows before serialising:

- `groupBy=question` (what the SPA always sends) — the per-question rows, untouched. The SPA rolls up to
  sub-principle / principle / group **client-side** in `lib/dashboard.ts`, so a grouping change is no
  refetch, exactly as the matrix's language switch is no refetch (§6.3).
- `groupBy=subPrinciple|principle|group` — the handler performs the same rollup server-side and returns the
  coarser rows, with `level` set accordingly and `questions`/`ferTypes` listing what was folded in. This
  exists **only** for direct API and CSV consumers (§3.6), which have no client to roll anything up.

The two paths must agree: a test asserts that the server-side rollup at each level equals the client-side
rollup of `groupBy=question` over the same population (§8.1 test 17). Because the grain of the aggregate
never changes, `groupBy` changes neither the cost nor the cardinality bound below — only the number of rows
serialised.

**One `GROUP BY`, no join, no `DISTINCT`, index-only on `ix_cells_q_state`:**

```sql
SELECT c.sub_principle, c.principle, c.principle_group, c.question_id, c.question_index,
       c.scope, c.fer_type, c.cell_state, COUNT(*) AS n
FROM fip_cells c
WHERE c.fip_id IN (SELECT fip_id FROM pop)
GROUP BY c.sub_principle, c.principle, c.principle_group, c.question_id, c.question_index,
         c.scope, c.fer_type, c.cell_state
```

Result cardinality is bounded by **questions × 6**, i.e. ≤126 rows for the GO FAIR model and ≤ (largest
questionnaire) × 6 for a custom one — independent of population size. `includeAssurance=1` adds
`c.max_assurance` to the grouping (× 5 states, still ≤630 rows). Any rollup of those ≤126 rows to
principles/groups happens in Python **after** the aggregate — on the server for a `groupBy` other than
`question`, in the SPA otherwise; either way it is a fold over ≤126 rows, not per-row work.

Response `data`:

```json
{"rows": [{"key": "F1-metadata", "level": "question",
           "subPrinciple": "F1", "principle": "F1", "principleGroup": "F",
           "questions": ["F1-metadata"], "ferTypes": ["identifier-service"],
           "counts": {"current": 7102, "planned": 812, "none": 240, "notApplicable": 95,
                      "unanswered": 1163, "absent": 0},
           "shares": {"current": 0.7545, "planned": 0.0863, "none": 0.0255,
                      "notApplicable": 0.0101, "unanswered": 0.1236, "absent": 0.0},
           "assurance": {"declared": 6800, "evidenced": 302}}],
 "totals": {"fips": 9412, "cells": 197652},
 "order": ["F1-metadata", "F1-data", "F2", "F3", "F4-metadata", "F4-data", "A1.1-metadata", "…"]}
```

`key` is the row's key **at its own `level`** — the `questionId` at `level: "question"` (the default and the
only level the SPA requests), the principle code at `level: "subPrinciple"`, and so on. `subPrinciple`,
`principle` and `principleGroup` are present on **every** row at every level, which is what makes the
client-side rollup possible without a refetch. `shares` carries all six keys explicitly (no `"…"`), summing
to 1.0 per row. `order` is the row keys in `question_index` order at the requested level, so the frontend
reproduces the matrix's row order without holding the knowledge model.

Cost: 40 FIPs → 840 rows scanned, < 3 ms. 12k FIPs → 250k rows, ~90 ms (T1 ceiling). 100k FIPs → 2.1M rows,
0.6–1.5 s on SQLite → **T2 snapshot**. Pagination: none — the response is bounded by the questionnaire, not
the population. Cap: `absent`/`unanswered` rollups never expand; a questionnaire with > 500 questions is
rejected with `413 questionnaire_too_large` (no such model exists; the cap keeps the bound honest).

### 3.2 Resource adoption — `GET /api/dashboard/adoption`

Params: `groupBy=fer|ferType|area|question` (default `fer`), `status=current|planned|any` (default
`current`), `catalogued=only|exclude|any` (default `any` — the free-text long tail of spec 12 §C2 is
`catalogued=exclude`), `limit` (default 50, max 200), `offset`, `sort=fips|fer` (default `fips`).

**One `GROUP BY`, index-only on `ix_decl_ferkey_q_fip` / `ix_decl_status_ferkey_fip`:**

```sql
SELECT d.fer_key, d.fer_id, d.status, COUNT(DISTINCT d.fip_id) AS fips, COUNT(*) AS declarations
FROM fip_declarations d
WHERE d.fip_id IN (SELECT fip_id FROM pop)
  AND (:status = 'any' OR d.status = :status)
  AND (:catalogued <> 'only'    OR d.fer_id IS NOT NULL)
  AND (:catalogued <> 'exclude' OR d.fer_id IS NULL)
GROUP BY d.fer_key, d.fer_id, d.status
ORDER BY fips DESC, d.fer_key ASC
LIMIT :limit OFFSET :offset
```

`COUNT(DISTINCT d.fip_id)` is required: a FIP may declare the same FER on two questions (ORCID under F1
metadata *and* data) and must count once. Group cardinality ≤ `distinct fer_keys × 5` — at the upper end
10k catalogue FERs plus a free-text tail, so ~60k groups; `ORDER BY` on an aggregate materialises them all,
so the cost is the scan (2.05M rows) plus a 60k-row sort. **T2 at the upper end**; the snapshot stores the
top 1000 groups per `(status, catalogued)` combination plus a `"truncated": true` marker and the true group
count, and `offset` beyond the stored top-1000 forces a live recompute (or `202` above `SYNC_MAX_CELLS`).

Labels are **not** in the aggregate: the handler takes the ≤200 returned `fer_id`s and issues **one**
`SELECT … FROM fers WHERE id IN (…)` for labels/types — one extra query, constant, never N+1. Free-text rows
carry the *first* raw text seen, fetched with one extra bounded query over `fip_declarations` joined to
`fips` for display only, capped at the page size; when the population is above T1 the snapshot carries the
labels already resolved.

Response `data`: `{"rows":[{"ferKey","ferId","label","ferType","status","fips","declarations","share","areas":[{"areaKey","fips"}]}],"total":60214,"truncated":false}`.
`areas` is included only for `groupBy=area` (a second, symmetric `GROUP BY` adding `f.area_key` via a join to
`fip_facets`, still one statement).

### 3.3 Similarity and convergence — `GET /api/dashboard/similarity/*`

Four endpoints; §4 specifies the algorithms and their costs.

| endpoint | params | response |
|---|---|---|
| `…/pair?a=&b=&weighting=` | two FIP ids, both must be `readable_individually` | the full per-question/per-principle breakdown |
| `…/neighbours?fip=&population=&limit=&weighting=&minSimilarity=` | `limit` default 20, max 100 | ranked neighbours with per-principle scores |
| `…/clusters?population=&minSimilarity=&limit=` | `limit` default 50, max 200 | clusters with size, representative, mean intra-similarity |
| `…/map?population=&buckets=&weighting=` | `buckets` default 10, max 20 | server-bucketed distribution, never per-FIP |

Convergence per question — the matrix's own aggregate, generalised to a population — is folded into
`…/map`'s response as `convergence`, because it is the same single `GROUP BY` and the room already knows the
number:

```sql
SELECT d.question_id, COUNT(DISTINCT d.fer_key) AS distinct_current,
       COUNT(DISTINCT d.fip_id) AS declaring_fips
FROM fip_declarations d
WHERE d.fip_id IN (SELECT fip_id FROM pop) AND d.status = 'current'
GROUP BY d.question_id
```

plus a second bounded statement for each question's top key (`GROUP BY question_id, fer_key ORDER BY
COUNT(*) DESC`, then top-1 per question in Python over ≤ questions × 200 rows). Two statements, constant,
`agreed = declaring_fips >= 2 AND distinct_current = 1` — the *identical* rule as `matrix.ts`, so the
dashboard and the session matrix cannot disagree.

#### 3.3.1 `…/map` — the normative `data` shape

Added 11 Sep 2026 (§11.3). The wire contract below is **authoritative**: it is transcribed from
`frontend/src/types/dashboard.ts` (`MapData` and the interfaces it names), which the frontend builder had to
infer from §4.4's prose. Backend and frontend now both conform to *this* block; a change to it is a change to
both.

```json
{"histogram": [{"bucket": 0, "from": 0.0, "to": 0.1, "count": 18342},
               {"bucket": 9, "from": 0.9, "to": 1.0, "count": 210}],
 "principleBuckets": {"F1": [4, 9, 22, 40, 61, 88, 120, 90, 40, 12], "A1.1": […]},
 "convergence": [{"questionId": "F1-metadata", "declaringFips": 8120, "distinctCurrent": 37,
                  "topKey": "https://orcid.org/", "topLabel": "ORCID", "topCount": 5140,
                  "agreed": false, "notApplicableFips": 95}],
 "topClusters": [{"id": "c7", "size": 214,
                  "representative": {"fipId": "f_abc", "label": "PARC Toxicology"},
                  "meanSimilarity": 0.78, "principles": ["F1", "F2", "I2"],
                  "members": [{"fipId": "f_abc", "label": "PARC Toxicology"}]}],
 "hotBuckets": [{"size": 30142, "representativeFipId": "f_xyz", "meanSimilarityEstimate": 0.94}],
 "scatterAvailable": true,
 "nodes": [{"id": "f_abc", "label": "PARC Toxicology", "clusterId": "c7"}],
 "edges": [{"a": "f_abc", "b": "f_def", "similarity": 0.71}],
 "edgesTruncated": false}
```

Field notes, and the two places the inferred shape needed correcting:

- `histogram` is exactly `buckets` entries (default 10, max 20), `bucket` being the 0-based index and
  `from`/`to` the half-open similarity range — counts of **pairs**, not FIPs, over the same candidate set the
  clustering used. Above `EXACT_PAIRS_MAX_FIPS` it is therefore a distribution over LSH candidate pairs, not
  over all pairs; that is stated in the response through the envelope's `tier` and in the UI by the
  `hotBuckets` disclosure, and it is why the histogram is never labelled "all pairs".
- `principleBuckets` maps each of the 12 principle codes to an array of exactly `buckets` counts — the
  `principle × bucket` grid of §4.4, 120 numbers at the default. Keys are the codes present in the
  population's questionnaire(s), so a custom model yields its own set.
- `convergence` mirrors `matrix.ts`'s `Convergence` field for field, so the dashboard and the session matrix
  are visibly the same number. **Correction 1 (additive):** the backend also emits `notApplicableFips`,
  which `matrix.ts` has and the inferred `ConvergenceRow` omits; it is free (it is already in `fip_cells`)
  and the gaps view needs the same figure. The frontend's `ConvergenceRow` should gain
  `notApplicableFips: number`; until it does, the extra field is simply ignored and nothing breaks.
- `topClusters` reuses the `clusters` view's row shape unchanged, capped at 20 entries here (the full list
  is `…/clusters`), and `members` is capped at 10 per cluster and filtered by `readable_individually`
  (§2.4) — so `members.length` may be smaller than `size`, which is not a bug and the UI must not present
  it as one.
- `scatterAvailable` is `fipCount ≤ FIPM_DASHBOARD_LIVE_MAX_FIPS_SCATTER` (default 300); `nodes` and `edges`
  are present **only** when it is true.
- **Correction 2 (the frontend must be corrected):** `edges` as inferred is unbounded, and it cannot be
  produced efficiently as such — 300 FIPs admit 44 850 pairs, and serialising them would be a ~2 MB payload
  for a view whose whole premise (§6.2) is that no response is proportional to the population. The contract
  is therefore: `edges` carries **only** pairs with `similarity ≥ FIPM_DASHBOARD_CLUSTER_MIN_SIM`, ordered
  by `similarity DESC`, capped at `FIPM_DASHBOARD_MAP_EDGE_CAP` (**new setting, default 5000**), with a
  sibling boolean **`edgesTruncated`** saying whether the cap bit. `MapData` must gain
  `edgesTruncated: boolean` and the scatter must render the disclosure when it is true, per AC 6 of brief C
  (“a number the server says is approximate must never be shown as exact”).
- **Correction 3 (additive):** `MapNode` gains `clusterId: string | null` — without it the scatter cannot
  colour by cluster without re-deriving components from `edges` in the browser, which is the O(n²)-adjacent
  work this design pushes to the server. It is one column from the clustering that already ran.

`FIPM_DASHBOARD_MAP_EDGE_CAP = 5000` joins the §7.5 settings list.

### 3.4 Gaps and coherence — `GET /api/dashboard/gaps`

Params: `minShare` (default 0, filter rows in Python after the aggregate), `limit` (default 100, max 500),
`offset`.

**There is no `groupBy` on this view** (amended 11 Sep 2026, §11.2). Gaps rows are **always per-question**.
Two reasons, both decisive: the response is already bounded by the questionnaire (21 rows for the GO FAIR
model), so a rollup saves nothing; and `coherence_flags` and `type_mismatches` (spec 12 §A3/§A2) have no
meaning summed across a rolled-up group — a coherence rule fires on a *pair* of questions, so adding the
flag counts of F1-metadata and F1-data would double-count the rule that relates them, and "3 mismatches on
F1" would be a number nobody can act on. A consumer that wants a per-principle gap picture rolls up the
per-question rows itself, choosing its own rule for the flag columns. An unknown query parameter is ignored
(FastAPI's default), so a client still sending a vestigial `groupBy=question` is harmless and should drop
it.

**One `GROUP BY`, index-only:**

```sql
SELECT c.question_id, c.question_index, c.sub_principle, c.principle_group, c.fer_type,
       COUNT(*) AS fips,
       SUM(CASE WHEN c.cell_state = 'unanswered'     THEN 1 ELSE 0 END) AS unanswered,
       SUM(CASE WHEN c.cell_state = 'none'           THEN 1 ELSE 0 END) AS none_only,
       SUM(CASE WHEN c.cell_state = 'not-applicable' THEN 1 ELSE 0 END) AS not_applicable,
       SUM(CASE WHEN c.cell_state = 'planned'        THEN 1 ELSE 0 END) AS planned_only,
       SUM(c.coherence_flags)                                            AS coherence_flags,
       SUM(CASE WHEN c.type_mismatch_ack THEN 1 ELSE 0 END)              AS type_mismatches
FROM fip_cells c
WHERE c.fip_id IN (SELECT fip_id FROM pop)
GROUP BY c.question_id, c.question_index, c.sub_principle, c.principle_group, c.fer_type
```

`SUM(CASE …)` is a portable aggregate, not per-row Python. Cardinality = questions. Same cost curve as
coverage. `coherence_flags`/`type_mismatches` are 0 until spec 12 §A2/§A3 land; the response always carries
them and the frontend hides the columns when the totals are 0, so those features need **no** dashboard change
when they arrive.

Response `data`:

```json
{"rows": [{"questionId": "F1-metadata", "questionIndex": 0,
           "subPrinciple": "F1", "principleGroup": "F", "ferType": "identifier-service",
           "fips": 9412, "unanswered": 1163, "noneOnly": 240, "notApplicable": 95,
           "plannedOnly": 812, "coherenceFlags": 0, "typeMismatches": 0}],
 "total": 21, "truncated": false}
```

`total` is the question count of the population's questionnaire(s), `truncated` is true when `limit` cut the
list. Rows are in `questionIndex` order — the matrix's row order.

### 3.5 Evolution — `GET /api/dashboard/evolution`

Params: `groupBy=question|subPrinciple` (default `subPrinciple`), `limit` (default 100, max 500), `offset`.

Two statements, both single `GROUP BY`s:

```sql
-- (a) what is planned, and the successor pairs
SELECT d.sub_principle, d.question_id, d.status, d.fer_key, d.successor_fer_key,
       COUNT(DISTINCT d.fip_id) AS fips
FROM fip_declarations d
WHERE d.fip_id IN (SELECT fip_id FROM pop)
  AND d.status IN ('planned', 'planned-development', 'planned-replacement')
GROUP BY d.sub_principle, d.question_id, d.status, d.fer_key, d.successor_fer_key
ORDER BY fips DESC LIMIT :limit OFFSET :offset

-- (b) migration history, from the flattened facets, never from fips.migrated_from JSON
SELECT ff.questionnaire_id, ff.questionnaire_version,
       ff.migrated_from_id, ff.migrated_from_version, COUNT(*) AS fips
FROM fip_facets ff WHERE ff.fip_id IN (SELECT fip_id FROM pop)
GROUP BY 1, 2, 3, 4
```

(b)'s cardinality is bounded by knowledge-model versions squared in the worst case; at the 1k-version design
point that is bounded further by `LIMIT 500` plus a `"truncated"` marker, and in practice by how many version
pairs actually exist. Cost of (a): the `planned*` slice is ~10–15% of declarations, ~300k rows at the upper
end behind `ix_decl_status_ferkey_fip` → ~120 ms; T1 covers it to a higher FIP count than coverage does.
Multi-version FIPs (spec 12 §C2's "FIPs with several versions") are the `migrated_from` chain; a per-FIP
version timeline is **not** a population view — it is the existing FIP read page, and the dashboard links to
it rather than aggregating it.

### 3.6 CSV per view

`GET /api/dashboard/{view}.csv` with identical parameters, `StreamingResponse`, `Content-Disposition:
attachment; filename="{view}-{population_hash[:8]}.csv"`, UTF-8 with BOM (matching the existing session CSV
export), one header row, then the aggregate rows — **the same aggregate statement**, iterated with
`yield_per(1000)` and never buffered. `limit` defaults to *unbounded* for CSV, capped at
`FIPM_DASHBOARD_CSV_MAX_ROWS` (default 100 000) with a final `# truncated` comment line if hit. Snapshot
tiers serve CSV from the snapshot payload.

`groupBy` reaches CSV unchanged, and is the reason the server-side rollup of §3.1 exists at all: a CSV
consumer has no client to fold rows for it.

### 3.7 FIP lookup — `GET /api/dashboard/fips`

Added 11 Sep 2026 (§11.4). §6.2 requires a typeahead over the population's readable FIPs so a participant can
pick "my FIP" for the neighbours panel; §3 never defined it. Specified here, and being implemented in brief B
alongside the similarity views.

```
GET /api/dashboard/fips?population=<hash|inline>&q=<text>&limit=20&offset=0
```

- `q` is optional; matched case-insensitively over the NFC-normalised, whitespace-collapsed, casefolded FIP
  label (`fips.title`, falling back to `community.name`, falling back to the id) as a **substring**, in SQL,
  never interpolated — the same discipline as spec 11 §3.2's `q`. An empty `q` lists the population's FIPs
  in `updated_at DESC` order, which is what the panel shows before the user types.
- `limit` default 20, **max 20** — this is a picker, not a listing, and capping it at the same number the UI
  shows keeps it from becoming an enumeration endpoint. `offset` default 0, max 200.
- Authorization: **identical to every other view**. The population resolves through §2.2's security
  predicate, and the result is then filtered a second time through `readable_individually` (§2.4), because
  this endpoint *names* FIPs. A FIP in the population that the viewer cannot open individually never appears
  — the same rule the neighbours, clusters and evolution views obey.
- **k-anonymity does not apply** and must not be applied: §2.4's threshold protects *aggregates* from
  inferring a single FIP, whereas every row here is a FIP the viewer may already fetch by id from
  `GET /api/fips/{id}`. Returning `403 population_too_small` on a 3-FIP session would break exactly the
  workshop case §2.4 was written to preserve. `total` is the count **after** the readability filter, so it
  discloses nothing the rows do not.
- `503 dashboard_disabled`, `400 invalid_population` and `409 projection_stale` behave as elsewhere;
  `projection_stale` in fact cannot fire, since this endpoint reads `fips` and `fip_facets` only, never the
  cell/declaration projection.

Response — a **plain list, deliberately not the §3 envelope** (there is no aggregate, no tier, no snapshot
and no ETag to negotiate; wrapping it would invite a client to cache a picker):

```json
{"items": [{"fipId": "f_abc", "label": "PARC Toxicology", "areaKey": "gofair-fip-mini@2.0.0",
            "answeredQuestions": 19, "questionCount": 21, "updatedAt": "2026-09-11T10:00:00Z"}],
 "total": 3, "truncated": false}
```

Cost: one statement, index-only on §2.2's covering indexes plus `fip_facets` for the two counts, bounded by
`LIMIT 20` at every scale. `Cache-Control: no-store`.

## 4. Similarity at scale

### 4.1 The measure, and its default weighting

For FIPs *a*, *b* and a question *q* present in both FIPs' questionnaires:

- `S_a(q)` = the set of `fer_key`s of *a*'s **`current`** declarations on *q*; plus the sentinel `NA` when
  `a`'s cell is `not-applicable`. (Only `current` — "similarity" in the FIP programme means "uses the same
  thing today"; `planned` belongs to the evolution view. A parameter `statuses=current|currentPlanned` is
  provided and defaults to `current`.)
- If `S_a(q)` and `S_b(q)` are both empty, *q* is **excluded** (two blanks are not agreement).
- Otherwise `J(q) = |S_a ∩ S_b| / |S_a ∪ S_b|` — plain Jaccard over the convergence key of §1.5.

Per principle code *p* (the 12 codes `F1…R1.2` carried by `question.principle`): `J(p) = mean of J(q)` over
included *q* with `sub_principle = p`. Overall:

- **`weighting=principle` (DEFAULT)** — mean of `J(p)` over principle codes with ≥1 included question.
- `weighting=question` — mean of `J(q)` over all included questions.
- `weighting=letter` — mean over F/A/I/R of the mean of their principle codes.

**Assumption A1 (to confirm with the lead — spec 12 §E.3's open question).** Equal weight per principle code
is the default. The argument: `weighting=question` makes F worth 6/21 and R worth 4/21 of the score purely
because the GO FAIR model splits some questions metadata/data, which is a questionnaire-construction artefact,
not a statement about FAIR. Equal weight per principle code makes F3 (one question) count as much as R1.1
(two), which matches how the principles are discussed in the room. `letter` is the third reading and is one
parameter away. The parameter is echoed in the response and in the ETag, so a change of mind is a query-string
change, not a recompute of stored data.

**Assumption A2.** `not-applicable` on both sides scores 1.0 for that question (they agree the question does
not apply to them); one side `not-applicable` and the other declaring scores 0.0. Implemented by the `NA`
sentinel, so it needs no special case in the scoring loop.

### 4.2 Tokens and signatures

The similarity **token set** of a FIP is
`{ question_id + "\x1f" + fer_key }` over its `current` declarations, plus `question_id + "\x1fNA"` for each
`not-applicable` cell. Size ≈ 20–30 tokens. Token-set Jaccard is *not* the §4.1 measure (it is the
`weighting=question` measure with a different denominator), and that is fine, because **MinHash/LSH is used
only to generate candidates; every score a user ever sees is the exact §4.1 measure recomputed over the
candidate's stored declarations.** This is the single most important invariant of §4 and it is asserted by
AC-24.

```
fip_signatures(fip_id TEXT PK, token_count INT, k INT, bands INT, rows_per_band INT,
               signature BLOB,          -- K big-endian uint32, K*4 = 512 bytes at K=128
               computed_at DATETIME)
fip_signature_bands(fip_id TEXT, band_index INT, band_hash BIGINT,
                    PRIMARY KEY (fip_id, band_index))
  ix_bands_bucket (band_index, band_hash, fip_id)   -- the LSH bucket scan, covering
```

Parameters, all configurable, defaults chosen below:

```
FIPM_DASHBOARD_LSH_K      = 128   -- hash functions
FIPM_DASHBOARD_LSH_BANDS  = 32
FIPM_DASHBOARD_LSH_ROWS   = 4     -- BANDS * ROWS must equal K; checked at startup
```

Detection probability of a pair at token-Jaccard *J* is `1 - (1 - J^r)^b`:

| J | 0.2 | 0.3 | 0.42 | 0.5 | 0.6 | 0.8 |
|---|---|---|---|---|---|---|
| P(candidate) | 0.05 | 0.24 | 0.63 | 0.87 | 0.99 | 1.00 |

So: **recall ≥ 0.99 for genuinely similar pairs (J ≥ 0.6), ~5% wasted candidates at J ≤ 0.2**, and the band
threshold `(1/b)^(1/r) = 0.42` sits just under the 0.5–0.6 region a facilitator would call "similar". The
trade-off, stated plainly: pairs in the 0.3–0.5 band are found about a quarter to seven-eighths of the time,
so the *clustering* view is approximate by construction at the upper scale point; `…/neighbours` for one FIP
is **not** approximate — it uses the exact inverted index (§4.3), which is why "communities closest to yours",
the question a participant actually asks, is answered exactly.

Hashing, **pure Python, no new dependency**: one 64-bit base hash per token,
`h0 = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")`, then K permutations
`h_i = ((a_i * h0 + b_i) % (2**61 - 1)) & 0xFFFFFFFF` with `a_i, b_i` drawn once from
`random.Random(FIPM_DASHBOARD_LSH_SEED)` and frozen as module constants (the seed is part of the ETag via
`projection_epoch`, and changing it requires a full signature rebuild — `check-declarations` detects a
mismatch via the stored `k`/`bands`/`rows_per_band`). A band hash is
`blake2b(b"".join(4-byte minhashes of the band), digest_size=8) & ((1<<62)-1)`. Cost: 27 tokens × 128
multiply-mods ≈ 3.5k integer ops ≈ 1–2 ms per FIP, inside the write hook's 10 ms budget. Full rebuild of 100k
FIPs ≈ 2–4 min, in `backfill-declarations`.

Storage at 100k FIPs: signatures ~60 MB, bands 3.2M rows ≈ 100 MB heap + 120 MB index.

### 4.3 Neighbours of one FIP — exact, via the inverted index

`GET /api/dashboard/similarity/neighbours?fip=…` in three statements, total, at any scale.

**Step 1 — the FIP's own keys and their document frequency.** `fer_key_df(question_id, fer_key, df_all INT,
df_public INT, PRIMARY KEY (question_id, fer_key))` is maintained incrementally by the projection hook
(`+1`/`-1` per key as declarations appear and disappear) and rebuilt by `backfill-declarations`. It is a
**heuristic for ordering only**; a wrong count costs candidates, never correctness.

**Step 2 — candidate generation.** Order the FIP's `(question_id, fer_key)` pairs by `df ASC` (rarest first —
a key declared by 3 FIPs is worth vastly more than one declared by 90 000) and consume keys until the
cumulative posting budget is exhausted:

```
FIPM_DASHBOARD_POSTING_BUDGET   = 20000   -- total posting rows scanned per neighbours request
FIPM_DASHBOARD_POSTING_CAP      = 2000    -- per (question_id, fer_key)
FIPM_DASHBOARD_CANDIDATE_CAP    = 200     -- candidates rescored exactly
FIPM_DASHBOARD_DF_SKIP_SHARE    = 0.20    -- skip keys held by >20% of the population…
FIPM_DASHBOARD_DF_MIN_KEYS      = 3       -- …unless fewer than 3 keys survive, then take the rarest 3 anyway
```

```sql
SELECT d.fip_id, COUNT(*) AS shared_keys
FROM fip_declarations d
WHERE d.status = 'current'
  AND (d.question_id, d.fer_key) IN :selected_keys      -- <= ~27 pairs, each a range scan on ix_decl_ferkey_q_fip
  AND d.fip_id <> :fip
  AND d.fip_id IN (SELECT fip_id FROM pop)
GROUP BY d.fip_id
ORDER BY shared_keys DESC, d.fip_id ASC
LIMIT :candidate_cap
```

With per-key `LIMIT` pushed down as a `UNION ALL` of capped subselects when any key's `df` exceeds
`POSTING_CAP`. **Cost bound: ≤ 20 000 index rows scanned + a ≤20k-row grouping, independent of population
size** → 15–40 ms at 40 FIPs and at 100k FIPs alike. This is the mechanism that makes the *participant's*
question interactive at the upper end.

**Degenerate case — the very popular FER.** DOI/ORCID/HTTPS will be declared by most of a 100k population.
Two guards, and the bias each introduces, documented:

1. `DF_SKIP_SHARE`: a key held by > 20% of the population is skipped entirely. Bias: a FIP whose *only*
   commonality with another is "we both use DOIs" is not offered as a neighbour. This is desirable — sharing
   a near-universal resource carries almost no information — but it means neighbour lists for a FIP with
   nothing but universal declarations can come back short. The response says so:
   `"candidateBudgetExhausted": bool, "skippedPopularKeys": ["…"], "keysUsed": n`.
2. `POSTING_CAP` (used only when no rarer key is available, per `DF_MIN_KEYS`): the posting list is truncated
   in `fip_id ASC` order. Bias: **lexicographic** — the alphabetically-first FIP ids are preferred. It is
   deterministic (so results are stable and cacheable) and it is disclosed in the response
   (`"postingTruncated": true`). The alternative, a random sample, trades reproducibility for fairness; we
   chose reproducibility because a facilitator projecting the same URL twice must see the same list.

**Step 3 — exact rescoring.** One statement fetches all cells and declarations for the ≤200 candidates plus
the subject FIP (`WHERE fip_id IN (…)`, ≈ 200 × 48 ≈ 9 600 rows, covering indexes), and the §4.1 measure is
computed in Python. Output is filtered through `readable_individually` (§2.4) and truncated to `limit`.

Response `data`:
```json
{"fip": {"id": "…", "label": "…"},
 "neighbours": [{"fipId": "…", "label": "…", "areaKey": "…", "similarity": 0.63,
                 "sharedKeys": 11,
                 "perPrinciple": {"F1": 1.0, "F2": 0.5, "…": 0.0},
                 "topShared": [{"questionId": "F1-metadata", "ferKey": "https://orcid.org/", "label": "ORCID"}]}],
 "weighting": "principle", "statuses": "current",
 "candidateBudgetExhausted": false, "postingTruncated": false,
 "skippedPopularKeys": ["https://doi.org/"], "keysUsed": 19, "candidatesScored": 178}
```

### 4.4 All-pairs work — clustering and the map

**Never O(n²) at request time.** Three regimes, selected by population size:

| regime | condition | method |
|---|---|---|
| **exact all-pairs** | `fipCount ≤ FIPM_DASHBOARD_EXACT_PAIRS_MAX_FIPS` (default 300) | every pair scored exactly: 300² / 2 = 45k pairs × ~25 questions ≈ 1.1M set operations ≈ 0.4–1.2 s → computed once and **snapshotted**, or live under 100 FIPs (4 950 pairs, ~40 ms). **This is the CONFOA path: 40 FIPs = 780 pairs, ~8 ms, fully exact, LSH never runs.** |
| **LSH candidates** | above 300 | band-bucket self-join → candidate pairs → exact rescoring of candidates only |
| **refuse** | candidate pairs would exceed `PAIR_CAP` even after bucket capping | `413 similarity_population_too_large` naming the cap and suggesting a narrower population |

LSH candidate pairs, one statement:

```sql
SELECT a.fip_id AS a_id, b.fip_id AS b_id, COUNT(*) AS bands_shared
FROM fip_signature_bands a
JOIN fip_signature_bands b
  ON b.band_index = a.band_index AND b.band_hash = a.band_hash AND b.fip_id > a.fip_id
WHERE a.fip_id IN (SELECT fip_id FROM pop)
  AND b.fip_id IN (SELECT fip_id FROM pop)
  AND a.band_hash NOT IN (SELECT band_hash FROM lsh_hot_buckets WHERE band_index = a.band_index)
GROUP BY a.fip_id, b.fip_id
HAVING COUNT(*) >= :min_bands          -- default 1
LIMIT :pair_cap
```

```
FIPM_DASHBOARD_LSH_BUCKET_MAX = 500     -- a band bucket bigger than this is "hot"
FIPM_DASHBOARD_LSH_PAIR_CAP   = 200000
FIPM_DASHBOARD_CLUSTER_MIN_SIM = 0.6
```

**The blow-up this guard exists for:** a band bucket holding *m* FIPs emits *m(m−1)/2* pairs. 30 000 FIPs
with identical declarations (entirely plausible — a national mandate, or a template) would emit 450 million
pairs from one bucket. So `lsh_hot_buckets(band_index, band_hash, member_count, representative_fip_id,
computed_at)` is maintained by the refresh job: any bucket over `LSH_BUCKET_MAX` is recorded there, excluded
from the pair join, and surfaced instead as **one pre-formed cluster** — which is what it is, since its
members collide on 4 consecutive minhashes and are by construction near-identical. Bias, documented in the
response: within a hot bucket, no pairwise structure is reported, only the group and a representative;
`"hotBuckets": [{"size": 30142, "representativeFipId": "…", "meanSimilarityEstimate": 0.94}]` with the
estimate computed from a random sample of 200 members of that bucket, exactly scored.

**Clustering** runs over the candidate graph, not the complete graph: exactly rescore up to `PAIR_CAP`
candidate pairs (in batches of 5 000, one statement per batch fetching both sides' rows — constant query
count per batch, not per pair), keep edges with `similarity ≥ CLUSTER_MIN_SIM`, then **union–find** (pure
Python, `O(E α(n))`) for connected components. Single-linkage semantics, stated so nobody expects
hierarchical dendrograms: spec 12 §C2 asked for "a simple clustering (hierarchical, no external
dependency)"; single-link connected components over a thresholded graph *is* the first level of single-link
hierarchical clustering, and offering the threshold as a parameter gives the same navigational value without
holding an O(n²) distance matrix. **D6** records that choice and the rejection of true hierarchical
clustering (which needs the full matrix and is therefore out at 100k).

Per cluster: size, representative (highest mean similarity to the rest of a ≤50-member sample), mean intra
similarity, the principle codes that hold it together (mean `J(p)` across sampled intra-cluster pairs), and
up to 10 named members filtered by `readable_individually`. Output is a **snapshot**, view `clusters`, never
computed inside a request above the exact-pairs threshold.

**The map**, for the "similarity map" of spec 12 §C2 at 10k FIPs: `…/map` returns **server-bucketed
distributions only** — a histogram of pair similarity in `buckets` bins, a `principle × bucket` grid
(12 × 10 = 120 numbers), the convergence table of §3.3, and the top clusters by size. Total payload ≈ 30 kB
regardless of population. A per-FIP scatter/force layout is offered **only** when
`fipCount ≤ FIPM_DASHBOARD_LIVE_MAX_FIPS_SCATTER` (default 300), as `{"nodes":[…],"edges":[…]}`; above that
the frontend renders the buckets and the cluster list (§6.3).

### 4.5 Dependencies

**No new dependency.** Everything in §4 is `hashlib.blake2b`, Python `int` arithmetic, `array`/`bytes`, and
`random.Random` with a fixed seed. `numpy`/`scipy`/`sklearn` are **not** in `backend/pyproject.toml` (checked:
the runtime list is fastapi, uvicorn, sqlalchemy, pydantic, pydantic-settings, argon2-cffi, python-multipart,
rdflib, qrcode, httpx) and **must not be added** — they would triple the Docker image for arithmetic the
interpreter does in single-digit milliseconds per FIP, and the projection's per-write budget (§1.6) does not
need vectorisation for 27 tokens. If a future profile shows minhashing to be the bottleneck of a full
rebuild, the fix is `--jobs N` over a FIP-id range in the CLI (embarrassingly parallel, no shared state),
not numpy. **D7.**

## 5. Caching, snapshots, and the network population

### 5.1 `dashboard_snapshots`

```
dashboard_snapshots
  population_hash      TEXT NOT NULL   -- PK part 1 (§2.3, already includes auth_scope)
  view                 TEXT NOT NULL   -- PK part 2: coverage|adoption|gaps|evolution|clusters|map|convergence
  params_hash          TEXT NOT NULL   -- PK part 3: sha256 of the canonical view params (weighting, status, groupBy, …)
  status               TEXT NOT NULL   -- 'fresh' | 'computing' | 'failed'
  payload              JSON NULL       -- the `data` object of §3's envelope, verbatim
  payload_bytes        INT  NOT NULL
  etag                 TEXT NOT NULL
  fip_count            INT  NOT NULL
  source_max_updated_at DATETIME NULL  -- MAX(fips.updated_at) over the population at compute time
  projection_epoch     INT  NOT NULL
  computed_at          DATETIME NOT NULL
  expires_at           DATETIME NOT NULL
  duration_ms          INT  NOT NULL
  error               TEXT NULL
  PRIMARY KEY (population_hash, view, params_hash)
  ix_snap_expires (expires_at)
```

`FIPM_DASHBOARD_SNAPSHOT_TTL_SECONDS` default 3600. `FIPM_DASHBOARD_SNAPSHOT_MAX_BYTES` default 4 MiB — a
payload over the cap is trimmed to its top-N rows with `"truncated": true` rather than stored oversized.

### 5.2 Which views are live, which snapshot

| view | T1 live | T2 snapshot | note |
|---|---|---|---|
| coverage | ≤250k cells (~12k FIPs) | above | always live at CONFOA |
| gaps | ≤250k cells | above | same query shape as coverage |
| adoption | ≤250k cells | above | snapshot stores top 1000 groups |
| evolution | ≤250k cells | above | the `planned*` slice is ~8× cheaper, so T1 reaches further |
| convergence | ≤250k cells | above | folded into `map` |
| similarity/pair | **always live** | never | two FIPs, ~100 rows |
| similarity/neighbours | **always live** | never | §4.3's budget is population-independent |
| similarity/map | ≤300 FIPs | above | scatter only under 300 |
| similarity/clusters | ≤300 FIPs (exact) | above (LSH) | never computed in-request above 300 |

### 5.3 Freshness, invalidation, refresh

A snapshot is **stale** if any of: `expires_at < now`; `projection_epoch != dashboard_meta['projection_epoch']`;
`fip_count != ` the population's current count; `source_max_updated_at != ` the population's current
`MAX(fips.updated_at)`. Those last two come from **one** extra index-only statement over the population CTE
(`SELECT COUNT(*), MAX(updated_at) FROM pop`) — ~10–25 ms at 100k, and it is the same statement the ETag
needs, so it is computed once per request.

```
POST /api/dashboard/refresh   body {"population": "<hash|inline>", "views": ["coverage","clusters"], "force": false}
```
Owner of the population, or admin. Sets each target row to `status='computing'` (a second concurrent refresh
gets `409 refresh_in_progress`), computes, writes. Synchronous when the estimated cost (cells + declaration
rows + candidate pairs) is under `FIPM_DASHBOARD_SYNC_MAX_CELLS` (default 600 000); otherwise it runs in a
`BackgroundTasks` worker and the endpoint returns `202 {"status":"computing","retryAfter":15}`. A `GET` on a
view whose snapshot is `computing` returns `202 snapshot_pending` with `Retry-After`, plus the stale payload
under `"stalePayload"` and `"degraded": true` when one exists — a projected dashboard degrades to last
hour's numbers with a visible timestamp, never to a spinner.

```
python -m fipm refresh-dashboard [--population HASH|--all-saved] [--views a,b] [--force] [--json]
```
is the cron entry point (`*/15` at 2027 scale, for the handful of `auth_scope='pub'` populations). It also
drains expired rows (`DELETE … WHERE expires_at < now - 7 days`).

### 5.4 The network population: ingested facts, never a live fetch

Spec 11's proxy is a **process-local, 15-minute, 256-entry LRU with no DB table** and network FIPs live in no
table at all unless someone runs `POST /api/fips/from-network`. Aggregating over it live would mean up to 3
upstream SPARQL calls per community per view — for 80 communities, minutes, and at 2027 scale unbounded.
**D8: the dashboard never calls the network.** Instead:

```
python -m fipm ingest-network-fips [--limit N] [--community IRI] [--since ISO8601] [--json]
network_fips(fip_id TEXT PK,            -- 'net:' + sha256(community_iri)[:22]; NOT a fips.id
             community_iri TEXT NOT NULL UNIQUE, label TEXT, fip_nanopub_iri TEXT,
             index_iri TEXT, created TEXT, fetched_at DATETIME NOT NULL,
             questionnaire_id TEXT, questionnaire_version TEXT)
```

The command walks `fipm.network.get_fip_communities()` then `get_community_fip()` per community, maps each
declaration through the existing `rdf.question_id_from_individual` + `fer_types` inversion (spec 11 §3.3 —
reused, not reimplemented), and writes **read-only shadow rows** into `fip_facets` / `fip_cells` /
`fip_declarations` / `fip_signatures` / `fip_signature_bands` with `source='network'`. Consequences, all
deliberate:

- network shadow rows have **no** `fips` row, so they cannot be edited, exported to RDF, claimed, or confused
  with a local FIP; `check-declarations` invariant 2 exempts exactly `source='network'`.
- they are excluded from every population unless the spec contains `{"kind":"network"}`; `visibility` does
  not apply to them (they are public nanopublications by construction) and the §2.2 predicate reaches them
  through the `UNION ALL` branch only.
- `unmapped` declarations (spec 11 §3.3's non-mini questions) are **dropped** from the projection — they have
  no `question_id` in our vocabulary — and counted in the command's report so the drop is visible.
- similarity across the local/network boundary works unchanged, because both sides share the convergence key
  of §1.5. This is what makes "distance to a chosen reference FIP … a network FIP from the same domain"
  (spec 12 §C2) a two-parameter query rather than a feature.
- freshness: `network_fips.fetched_at` feeds the population's `source_max_updated_at`, so a re-ingest
  invalidates the snapshots that include the network. `GET /api/dashboard/populations` reports
  `networkIngestedAt`, and the frontend shows it next to any network-bearing view.

At 80 communities the command takes ~2–4 minutes (3 upstream calls each, 10 s timeout) and is a cron job, not
a request path. At 2027 scale it is `--since`-incremental.

## 6. Frontend contract

Desktop-first, and deliberately the **matrix's own layout**: sticky first column, one row per question grouped
by principle, the same `--color-status-*` variables and the same legend vocabulary, so the room recognises
what it is looking at (spec 12 §C3).

### 6.1 Routes, and URL-addressable populations

| route | view |
|---|---|
| `/dashboard?pop=…` | overview: population picker + the headline numbers of all five views |
| `/dashboard/coverage?pop=…&groupBy=…&scope=…` | §3.1 |
| `/dashboard/adoption?pop=…&status=…&catalogued=…&page=…` | §3.2 |
| `/dashboard/similarity?pop=…&fip=…&weighting=…` | §3.3, three panels |
| `/dashboard/gaps?pop=…` | §3.4 |
| `/dashboard/evolution?pop=…` | §3.5 |

**Every** view's complete state lives in the query string — population, grouping, filters, weighting, page —
so a facilitator projects a URL, pastes it into chat, and everyone sees the same numbers. `pop=session:<id>`,
`pop=public`, `pop=network` are the three shorthands a human types; `pop=<hash>` is what "Save this
population" produces (`POST /api/dashboard/populations` → replace the query param with the hash). A stored
population's label is shown in the header with its `fipCount` and `computedAt`, and a `tier: "snapshot"`
response renders a visible *"computed {time} ago · Refresh"* control (which `POST`s to `/refresh`).

### 6.2 Rendering 10k FIPs without shipping 10k rows

The load-bearing point: **no dashboard response is proportional to the population.** Concretely:

- **Coverage heat map** — rows are the 12 principle codes (or 21 questions), columns are the six
  `cell_state`s. The cell is a share, rendered as a diverging fill plus the number, because colour is never
  the only signal (spec 02 §4.3). That is ≤126 numbers whether the population is 40 FIPs or 100 000. There is
  no per-FIP column, ever — the per-FIP matrix is the session matrix, and it stays where it is.
- **Adoption** — server-paginated table, 50 rows a page, server-sorted; a "long tail" tab is
  `catalogued=exclude`, same pagination.
- **Similarity** — three panels: (a) *Neighbours* — pick a FIP via `GET /api/dashboard/fips` (§3.7: the
  typeahead over the population's readable FIPs, server-side `q`, debounced 300 ms, at most 20 suggestions),
  then get ≤100 rows from `…/neighbours`; (b) *Distribution* — the histogram and the
  `principle × bucket` grid from `…/map`, ≤130 numbers; (c) *Clusters* — ≤200 cluster cards with size,
  representative and the principles that bind them, expandable to ≤10 named members. The force-directed
  scatter appears only when the server says `"scatterAvailable": true` (≤300 FIPs) — at 10k the panel shows
  the distribution and the clusters instead, with a one-line explanation of why, not a broken canvas.
- **Gaps / evolution** — question-indexed tables, ≤500 rows, one page.

No SSE, no websockets, no streaming JSON: the responses are small by construction. The only asynchrony is the
`202 snapshot_pending` poll — one `setTimeout` at `Retry-After`, max 20 attempts, with the stale payload
rendered underneath and dimmed while it waits.

### 6.3 Components, print, CSV, i18n

- `views/DashboardHome.vue`, `DashboardCoverage.vue`, `DashboardAdoption.vue`, `DashboardSimilarity.vue`,
  `DashboardGaps.vue`, `DashboardEvolution.vue`.
- `components/PopulationPicker.vue` (the six term kinds, a date range, save/share), `CoverageHeatMap.vue`,
  `PrincipleRow.vue` (shared with nothing — but it reuses `matrix.ts`'s `principleGroup` convention),
  `SimilarityHistogram.vue`, `ClusterCard.vue`, `NeighbourList.vue`, `DashboardLegend.vue`,
  `SnapshotBanner.vue`, `DegradedBanner.vue`.
- `lib/dashboard.ts` — pure, unit-tested: parse/serialise a population spec to and from the query string,
  roll `coverage.rows` up between grouping levels client-side (the response already carries every level's
  key, so a grouping change is **no refetch**, exactly as the matrix's language switch is no refetch),
  format shares.
- `api/dashboard.ts` — one function per endpoint, `If-None-Match` passed through so a `304` reuses the cached
  body.
- `assets/print-dashboard.css` — `@page { size: A3 landscape; margin: 10mm }`, same hide-list as
  `print-matrix.css`, target: coverage on one A3 sheet.
- CSV: a plain `<a :href>` per view to `/api/dashboard/{view}.csv?…` (no fetch-then-blob, so
  `Content-Disposition` is honoured) — the same pattern as `ExportButtons.vue`.
- i18n: builder adds **en only**, all keys under `dashboard.*`, and lists them for the translator. No
  hard-coded English outside `data/i18n/en.json`. No new npm dependency.

## 7. Migration and rollout

### 7.1 Schema

`SCHEMA_VERSION` **7 → 8**. Eleven new tables, all created by `Base.metadata.create_all()`:
`fip_facets`, `fip_cells`, `fip_declarations`, `fer_key_df`, `fip_signatures`, `fip_signature_bands`,
`lsh_hot_buckets`, `network_fips`, `dashboard_populations`, `dashboard_snapshots`, `dashboard_meta`
— six for the projection (§1.2–§1.4, §4.2, plus `fer_key_df`), one for hot buckets, one for network
shadow identity, and three for the dashboard itself (`dashboard_populations`, `dashboard_snapshots`,
`dashboard_meta`). **No column is added to any existing table**, so
`_EXPECTED_COLUMNS` is unchanged. The one new mechanism is `_ensure_indexes()` (§1.9) for the four covering
indexes on the pre-existing `fips` table. An existing v7 database upgrades in place: new tables appear empty,
the four indexes are created, `schema_version` becomes 8, and the projection is empty until backfilled
(§1.8's `409 projection_missing`, or the startup rule below).

Postgres: still no Alembic (PLAN §1's v1 decision stands). This spec adds nothing that makes the eventual
Alembic adoption harder — every table is new and every index is declarative — and `_ensure_indexes()` is
explicitly SQLite-shaped (`CREATE INDEX IF NOT EXISTS`, which Postgres also supports) so it survives the
move. Recorded as **Q5**.

### 7.2 Backfill: startup vs CLI

```
FIPM_DASHBOARD_BACKFILL_ON_STARTUP          = true    -- but see the cap
FIPM_DASHBOARD_STARTUP_BACKFILL_MAX_FIPS    = 500
```

At startup, after `init_db()` and the existing `run_import()`: count FIPs needing projection (§1.7's
`--only-stale` predicate). If 0, nothing. If ≤ 500, backfill inline and log the count and duration (500 × 2.5
ms ≈ 1.3 s — invisible, and it means the **workshop laptop never needs a CLI step**). If > 500, log one
`WARNING` naming `python -m fipm backfill-declarations --only-stale` and leave the projection stale; the
endpoints then behave per §1.8. Never block a 100k-row startup on a 4-minute backfill.

### 7.3 Feature flag

```
FIPM_DASHBOARD_ENABLED = true
```

`false` → all `/api/dashboard/*` return `503 {"detail":"dashboard_disabled"}`, `GET /api/health` reports
`dashboardEnabled: false`, the frontend hides the nav entry, **and the projection write hook is a no-op** (so
the flag is a genuine kill switch for the write-path cost, not just a UI toggle). Turning it back on leaves a
stale projection, handled by §7.2's startup rule at ≤500 FIPs and by the CLI above it — a test asserts that
round trip.

Recommendation: ship `true`. The write-path cost is < 10 ms per FIP write (AC-14) and the facilitator gets
coverage and exact similarity live during the session. The flag exists for the dry run: if it shows any
regression on a phone-side `PATCH`, set `FIPM_DASHBOARD_ENABLED=false` in the CONFOA `.env` and the workshop
proceeds exactly as it does today.

### 7.4 What 6 Oct uses, and what 2027 turns on

**CONFOA, 6 Oct 2026 — 1 session, ~40 FIPs, 138 FERs.** Everything live, nothing snapshotted, no cron, no
LSH:

- coverage / gaps / adoption / evolution: 840 cell rows, 700 declaration rows → single-digit milliseconds.
- similarity: 40 FIPs is below `EXACT_PAIRS_MAX_FIPS`, so clusters and the map are **exact all-pairs** (780
  pairs, ~8 ms) and the scatter renders. MinHash signatures are still written (they are 1–2 ms and keep the
  write path uniform) but **the LSH query never runs** — which is exactly why AC-25 asserts the LSH path's
  output against the exact path's on a 300-FIP fixture: the code that will not run in the room is the code
  that needs the strongest test.
- population: one shorthand, `pop=session:<id>`, reachable from a button on the session matrix. Network
  population optional (`ingest-network-fips` once before the workshop gives the ~80 communities as a
  comparison population, which is where the interesting numbers are — spec 12 §C3's own point).
- k-anonymity never binds (the facilitator can read every FIP in their own session individually).
- backfill: automatic at startup (40 ≪ 500).

**2027 scale — turn on:** `refresh-dashboard` on a 15-minute cron for the saved `auth_scope='pub'`
populations; `ingest-network-fips --since` nightly; `check-declarations --sample 1000 --json` weekly;
`backfill-declarations --only-stale` after any knowledge-model content change (the `reprojection_backlog`
makes this a no-argument command); Postgres + Alembic; and tune `LIVE_MAX_CELLS`, `POSTING_BUDGET`,
`LSH_BUCKET_MAX` from the scale test's recorded timings on the real hardware — the defaults in this spec are
chosen from the cost model in §3/§4, not measured, and §8's scale test exists to replace them with measurements.

### 7.5 The full settings list

```
FIPM_DASHBOARD_ENABLED                      = true
FIPM_DASHBOARD_MIN_POPULATION               = 5
FIPM_DASHBOARD_LIVE_MAX_CELLS               = 250000
FIPM_DASHBOARD_SYNC_MAX_CELLS               = 600000
FIPM_DASHBOARD_FALLBACK_MAX_FIPS            = 200
FIPM_DASHBOARD_SNAPSHOT_TTL_SECONDS         = 3600
FIPM_DASHBOARD_SNAPSHOT_MAX_BYTES           = 4194304
FIPM_DASHBOARD_CSV_MAX_ROWS                 = 100000
FIPM_DASHBOARD_BACKFILL_ON_STARTUP          = true
FIPM_DASHBOARD_STARTUP_BACKFILL_MAX_FIPS    = 500
FIPM_DASHBOARD_POSTING_BUDGET               = 20000
FIPM_DASHBOARD_POSTING_CAP                  = 2000
FIPM_DASHBOARD_CANDIDATE_CAP                = 200
FIPM_DASHBOARD_DF_SKIP_SHARE                = 0.20
FIPM_DASHBOARD_DF_MIN_KEYS                  = 3
FIPM_DASHBOARD_LSH_K                        = 128
FIPM_DASHBOARD_LSH_BANDS                    = 32
FIPM_DASHBOARD_LSH_ROWS                     = 4
FIPM_DASHBOARD_LSH_SEED                     = 20260911
FIPM_DASHBOARD_LSH_BUCKET_MAX               = 500
FIPM_DASHBOARD_LSH_PAIR_CAP                 = 200000
FIPM_DASHBOARD_EXACT_PAIRS_MAX_FIPS         = 300
FIPM_DASHBOARD_LIVE_MAX_FIPS_SCATTER        = 300
FIPM_DASHBOARD_MAP_EDGE_CAP                 = 5000
FIPM_DASHBOARD_CLUSTER_MIN_SIM              = 0.6
FIPM_DASHBOARD_DEFAULT_WEIGHTING            = principle
```

`Settings.check_dashboard_safety()` (called from `main.py` beside `check_network_safety()`) asserts
`LSH_BANDS * LSH_ROWS == LSH_K`, `MIN_POPULATION >= 1`, `SYNC_MAX_CELLS >= LIVE_MAX_CELLS`, and
`0 < DF_SKIP_SHARE <= 1`, refusing to start otherwise.

## 8. Tests

### 8.1 Acceptance tests (`backend/tests/test_ac_13_*.py`)

**Projection (`…_01_projection.py`)**
1. `project_answers` on a hand-built FIP produces the exact `fip_cells`/`fip_declarations`/`fip_facets` rows
   of a fixture, including the six `cell_state` values and their precedence.
2. `fer_key` equals `matrix.ts`'s key for a shared fixture table of 12 tricky free texts (combining accents,
   NBSP, CRLF, Turkish ı, leading/trailing space, mixed case) — the same table is consumed by a Vitest test
   on the frontend side, so the two normalisations are asserted against one oracle.
3. `hidden: true` questions produce no `fip_cells` row.
4. Every FIP write path (`POST`, `PATCH`, `import`, `from-network`, `claim`, migration apply, `DELETE`,
   `DELETE /sessions/{id}`) leaves `check-declarations --all` clean. One parametrised test, eight cases.
5. A rolled-back FIP write (IntegrityError injected) leaves **no** projection rows.
6. `backfill-declarations` is idempotent: two runs, byte-identical table dumps; a run interrupted after one
   batch and resumed produces the same dump.
7. `check-declarations` detects each of: a missing facets row, a wrong `cell_state`, an extra declaration
   row, a stale `projection_epoch`, a signature computed with a different `k`; `--fix` repairs all five.
8. A knowledge-model content edit bumps `projection_epoch`, enqueues the ref in `reprojection_backlog`, and
   does **not** reproject inline; `backfill-declarations --only-stale` drains it.

**Population and authorization (`…_02_population_auth.py`)**
9. Six viewer/visibility combinations: a private FIP appears only in its owner's and an admin's populations;
   a `link` FIP never appears in `public` or `network` populations but does in `mine` and in its session
   owner's session population; an anonymous session FIP reaches the session owner.
10. Two viewers with different rights on the **same** population spec get different `population_hash`es and
    never read each other's `dashboard_snapshots` row.
11. `population_too_small`: a population with `k_hidden > 0` and fewer than `MIN_POPULATION` FIPs 403s
    without echoing the count; the facilitator's own 3-FIP session does **not** 403; an empty effective
    population is a 200 with zeros.
12. Differencing: `public MINUS (public ∧ area=X)` is counted after exclusion and subject to the same
    threshold.
13. No aggregate response body contains an id, title, owner or session of a FIP the viewer cannot read
    individually — asserted by scanning the JSON of all five views for the ids of a fixture's unreadable
    FIPs.

**The five views (`…_03_views.py`)**
14. Write-path budget: 200 sequential `PATCH /api/fips/{id}` calls add < 10 ms median per call versus the
    same run with `FIPM_DASHBOARD_ENABLED=false` (asserted as a ratio with generous slack, plus the absolute
    projection-row count).
15. Coverage on a 12-FIP fixture returns hand-computed counts for all six states across all 21 questions,
    and its `SUM` over states equals the FIP count per question.
16. Coverage, adoption and gaps each execute **exactly one** aggregate statement (plus the population
    resolution and, for adoption, the one label lookup), counted by a `after_cursor_execute` listener.
17. Grouping levels (`question`/`subPrinciple`/`principle`/`group`) are consistent: the coarser rollup equals
    the sum of the finer one, computed from the same response.
18. Adoption counts a FIP once when it declares the same FER on two questions
    (`COUNT(DISTINCT fip_id)` regression).
19. `catalogued=exclude` returns exactly the free-text long tail, keyed by `text:…`.
20. Gaps' `coherence_flags`/`type_mismatches` are present and 0 before spec 12 §A2/§A3 exist.
21. Evolution's successor pairs match a fixture with `planned-replacement` + `successorFerId`.
22. Every view's CSV has the same numbers as its JSON (parsed and compared), a BOM, and honours
    `CSV_MAX_ROWS`.
23. ETag round trip: `If-None-Match` → 304; a FIP edit inside the population changes the ETag; a FIP edit
    **outside** it does not.

**Similarity (`…_04_similarity.py`)**
24. **The invariant:** for a 120-FIP fixture, `…/neighbours` scores are bit-identical to a brute-force
    reference implementation of §4.1 written independently in the test, for all three weightings. Candidate
    generation may only affect *which* neighbours appear, never a reported score.
25. **LSH vs exact:** on a 300-FIP fixture, the LSH-candidate cluster assignment agrees with the exact
    all-pairs assignment on ≥ 95% of FIPs at `minSimilarity=0.6`, and every reported cluster edge's score is
    the exact score.
26. Assumption A2: both-`notApplicable` scores 1.0; one-sided scores 0.0; both-empty is excluded from the
    denominator (a fixture where excluding vs including changes the answer).
27. `weighting=principle` differs from `weighting=question` on a fixture built so it must (an F-heavy
    disagreement), and both are reproducible across two calls.
28. Popular-key guard: a fixture where one FER is declared by 95% of FIPs — the key is skipped,
    `skippedPopularKeys` names it, and a FIP whose only other key is rare still finds its true neighbour
    first.
29. Posting cap: with `POSTING_CAP=3` and one key held by 10 FIPs, `postingTruncated` is true and the
    candidates are the three lexicographically-first ids (deterministic across runs).
30. Hot bucket: a fixture with 60 identical FIPs and `LSH_BUCKET_MAX=10` reports one `hotBuckets` entry of
    size 60 with a representative and no 1 770 pairs.
31. Signature determinism: reprojecting a FIP twice yields an identical `signature` blob and identical band
    rows; changing one declaration changes at least one band.
32. `…/pair` 404s (not 403) for a FIP the viewer cannot read individually — no existence oracle.

**Snapshots, network, flags (`…_05_snapshots_network_flags.py`)**
33. A snapshot is written on the first above-T1 request, reused on the second (asserted by statement count),
    and invalidated by each of the four staleness conditions independently.
34. `202 snapshot_pending` carries `Retry-After` and, when a stale row exists, `stalePayload` +
    `degraded: true`.
35. `refresh` is owner/admin-only; a concurrent refresh 409s.
36. `ingest-network-fips` against the spec 11 fixtures writes `source='network'` shadow rows, no `fips` row,
    drops `unmapped` with a counted report, and the shadow rows appear **only** in a population containing
    `{"kind":"network"}`. The autouse conftest guard proves no live network call.
37. Cross-boundary similarity: a local FIP's nearest neighbour in a `public ∪ network` population is the
    network shadow row that shares its keys.
38. `FIPM_DASHBOARD_ENABLED=false` → 503 on all endpoints, `dashboardEnabled: false` in `/api/health`, **and
    no projection rows written** by a FIP write; flipping it back on plus a restart backfills (≤500 FIPs).
39. Schema 7 → 8 upgrades an existing `fipm.db` in place: eleven new tables, the four `fips` covering
    indexes created by `_ensure_indexes()`, existing rows untouched, `schema_version = 8`.
40. `check_dashboard_safety()` refuses to start on `BANDS*ROWS != K`, `MIN_POPULATION=0`,
    `SYNC_MAX_CELLS < LIVE_MAX_CELLS`, `DF_SKIP_SHARE=0`.
41. §1.8's degrade ladder: with the projection deliberately emptied, a 50-FIP population returns correct
    numbers with `degraded: true` and `no-store`; a 5 000-FIP population returns `409 projection_stale`; and
    the degraded numbers equal the projected ones (the same fixture, projected and unprojected).
42. No `json_extract` / `->>` / `json_each` appears in any statement executed by any of the five views — a
    test installs an `after_cursor_execute` listener across a full view sweep and greps the emitted SQL.

### 8.2 Scale test

`backend/tests/scale/` — `generate_fips.py` + `test_scale_13_dashboard.py`, marked
`@pytest.mark.scale` (registered in `[tool.pytest.ini_options] markers`), **excluded from the default run**
by `addopts = "-m 'not scale'"`.

`generate_fips.py --n N --seed S --out DB` builds a realistic population with the standard library only:

- FER choice per question drawn from a **Zipf** distribution over the 138 seed FERs (s ≈ 1.1) so a handful of
  FERs dominate and a long tail exists — the shape that breaks naive inverted indexes and the shape the
  popular-key guards are for;
- 12% of answers free text, drawn from a 300-phrase pool with deliberate near-duplicates (case, whitespace,
  accents) so the convergence key earns its keep;
- 25% of cells unanswered, 5% `not-applicable`, 8% `planned*`, 3% `none`;
- 30 **cluster seeds**: 40% of FIPs are a mutation (3 random changes) of one seed, so clusters genuinely
  exist and clustering recall is measurable;
- 200 FIPs share one identical declaration set (the hot-bucket case);
- a visibility mix (70% public, 20% link, 10% private), 50 sessions, 5 questionnaire versions;
- written with `projection_suspended()` + bulk inserts, then `backfill-declarations`, so generation itself
  exercises the backfill path. Throughput target ≥ 2 000 FIPs/s for generation, ≥ 400 FIPs/s for projection.

`test_scale_13_dashboard.py` reads `N` from `FIPM_TEST_SCALE_FIPS` (**default 2 000** — the whole test,
generation included, runs in ~25 s, which is CI-reasonable; `FIPM_TEST_SCALE_FIPS=20000 pytest -m scale` is
the opt-in and takes ~5 min). It asserts, for each of the five views plus `neighbours`, `clusters` and `map`:

- **hard: the statement count is constant in N.** Run each view at N and at N/4 and assert the counted
  statements are *equal* — the N+1 detector, and the only assertion that must never be relaxed. Exact
  expected counts: coverage 2, gaps 2, adoption 4, evolution 3, convergence 4, neighbours 4, map 6.
- **hard: no statement text repeats** within a view (parameter-varying repeats are how N+1 hides).
- **hard: `neighbours` scans ≤ `POSTING_BUDGET` + `CANDIDATE_CAP × 60` rows** at both N and N/4, measured
  from `EXPLAIN QUERY PLAN`-independent row counters — i.e. the cost really is population-independent.
- **soft: timings are recorded** to `backend/tests/scale/last-run.json` (per view: N, rows scanned, wall ms,
  p50/p95 over 20 runs, SQLite file size) and printed. Ceilings are deliberately loose (coverage ≤ 3 s at
  N=20 000) because CI hardware varies; the *numbers* are the deliverable, and §7.4's tuning step reads this
  file. A regression gate compares against a committed `baseline.json` and fails only on a > 3× regression.
- **hard: the projection's row counts and file size match the §0 model** within 20% (so a future change that
  silently doubles the projection is caught).

## 9. Decisions taken, and open questions for the lead

Decisions, taken here so implementation is not blocked (per the working-style note in PLAN §9):

- **D1.** Two fact tables (`fip_cells` at cell grain, `fip_declarations` at declaration grain), not the one
  mixed-grain table the brief sketched — a mixed grain forces a `DISTINCT` into every coverage query (§1.1).
- **D2.** No denormalised `visibility`/`owner_id` on the fact tables. The security predicate runs once, in
  phase 1, against the authoritative `fips` table behind covering indexes. A cached authorization decision
  that can go stale is a leak waiting to happen (§1.1, §2.2).
- **D3.** One `after_flush`/`before_commit` ORM hook maintains the projection inside the caller's
  transaction, rather than eight explicit call sites a future router can forget (§1.6).
- **D4.** `cell_state` is precomputed as one of six mutually exclusive values, so no view ever writes a
  `CASE` over declarations and coverage/gaps are genuinely single `GROUP BY`s (§1.3).
- **D5.** Equal weight **per principle code** is the default similarity weighting; `question` and `letter`
  are parameters (§4.1). Recorded as assumption A1, to confirm.
- **D6.** Clustering is single-link connected components over a thresholded LSH-candidate graph, cached as a
  snapshot — not true hierarchical clustering, which needs the O(n²) distance matrix this spec exists to
  avoid (§4.4).
- **D7.** No numpy/scipy/sklearn, and no new dependency of any kind. MinHash is `hashlib.blake2b` plus
  integer arithmetic; the parallel escape hatch is `--jobs` over an id range (§4.5).
- **D8.** The dashboard never calls the nanopublication network. Network FIPs are periodically **ingested**
  as read-only shadow rows with `source='network'` and no `fips` row (§5.4).
- **D9.** `link`-visibility FIPs are excluded from every population except the owner's, their session
  owner's, and admin — stricter than `authz.can_read`, because appearing in an aggregate is not the same as
  being fetchable by id (§2.2, assumption A4).

Open questions, each with a recommendation and the cost of deciding late:

- **Q1 — similarity weighting (spec 12 §E.3, the lead's own open question).** Equal per principle code, per
  question, or per FAIR letter? Recommendation: **per principle code** (D5) — per-question weighting makes F
  worth 6/21 of the score because of a questionnaire-construction artefact. Cost of deciding late: **none**.
  It is a query parameter echoed in the ETag; changing the default is one line and a snapshot refresh.
- **Q2 — what counts as similarity: `current` only, or `current` + planned?** Recommendation: **`current`
  only** by default, `statuses=currentPlanned` as a parameter. "We both plan to adopt X" is convergence too,
  but it belongs to the evolution view, and mixing them makes a high score ambiguous. Cost of deciding late:
  **none**, same mechanism as Q1.
- **Q3 — the k-anonymity threshold.** Recommendation: **`FIPM_DASHBOARD_MIN_POPULATION = 5`**, with §2.4's
  `k_hidden` rule so it never blocks a facilitator reading their own small session. 5 is the conventional
  floor for aggregate disclosure and, given today's visibility rules, it almost never binds — it is there
  for the moment a population term admits FIPs the viewer cannot open. Cost of deciding late: **low** (one
  setting), but the *rule* (threshold on `k_hidden`, not on the raw count) should be agreed now, because
  getting it wrong in the other direction breaks the workshop.
- **Q4 — is the network population the default outside a session?** Spec 12 §C3 says it should be ("the
  value grows with the network population"). That requires `ingest-network-fips` to have run, and it makes
  the first `/dashboard` visit show other people's data. Recommendation: **yes**, default `pop=network` on
  `/dashboard` when no population is given *and* an ingest exists; fall back to `pop=public` otherwise, with
  the picker one click away and the ingest timestamp always visible. Cost of deciding late: **none**, a
  default in one component.
- **Q5 — Postgres and Alembic.** This spec adds eleven tables under the no-Alembic v1 rule. Recommendation:
  keep `create_all` + `_ensure_columns` + the new `_ensure_indexes` for now, and make **Postgres + Alembic a
  single v2 workstream** rather than migrating table by table — the 2027 scale point needs Postgres anyway,
  for concurrent writers more than for speed. Cost of deciding late: **medium** — every additional table
  shipped under `create_all` is one more table the first Alembic revision has to reverse-engineer, so this is
  the decision worth taking before the *next* schema-bearing spec, not before this one.
- **Q6 — do free-text declarations enter the FER catalogue automatically?** Adoption's long tail
  (`catalogued=exclude`) is explicitly "candidates for the catalogue" (spec 12 §C2), and at 10k FERs a human
  cannot triage it. Recommendation: **no automation in v2** — add a "promote to catalogue" action on a
  long-tail row, reusing the existing admin FER promote/merge path, with the dashboard supplying the count
  and the raw variants. Automatic promotion would import typos as resources. Cost of deciding late: **none**,
  it is additive.
- **Q7 — snapshot retention and the right to be forgotten.** A snapshot payload is aggregate-only and names
  FIPs only in the similarity views, where output is filtered by readability at compute time — but a deleted
  FIP's id could survive in a `clusters` payload until the snapshot expires. Recommendation: on FIP delete,
  additionally `DELETE FROM dashboard_snapshots WHERE view IN ('clusters','map')` for any population whose
  `source_max_updated_at` predates the delete — cheap, and it keeps the privacy notice's deletion promise
  literally true. Cost of deciding late: **low** technically, **high** if it is discovered by an auditor
  rather than by us. Recommend implementing it in brief B.

### Assumptions recorded (per PLAN §9, facilitator-level, to confirm)

- **A1.** Similarity weights each of the 12 principle codes equally (Q1).
- **A2.** Both sides `not-applicable` on a question = agreement (1.0); one side = disagreement (0.0); both
  empty = the question is excluded (§4.1).
- **A3.** `FIPM_DASHBOARD_MIN_POPULATION = 5`, applied to `k_hidden` rather than the raw count (Q3).
- **A4.** `link` FIPs are excluded from public and network populations (D9).
- **A5.** Network FIPs are ingested facts, not live fetches, and are never `fips` rows (D8).
- **A6.** No new Python or npm dependency (D7).
- **A7.** Similarity counts `current` declarations only, by default (Q2).
- **A8.** The default population on `/dashboard` outside a session is the network population when one has
  been ingested (Q4).

---

## 10. Implementation plan — three briefs

**The backend does not fit in one builder round.** Briefs A and B are **sequential**: B depends on A's
projection tables, population resolver and response envelope. Brief C (frontend) can start in parallel with
B as soon as A's contracts are merged, because §3's response shapes are fixed above and C mocks the API
module. All three go through `verifier`, then `reviewer`, then `scribe`. i18n strings are `translator`'s job:
builders add **en** keys only and list them.

### 10.1 Builder brief A — backend, the projection and the four aggregate views

**Goal.** Implement, with tests, (a) the derived projection of spec 13 §1 with its write hook, CLI and
degrade ladder, (b) population resolution, authorization and k-anonymity of §2, and (c) the coverage,
adoption, gaps and evolution endpoints of §3.1/§3.2/§3.4/§3.5 plus their CSV variants of §3.6. **Not** in
this brief: anything in §4 (similarity) or §5 (snapshots, network ingestion) — B does those. Where a view
would exceed tier T1 (§0), return `409 projection_stale` or `413` as specified and leave a `TODO(spec13-B)`
comment naming the snapshot layer; do **not** invent a cache.

**Read first, in this order.** `docs/specs/13-fip-dashboard.md` (this spec — §1, §2, §3, §7, §8.1 tests 1–23
and 39–42 are yours), `docs/specs/12-understanding-assurance-dashboard.md` §C (what the views are for),
`docs/specs/03-matrix-and-rdf.md` §1.2 (the convergence key and the `agreed` rule you must not re-derive),
`frontend/src/lib/matrix.ts` (`normaliseFreeText`, `buildConvergence`, `principleGroup` — the behaviour your
projection must reproduce exactly), `backend/fipm/models.py` (`Fip.answers` is JSON; the existing index
naming convention), `backend/fipm/db.py` (`SCHEMA_VERSION`, `_ensure_columns`, the WAL/pragma block, and the
comment style that documents every version bump), `backend/fipm/rdf.py` (`_free_text_hash` — you refactor
`normalise_free_text` out of it; `KNOWN_PRINCIPLE_IDS`, `KNOWN_QUESTION_INDIVIDUALS`, `_questions_by_id`),
`backend/fipm/authz.py` (`can_read`, `optional_user`, `require_user` — your security predicate must agree
with `can_read` except for the documented `link` narrowing, D9), `backend/fipm/routers/fips.py` (the eight
FIP write paths your hook must cover; `_get_readable_fip`), `backend/fipm/routers/sessions.py`
(`list_session_fips`, `delete_session`, `resolve_session_questionnaire_refs` for `area_key` labels),
`backend/fipm/exporters.py` (`build_session_export_csv` — the CSV/BOM conventions you reuse),
`backend/fipm/cli.py` (subcommand shape), `backend/fipm/config.py` (`check_network_safety` is the model for
`check_dashboard_safety`), `backend/tests/test_ac_05_7_schema_upgrade.py` (the in-place upgrade test
pattern), `backend/tests/conftest.py`.

**Files to create.**

- `backend/fipm/projection.py` — the heart. Exports `convergence_key(decl) -> str`,
  `project_answers(km_content, answers) -> ProjectedFip` (**pure**, no DB — this is the one function the
  §1.8 fallback and the projection share, and the reason they cannot disagree),
  `reproject_fip(session, fip_id)`, `unproject_fip(session, fip_id)`, `projection_suspended()`,
  `register_projection_hooks(session_factory)`, `stale_fip_ids(session, limit)`. No FastAPI imports.
- `backend/fipm/dashboard/__init__.py`, `populations.py` (spec parsing, canonicalisation, `spec_hash`,
  `auth_scope`, the §2.2 resolver returning a reusable SQLAlchemy CTE, the §2.4 k-anonymity check),
  `views.py` (one function per view returning `(data, params_hash)`, each issuing the §3 statements and
  nothing else), `csvout.py` (§3.6).
- `backend/fipm/routers/dashboard.py` — `GET /api/dashboard/{coverage,adoption,gaps,evolution}`, their
  `.csv` siblings, `GET|POST /api/dashboard/populations`, `GET /api/dashboard/populations/{hash}`. Registered
  in `main.py` after `fips.router`.
- `backend/tests/test_ac_13_01_projection.py`, `…_02_population_auth.py`, `…_03_views.py` — tests 1–23,
  39–42 of §8.1.
- `backend/tests/fixtures/dashboard/normalisation-cases.json` — the 12 tricky free texts of test 2, shared
  with the frontend's Vitest (brief C consumes the same file).

**Files to change.**

- `backend/fipm/models.py` — `FipFacets`, `FipCell`, `FipDeclaration`, `FerKeyDf`, `DashboardPopulation`,
  `DashboardMeta` with **exactly** the columns and indexes of §1.2/§1.3/§1.4/§2.1 (B adds the signature,
  bucket, network and snapshot tables); plus the four covering indexes on `Fip` from §2.2 declared in
  `Fip.__table_args__`.
- `backend/fipm/db.py` — `SCHEMA_VERSION` 7 → 8 with the version comment in the established style; new
  `_ensure_indexes()` called after `_ensure_columns()` and **before** the version bump, with the same
  duplicate-tolerant `OperationalError` handling; `register_projection_hooks(SessionLocal)`.
- `backend/fipm/config.py` — the §7.5 settings and `check_dashboard_safety()`; called from `main.py` beside
  `check_network_safety()`.
- `backend/fipm/main.py` — include the router; the §7.2 startup backfill (after `run_import()`, inside the
  same try/except-and-log discipline).
- `backend/fipm/cli.py` — `backfill-declarations` and `check-declarations` per §1.7; collect-then-`unproject`
  in `_cmd_purge_standalone_fips`.
- `backend/fipm/routers/health.py` — `dashboardEnabled`.
- `.env.example` — the §7.5 variables, one comment line each.
- `data/i18n/en.json` — **en only**, keys under `dashboard.*` for the four views' labels, the six
  `cell_state`s, the error codes and the population term kinds. List them in your report.

**Acceptance criteria.**

1. `cd backend && uv run pytest -q` passes; the count rises by tests 1–23 and 39–42 of §8.1. Report before/after.
2. `uv run ruff check .` and `uv run ruff format --check .` clean.
3. **Coverage, adoption and gaps each execute exactly one aggregate statement** (plus population resolution,
   plus adoption's single label lookup), proven by test 16's `after_cursor_execute` counter with exact
   expected numbers — not "few", the exact integer.
4. **No `json_extract`, `->>` or `json_each` in any statement any view emits** (test 42). The only JSON
   reading in the diff is inside `project_answers` and the §1.8 fallback.
5. Everything per-request is SQLAlchemy Core; no `text()` outside `db.py`'s DDL and the CLI's invariant
   checks. Grep the diff and confirm in your report.
6. `check-declarations --all` is clean after every one of the eight FIP write paths (test 4) and after a
   `purge-standalone-fips` run.
7. A rolled-back FIP write leaves no projection rows (test 5).
8. The §1.8 ladder behaves exactly as specified, and the degraded numbers **equal** the projected ones on the
   same fixture (test 41).
9. Authorization: tests 9–13 pass, including that no aggregate body names an unreadable FIP.
10. Schema 7 → 8 upgrades an existing `fipm.db` in place, creating the four `fips` covering indexes via
    `_ensure_indexes()` (test 39). Verify by hand on a copy of a real dev DB and say so in your report.
11. `FIPM_DASHBOARD_ENABLED=false` → 503 everywhere, `dashboardEnabled: false` in health, **and zero
    projection rows written** by a FIP write (test 38's first half).
12. Write-path budget: test 14's median overhead per `PATCH` is under 10 ms. If it is not, report the
    measured number and what dominates — do not silently relax the test.

**Report back:** the test count before/after; the measured per-FIP projection time and the projection row
counts for a 1 000-FIP fixture; the exact statement count per view; the full list of new `dashboard.*` i18n
keys with their en strings (for the translator); anything in §1–§3 the code could not do as specified, with
what you did instead; and any place where `matrix.ts`'s behaviour and your projection had to differ.

### 10.2 Builder brief B — backend, similarity, snapshots and network ingestion

**Depends on brief A being merged.** Uses A's `projection.project_answers`, `dashboard.populations` resolver
and response envelope unchanged; if either needs a change, say so rather than forking it.

**Goal.** Implement, with tests, (a) the exact similarity measure and its three weightings of spec 13 §4.1,
(b) exact nearest neighbours via the inverted index of §4.3, (c) MinHash signatures, LSH bucketing, hot-bucket
handling and bounded clustering of §4.2/§4.4, (d) the snapshot layer, ETags and refresh of §5.1–§5.3, (e)
network ingestion of §5.4, and (f) the scale test harness of §8.2.

**Read first.** `docs/specs/13-fip-dashboard.md` §4, §5, §8.1 tests 24–38, §8.2 (all yours), plus §0's tier
table and §1.5's key rule; `docs/specs/11-nanopub-network.md` §3.3 and §3.4 (the network response shape you
ingest, the question mapping and the cache you must **not** bypass or extend), `backend/fipm/network.py`
(`get_fip_communities`, `get_community_fip` — call them, do not reimplement),
`backend/fipm/rdf.py::question_id_from_individual` and `backend/fipm/fer_types.py` (the `ferTypeKey`
inversion, already written for spec 11), `backend/fipm/projection.py` (brief A's — you extend it with
signatures), `backend/fipm/dashboard/populations.py` (brief A's resolver and `auth_scope`),
`frontend/src/lib/matrix.ts::buildConvergence` (the `agreed` rule §3.3 reuses),
`backend/tests/fixtures/network/*.json` (spec 11's recorded fixtures — reuse them, record nothing new),
`backend/tests/conftest.py` (the autouse guard that raises on any un-patched `fipm.network` call).

**Files to create.**

- `backend/fipm/similarity.py` — **pure, no DB, no FastAPI.** `tokens(cells, declarations) -> set[str]`,
  `score_pair(a, b, weighting, statuses) -> PairScore` (the §4.1 measure with the per-principle breakdown),
  `minhash(tokens) -> bytes`, `bands(signature) -> list[int]`, `union_find` clustering. This module is where
  every number a user sees comes from, so it is unit-tested independently of any query.
- `backend/fipm/dashboard/similarity_views.py` — candidate generation (§4.3's key ordering, budgets, caps and
  their disclosure fields), the LSH candidate-pair query, the exact-all-pairs path under
  `EXACT_PAIRS_MAX_FIPS`, clustering, the map's server-side bucketing, and §3.3's convergence statements.
- `backend/fipm/dashboard/snapshots.py` — the §5 tier decision, freshness check, ETag construction,
  `get_or_compute`, the `202`/`stalePayload` behaviour, and Q7's delete-time invalidation.
- `backend/fipm/network_ingest.py` — §5.4.
- `backend/tests/test_ac_13_04_similarity.py`, `…_05_snapshots_network_flags.py` — tests 24–38.
- `backend/tests/scale/__init__.py`, `generate_fips.py`, `test_scale_13_dashboard.py`, `baseline.json`,
  `README.md` (how to run the opt-in N, what `last-run.json` means, how to refresh the baseline).

**Files to change.**

- `backend/fipm/models.py` — `FipSignature`, `FipSignatureBand`, `LshHotBucket`, `NetworkFip`,
  `DashboardSnapshot` with exactly §4.2/§4.4/§5.1/§5.4's columns and indexes.
- `backend/fipm/projection.py` — write the signature and 32 band rows in `reproject_fip`; delete them in
  `unproject_fip`; maintain `fer_key_df` incrementally; extend `check-declarations` with invariants 4 and the
  signature-parameter check.
- `backend/fipm/routers/dashboard.py` — `GET /api/dashboard/similarity/{pair,neighbours,clusters,map}`,
  their `.csv` siblings, `POST /api/dashboard/refresh`; route coverage/adoption/gaps/evolution through
  `snapshots.get_or_compute` so the T2 path replaces brief A's `409`.
- `backend/fipm/cli.py` — `refresh-dashboard`, `ingest-network-fips`.
- `backend/fipm/routers/fips.py` — Q7's snapshot invalidation on FIP delete.
- `backend/fipm/db.py` — the version comment gains B's tables (SCHEMA_VERSION stays 8 if A and B land in the
  same release; bump to 9 and say so if not).
- `backend/pyproject.toml` — `[tool.pytest.ini_options]` gains `markers = ["scale: ..."]` and
  `addopts = "-m 'not scale'"`. **No new dependency** (AC 4 below).
- `.env.example`, `data/i18n/en.json` (en only, `dashboard.similarity.*`, `dashboard.snapshot.*`).

**Acceptance criteria.**

1. `cd backend && uv run pytest -q` passes (default run excludes `-m scale`); count rises by tests 24–38.
   `uv run pytest -m scale` passes at the default `FIPM_TEST_SCALE_FIPS=2000` in under 60 s.
2. `uv run ruff check .` / `format --check` clean.
3. **The §4.2 invariant:** every similarity score in every response is the exact §4.1 measure, asserted
   against an independent brute-force reference for all three weightings (test 24). Candidate generation may
   change *which* neighbours appear, never a score.
4. **No new dependency.** `backend/pyproject.toml`'s `[project] dependencies` is unchanged; grep the diff for
   `numpy`, `scipy`, `sklearn`, `datasketch`, `pandas` and confirm zero hits in your report.
5. `neighbours`'s scanned-row count is **independent of population size** (scale test), and its statement
   count is 4 at every N.
6. LSH agrees with exact all-pairs on ≥95% of cluster assignments at 300 FIPs (test 25), and the hot-bucket
   guard turns 60 identical FIPs into one group, not 1 770 pairs (test 30).
7. Signatures are deterministic across reprojections and across processes (test 31); a changed declaration
   changes at least one band.
8. `ingest-network-fips` writes only `source='network'` shadow rows, no `fips` row, and **no test makes a
   live network request** — proven by spec 11's autouse conftest guard (test 36).
9. Snapshot isolation: two viewers with different rights never read each other's snapshot (brief A's test 10
   still passes with snapshots enabled); all four staleness conditions invalidate independently (test 33).
10. The scale test's **statement-count assertions are equalities, at two values of N**, and its timings are
    written to `last-run.json`. Paste that file's contents into your report.
11. `…/clusters` and `…/map` are never computed in-request above `EXACT_PAIRS_MAX_FIPS` — asserted by a test
    that patches the compute function to raise and expects `202`, not a 500.

**Report back:** the test count before/after; `last-run.json` verbatim for N=2 000 **and** N=20 000 if you
can run it; the measured LSH recall at 300 and at 2 000 FIPs; the measured per-FIP signature time; the
SQLite file size for a 20 000-FIP population broken down per table; the new en i18n keys; and — most
important — **which of §7.5's defaults your measurements say are wrong**, with the numbers.

### 10.3 Builder brief C — frontend

**Can start as soon as brief A is merged** (§3's response shapes are fixed and A ships coverage, adoption,
gaps and evolution). Mock the similarity endpoints from §3.3/§4.3's documented shapes until B lands.

**Goal.** Implement, with tests, the six dashboard routes of spec 13 §6.1, the population picker and its
URL-addressable state, the server-bucketed renderings of §6.2, print and CSV of §6.3.

**Read first.** `docs/specs/13-fip-dashboard.md` §3 (the exact response shapes you render), §6 (what each
page contains and what must never be rendered per-FIP), §0 (the tier table — the frontend must render
`tier`, `degraded` and `202` states, not hide them); `docs/specs/12-…` §C2/§C3 (what the views are *for*, and
"same principle × row layout as the matrix … desktop-first"); then, in the repo:
`frontend/src/views/SessionMatrix.vue` and `frontend/src/lib/matrix.ts` (the layout, the sticky first column,
the toggles-as-pure-view-state discipline you copy — a grouping change must **not** refetch),
`frontend/src/components/MatrixCell.vue`, `MatrixLegend.vue`, `ConvergenceBadge.vue` (reuse the
`--color-status-*` variables and the legend vocabulary; do **not** fork these components — the dashboard's
cells are shares, not chips),
`frontend/src/assets/print-matrix.css`, `frontend/src/api/client.ts` and `fips.ts` (API-module conventions,
`If-None-Match` handling), `frontend/src/lib/lang.ts`, `frontend/src/router/index.ts`,
`frontend/src/views/NetworkFipList.vue` (the three-way error-state pattern: disabled / unavailable /
not-found), `frontend/src/views/Home.test.ts` (component-test pattern with a mocked api module).

**Files to create.**

- `frontend/src/api/dashboard.ts` — one function per §3 endpoint plus `savePopulation`,
  `refreshDashboard`, and `dashboardCsvUrl(view, params)`. `If-None-Match` passed through; a `304` reuses the
  cached body; a `202` returns `{status:'pending', retryAfter}` rather than throwing.
- `frontend/src/types/dashboard.ts` — response types transcribed from §3, including `tier`, `degraded`,
  `truncated`, `candidateBudgetExhausted`, `skippedPopularKeys`, `hotBuckets`, `scatterAvailable`.
- `frontend/src/lib/dashboard.ts` + `dashboard.test.ts` — **pure**: population spec ⇄ query string
  (including the three shorthands), client-side rollup between the four grouping levels, share formatting,
  `cell_state` ordering. Must consume
  `backend/tests/fixtures/dashboard/normalisation-cases.json` and assert `normaliseFreeText` against it, so
  the frontend and backend keys are proven identical (brief A's test 2 is the other half).
- `frontend/src/views/DashboardHome.vue`, `DashboardCoverage.vue`, `DashboardAdoption.vue`,
  `DashboardSimilarity.vue`, `DashboardGaps.vue`, `DashboardEvolution.vue`, each with a `.test.ts`.
- `frontend/src/components/PopulationPicker.vue`, `CoverageHeatMap.vue`, `SimilarityHistogram.vue`,
  `ClusterCard.vue`, `NeighbourList.vue`, `DashboardLegend.vue`, `SnapshotBanner.vue`, `DegradedBanner.vue`,
  with tests for the picker, the heat map and the two banners.
- `frontend/src/assets/print-dashboard.css`.

**Files to change.**

- `frontend/src/router/index.ts` — the six routes, `meta: { requiresAuth: false }` (an anonymous viewer gets
  the public/network populations), `props: true`.
- `frontend/src/App.vue` (or wherever the nav lives) — a **Dashboard** entry, hidden when `GET /api/health`
  reports `dashboardEnabled: false`.
- `frontend/src/views/SessionMatrix.vue` — one link, "Dashboard for this session" →
  `/dashboard?pop=session:<id>`. Nothing else in this view changes.
- `data/i18n/en.json` — **en only**, everything under `dashboard.*`. List every key with its en string in
  your report for the translator; do **not** touch `pt-PT.json` / `pt-BR.json` / `es.json`.

**Acceptance criteria.**

1. `cd frontend && npm run test` passes; `npm run build` and `npx vue-tsc --noEmit` clean. No new
   `package.json` dependency.
2. **Nothing renders per-FIP at scale.** Asserted by a test that mocks a `fipCount: 10000` response and
   counts DOM rows: coverage ≤ 126 cells, gaps ≤ 21 rows, adoption ≤ 50 rows, similarity ≤ 200 cluster cards
   and ≤ 130 histogram bars, and **no** scatter when `scatterAvailable: false` (a one-line explanation is
   rendered instead).
3. A grouping change (`question` ⇄ `subPrinciple` ⇄ `principle` ⇄ `group`) and a language change **do not
   refetch** — asserted by the mocked api call count, exactly as `SessionMatrix.vue` re-derives on a language
   switch.
4. Every view's full state round-trips through the URL: navigate, change three controls, read
   `router.currentRoute.query`, reload from that query, assert identical rendering. A saved population
   renders its label, `fipCount` and `computedAt`.
5. Four distinct states render distinctly: `tier: "snapshot"` (banner with age + a Refresh that `POST`s
   exactly once per click), `degraded: true` (banner naming the reason), `202 snapshot_pending` (polls at
   `Retry-After`, max 20 attempts, renders `stalePayload` dimmed underneath when present), and each error
   code — `dashboard_disabled` (no retry), `population_too_small`, `projection_stale` (shows the CLI hint to
   an admin only), `similarity_population_too_large`.
6. Disclosure fields are visible, not swallowed: `truncated`, `candidateBudgetExhausted`,
   `postingTruncated`, `skippedPopularKeys` and `hotBuckets` each render a short, translated explanation
   where they apply. A number the server says is approximate must never be shown as exact.
7. Colour is never the only signal (spec 02 §4.3): every heat-map cell carries its number and an
   `aria-label`; the legend is always present and always printed.
8. `print-dashboard.css` puts the coverage view on one A3 landscape sheet with the legend visible.
9. CSV is a plain `<a :href="dashboardCsvUrl(...)">` per view — no fetch-then-blob.
10. No hard-coded English outside `data/i18n/en.json`. The frontend makes no request to any host other than
    its own `/api`.

**Report back:** the test count before/after; the full list of new i18n keys with their en strings; any place
§3's or §6's shape was awkward to render, with the contract change you would make; and a screenshot-free
description of what the coverage view looks like at `fipCount: 40` versus `fipCount: 10000`, so the lead can
sanity-check the "same layout, different density" claim before the dry run.

---

## 11. Amendments

### 11.1 Coverage `groupBy` is presentation-only — 11 Sep 2026 (§3.1)

The spec contradicted itself: §3.1's aggregate ran at per-question grain and rolled up in Python before
responding, while §6.3 required the SPA to change grouping levels with no refetch — which only works if the
response is always the finest grain. Resolved in favour of the SPA: **the aggregate and the response are
always per-question**, every row carries every rollup key (`questionId`, `subPrinciple`, `principle`,
`principleGroup`), the SPA sends `groupBy=question` and folds client-side, and `groupBy` now affects only
direct API and CSV consumers, which have no client to fold for them. §8.1 test 17 becomes the assertion that
the two rollups agree. No cost or cardinality change — the grain of the aggregate never varied in the first
place.

### 11.2 Gaps has no `groupBy` — 11 Sep 2026 (§3.4)

"Same four `groupBy` levels as coverage" was under-specified and, on inspection, unimplementable as written:
`coherence_flags` and `type_mismatches` (spec 12 §A3/§A2) have no defined meaning summed across a rolled-up
group, because a coherence rule fires on a *pair* of questions and would be double-counted by the fold. The
parameter is dropped; gaps rows are **always per-question**, bounded by questionnaire size (21 rows for the
GO FAIR model), which is what the implementation does. §3.4 gains the `data` shape it was missing. A client
still sending a vestigial `groupBy=question` is harmless — unknown query parameters are ignored — and should
drop it.

### 11.3 `…/map` has a normative wire contract — 11 Sep 2026 (§3.3.1)

§4.4 described the map in prose only, so the frontend builder inferred the field names for `histogram`,
`principleBuckets`, `convergence`, `topClusters`, `hotBuckets` and the scatter's `nodes`/`edges`. Those
shapes are now transcribed from `frontend/src/types/dashboard.ts` into the spec as the authoritative
contract, with three corrections:

1. *additive* — `convergence` rows also carry `notApplicableFips`, which `matrix.ts`'s `Convergence` has and
   the inferred type omitted; the frontend's `ConvergenceRow` should gain it, and ignoring it breaks nothing
   meanwhile;
2. **the frontend must be corrected** — `edges` as inferred is unbounded and cannot be produced efficiently
   (300 FIPs admit 44 850 pairs, ≈2 MB, in a view whose premise is that no response scales with the
   population). Edges are now thresholded at `CLUSTER_MIN_SIM`, ordered by similarity, capped at the new
   `FIPM_DASHBOARD_MAP_EDGE_CAP` (default 5000), with a new `edgesTruncated: boolean` the scatter must
   disclose per brief C's AC 6;
3. *additive* — `MapNode` gains `clusterId`, so the scatter colours by cluster without re-deriving connected
   components in the browser.

`FIPM_DASHBOARD_MAP_EDGE_CAP` is added to §7.5.

### 11.4 `GET /api/dashboard/fips` specified — 11 Sep 2026 (§3.7)

§6.2 required a typeahead over the population's readable FIPs for the neighbours panel; §3 never defined the
endpoint. Now specified — `q` substring-matched in SQL over the FIP label, `limit` capped at 20, the §2.2
security predicate followed by a second `readable_individually` filter because the endpoint *names* FIPs, a
plain non-envelope response, and one explicit carve-out: **§2.4's k-anonymity threshold does not apply**,
since every row is a FIP the viewer may already fetch by id, and applying it would 403 the 3-FIP workshop
session that §2.4 exists to protect. Brief B is implementing it alongside the similarity views; it is
specified here as shipped, not as pending.

### 11.5 Known gap, not amended: `…/pair` has no UI

`GET /api/dashboard/similarity/pair` is specified (§3.3), implemented, and reachable only by direct API call:
brief C ships no panel for it. Spec 12 §C2's *"distance to a chosen reference FIP … so an area can compare
itself with, say, a network FIP from the same domain"* is therefore **not** delivered by the first release.
It is a v2 follow-up and a small one — the endpoint, the scoring and §3.7's picker all exist, so the work is
a second picker beside the neighbours one and a reuse of `SimilarityPairData`'s per-principle breakdown.
Recorded here so it is not mistaken for an oversight, and so the lead can weigh it against the 3 Oct code
freeze.
