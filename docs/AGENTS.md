# FIP Manager – Multi-agent setup

Purpose: keep the expensive orchestrator context small by routing each kind of work to the cheapest model that does it reliably. Definitions live in `.claude/agents/*.md`; the routing policy the orchestrator follows is in `CLAUDE.md`.

## Roles by model tier

| Tier | Strength | Agents | Typical brief |
|---|---|---|---|
| Haiku 4.5 | Fast, cheap, good at lookup and mechanical edits | `scout`, `scribe` | "Where is the FIP export code?" / "Tick roadmap item X, validate data/fers/seed.json" |
| Sonnet 5 | Reliable coding and language work at moderate cost | `builder`, `verifier`, `translator` | "Implement POST /api/fips per docs/specs/fips.md, criteria 1–5" / "Translate these 14 new keys" |
| Opus 5 | Deep reasoning, careful review, domain precision | `architect`, `reviewer`, `fair-expert` | "Spec the edit-token and claim flow" / "Review the auth diff" / "Map declaration statuses to FIP ontology terms" |
| Fable 5.1 | Strongest; orchestrator and rare escalation | main session, `arbiter` | Plan, delegate, integrate; arbitrate a builder/reviewer disagreement |
| Mistral Vibe (external) | Separate token budget; capable coding model (mistral-medium-3.5) for bulk work | `vibe-runner` (haiku driver) | "Scaffold CRUD endpoints for Session per spec" / "Draft pt-BR for these 40 keys" / "Generate 60 FER seed entries in this JSON shape" |

Each agent has a capped report length and a fixed report shape so the orchestrator receives conclusions, not file dumps. `scout` and `reviewer` are read-only. `architect` writes only under `docs/specs/`. `fair-expert` writes only under `data/`, `docs/` and the RDF export module. Only `scribe` edits `docs/ROADMAP.md`.

## Standard pipeline for a change

1. **architect** (opus) – only when the design is open. Writes `docs/specs/<topic>.md` with acceptance criteria.
2. **builder** (sonnet) – implements against the spec, runs targeted tests, reports diff summary and results.
3. **verifier** (sonnet) – independently runs the suite and checks each criterion; adds missing regression tests.
4. **reviewer** (opus) – mandatory for auth, authz, cookies, CSRF, edit tokens, visibility, SQL, exports. Optional elsewhere.
5. **scribe** (haiku) – ticks the roadmap, updates status lines.
6. **arbiter** (fable) – only after two failed rounds of 2–4, with the prior reports pasted in.

`vibe-runner` can replace `builder` in step 2 for boilerplate with no security surface; its output is never trusted without step 3.

Translations run in parallel with steps 2–3 whenever user-facing text changes. `fair-expert` is consulted before step 1 for anything about FIP/FER representation or RDF.

## Token-saving rules the orchestrator follows

- Delegate every search and every whole-file read; read directly only a known small range when the answer is one fact.
- Pass paths and criteria, not file contents. Agents read files themselves.
- Ask for a specific report shape; agents are instructed to cap output and paste only failing test output verbatim.
- Run independent agents concurrently in the background.
- Escalate with reports, not transcripts.
- Reuse a running agent by SendMessage when a follow-up needs its context; start fresh otherwise.

## Mistral Vibe integration

- Installed with `uv tool install mistral-vibe` (binary at `~/.local/bin/vibe`) and symlinked system-wide into `/opt/homebrew/bin/vibe` and `vibe-acp`, so `vibe` resolves for every shell and for the VS Code extension. Reinstall or upgrade with `uv tool upgrade mistral-vibe`. Authenticated through the Mistral account already used by the VS Code extension; the current plan is the free tier, so expect rate limits on long runs.
- `scripts/vibe-task.sh` runs Vibe in programmatic mode (`-p`, `--auto-approve`, `--output json`, `--max-turns`, `--max-price`) and prints only the final assistant message, so the calling agent's context stays small. `--readonly` restricts Vibe to read and search tools.
- Vibe never touches docs/PLAN.md, docs/ROADMAP.md or authentication code. The `vibe-runner` agent enforces this in its prompt; `reviewer` is the safety net.
- If the free-tier limits bite, either add a Mistral API key in `~/.vibe/config.toml` or route the task to `builder` (sonnet).

## Adjusting

- A role is under-powered if it produces repeated verifier failures or reviewer findings: move it one tier up in its frontmatter `model:` line.
- A role is over-powered if its output is trivially mechanical: move it down.
- `effort:` (low/medium/high/xhigh/max) is the second lever; change it before changing the model.
