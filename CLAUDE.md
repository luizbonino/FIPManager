# FIP Manager – working rules for Claude Code

Plan: docs/PLAN.md. Roadmap: docs/ROADMAP.md. Agent roles and rationale: docs/AGENTS.md.

## Delegation (token policy)
The main session is the orchestrator: it plans, delegates, integrates and reports. It does not read whole files or run searches itself when an agent can. Route by cost tier:

| Need | Agent | Model |
|---|---|---|
| Find files, excerpts, what the docs say | `scout` | haiku |
| Tick roadmap, format, validate JSON, i18n key parity | `scribe` | haiku |
| Implement a specified change + tests | `builder` | sonnet |
| Run tests/lint/build, reproduce bugs, add regression test | `verifier` | sonnet |
| pt-PT / pt-BR / es strings and questionnaire text | `translator` | sonnet |
| Data model, auth, API or versioning design; plan-vs-code drift | `architect` | opus |
| Review diffs for correctness and security | `reviewer` | opus |
| FIP ontology, RDF export, FER catalogue, maDMP mapping | `fair-expert` | opus |
| Escalation after two failed rounds | `arbiter` | fable |
| Bulk boilerplate, scaffolds, test stubs, first-draft translations, FER/JSON fixtures | `vibe-runner` | Mistral Vibe (external, via `scripts/vibe-task.sh`) |

Rules:
- Start every non-trivial change as: architect (only if design is open) → builder or vibe-runner → verifier → reviewer → scribe. Skip stages that add no information; never skip verifier for code.
- Prefer `vibe-runner` over `builder` when the task is boilerplate with clear acceptance criteria and no security surface; its tokens are billed to the Mistral plan. Everything it produces goes through `verifier` (code) or `translator` (text) before it counts as done.
- Give agents a precise brief: goal, files if known, acceptance criteria, what to return. Their report is the only thing that enters this context, so ask for what you need and nothing more.
- Run independent agents in parallel and in the background.
- Do not paste file contents into agent prompts if the agent can read them; pass paths.
- Pass prior agent reports, not the transcript, when escalating.
- Only `scribe` edits docs/ROADMAP.md; only the orchestrator or `architect` edits docs/PLAN.md.

## Project conventions
- Backend Python 3.12 / FastAPI / SQLAlchemy / rdflib; frontend Vue 3 + Vite + vue-i18n; Docker Compose. Questionnaires, FER catalogue and translations are JSON under data/, never hard-coded.
- Languages: en (source), pt-PT, pt-BR; es later. Fallback pt-PT ⇄ pt-BR → en.
- Every backend change has a pytest test. No commits unless asked.
- Deadline: code freeze Fri 3 Oct 2026 for the CONFOA workshop on 6 Oct. Anything not needed for the workshop is v2.
