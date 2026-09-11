# Documentation

## Guides

- **[Running FIP Manager — A Guide for Administrators and Facilitators](administrator-guide.md)**
  Deploying and configuring an instance, preparing questionnaires in the knowledge-model editor,
  running a session, comparing the results, curating the FER catalogue, administering users,
  exports and RDF, the dashboard, the nanopublication network, and day-to-day operation —
  with a configuration reference, a CLI reference and troubleshooting.

- **[Filling in a FIP — A Guide for Participants](participant-guide.md)**
  A walkthrough for the person filling in a profile: what a FIP and a FER are, the ways to
  start, the five kinds of answer, statuses, saving and sharing, continuing on another device,
  and downloading the result. Assumes no technical background.

Both guides are available in English, European Portuguese, Brazilian Portuguese and Spanish:

| Guide | en | pt-PT | pt-BR | es |
|---|---|---|---|---|
| Administrators and facilitators | [en](administrator-guide.md) | [pt-PT](administrator-guide.pt-PT.md) | [pt-BR](administrator-guide.pt-BR.md) | [es](administrator-guide.es.md) |
| Participants | [en](participant-guide.md) | [pt-PT](participant-guide.pt-PT.md) | [pt-BR](participant-guide.pt-BR.md) | [es](participant-guide.es.md) |

Screenshots live in [`images/`](images/) and are shared by every language; regenerate them with
`scripts/capture-screenshots.mjs` against a running, demo-seeded instance.

## Workshop materials

- **[Facilitator script](workshop/facilitator-script.md)** — the 30-minute CONFOA 2026 runbook:
  pre-workshop checklist, minute-by-minute timeline, contingencies.
- **[Participant handout](workshop/participant-handout.md)** — the same ground as the
  participant guide compressed onto one printable page, in English and pt-PT.

## Project documents

- **[PLAN.md](PLAN.md)** — goals, data model, architecture, risks, decisions taken.
- **[ROADMAP.md](ROADMAP.md)** — week-by-week plan to the workshop, and the v2 list.
- **[AGENTS.md](AGENTS.md)** — agent roles and delegation policy for development.
- **[specs/](specs)** — implementation specifications, one per feature area. Internal design
  documents rather than user documentation.
- **[integration/](integration)** — the FioDMP API contract and OpenAPI description.
