# spec 13 §8.2 — the opt-in scale test

`test_scale_13_dashboard.py` is excluded from the default `uv run pytest -q`
run (`addopts = "-m 'not scale'"` in `pyproject.toml`). Opt in with:

```
uv run pytest -m scale
```

`FIPM_TEST_SCALE_FIPS` controls the population size `N` (default **2000** —
the whole test, including generation, takes ~25-40s on ordinary developer
hardware). The opt-in, larger run:

```
FIPM_TEST_SCALE_FIPS=20000 uv run pytest -m scale
```

takes several minutes; this is the number to run before a release that
touches `fipm/dashboard/*`, `fipm/similarity.py` or `fipm/projection.py`.

## What it asserts

For each of `coverage`, `gaps`, `adoption`, `evolution`, `neighbours`,
`map` (and `clusters`, without a spec-mandated exact count):

- **hard** — the statement count is an *exact*, spec-given integer
  (coverage 2, gaps 2, adoption 4, evolution 3, neighbours 4, map 6), and
  it is *identical* at `N` and at `N/4` — the classic N+1 detector. This is
  the assertion that must never be relaxed: if it starts failing, a code
  change introduced a query that scales with population size.
- **hard** — no statement's SQL text repeats within one view call
  (parameter-varying repeats are how N+1 hides behind a superficially
  constant count).
- **hard** (`neighbours` only, spec §4.3) — the number of `fip_declarations`
  rows scanned by candidate generation is bounded by
  `FIPM_DASHBOARD_POSTING_BUDGET + FIPM_DASHBOARD_CANDIDATE_CAP * 60`, at
  both `N` and `N/4` — this is the numeric expression of "neighbour cost is
  independent of population size".
- **soft** — wall-clock timings for every view, at `N` and `N/4`, written to
  `last-run.json` and printed. Ceilings are loose on purpose (a 3-second
  bar CI hardware may or may not clear) — the *numbers* are what §7.4's
  tuning pass reads, not a pass/fail gate.

## `generate_fips.py`

`python generate_fips.py --n N --seed S --out fipm-scale.db [--progress]`
builds a population directly into a fresh SQLite database (standard
library only — no test-suite dependency, so it can be run standalone to
produce a database for manual poking around). Per spec §8.2's recipe:

- a Zipf(s≈1.1) FER distribution over a 138-entry pool (a handful of FERs
  dominate, a long tail exists);
- 12% free-text answers from a 300-phrase pool with deliberate near-
  duplicates (case, whitespace, accents) so the convergence key (§1.5)
  earns its keep;
- the cell-state mix (25% unanswered, 5% not-applicable, 8% planned*, 3%
  none, the rest current);
- **30 cluster seeds** — 40% of FIPs are a 3-field mutation of one seed
  (over 6 of the questionnaire's questions), so genuine similarity clusters
  exist and LSH recall is measurable;
- **one hot-identical-declaration group**, sized `min(200, n // 3)` (so it
  never dominates a small `--n`) — the "a national mandate, or a template"
  case spec §4.4 guards against;
- a visibility mix (70% public / 20% link / 10% private), 50 sessions, 5
  knowledge-model versions;
- signatures and band rows (`fip_signatures`/`fip_signature_bands`,
  §4.2) and `fer_key_df` (§4.3), written via the same public
  `fipm.projection.write_signature_rows`/`bump_fer_key_df` helpers
  `reproject_fip` itself calls, so a generated database's signatures are
  byte-identical to what the live write path would have produced;
- `lsh_hot_buckets` (§4.4) refreshed once at the end, via
  `fipm.dashboard.similarity_views.refresh_hot_buckets`.

Bulk-inserted with `projection_suspended()` + `INSERT`, then projected in a
second pass — generation itself never goes through the per-request ORM
write hook, matching how a real `backfill-declarations` run behaves.

## `last-run.json` and `baseline.json`

`last-run.json` is overwritten by every scale-test run — it is the most
recent measurement, not accumulated history. `baseline.json` is written
once (if absent) and then used as a regression gate: a view's `wall_ms_at_n`
in a later run must stay under 3× the committed baseline's, or the test
fails. This catches a silent 5-10x regression; it does not catch a slow
drift, and it is not a substitute for reading `last-run.json` yourself
after a change to the hot path.

**To deliberately refresh the committed baseline** (e.g. after a real,
intentional performance change, or once real hardware numbers are
available per §7.4): delete `baseline.json` and re-run `uv run pytest -m
scale` once — the test writes a fresh one when none exists. Commit the
result.

## Known finding from the recorded baseline (N=2000, brief B)

`clusters`/`map` measured at ~13-14 seconds wall time at the default
N=2000 — far above the 3s soft ceiling, unlike the four base views (all
under 65 ms). This is the honest, load-bearing number the spec's §8.2
exists to produce, not a bug being hidden: the LSH-candidate rescoring path
(`fipm.dashboard.similarity_views._score_edges`) is pure-Python
`similarity.score_pair` calls over every candidate pair, fetched in one
batch rather than the spec §4.4 "batches of 5000" it describes. Recorded
here for §7.4's tuning pass; see the builder brief B report for the full
discussion of which `FIPM_DASHBOARD_LSH_PAIR_CAP`/batching changes this
measurement recommends.
