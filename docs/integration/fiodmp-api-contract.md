# FIP Manager ↔ FioDMP — proposed API contract

Draft 1, 2026-09-09 · L. O. Bonino da Silva Santos (University of Twente) · for the ICTIC/Fiocruz FioDMP team
Companion files: `fiodmp-openapi.yaml` (OpenAPI 3.1, both sides) · `../specs/06-dmp-linkage.md` (what FIP Manager builds)

## Resumo (pt-BR)

O FIP Manager é uma ferramenta aberta (MIT) que permite a uma comunidade declarar o seu **FAIR Implementation Profile** (FIP): 21 perguntas
sobre os recursos que a comunidade usa para cumprir cada princípio FAIR, com exportação em JSON, CSV e RDF. Queremos ligá-lo ao **FioDMP**
nas duas direções. A direção **FIP → PGD** já funciona hoje: um FIP guarda um ou mais URLs de planos (`https://fiodmp.fiocruz.br/{ID}`) e cada
declaração pode citar a secção e a pergunta do plano que a justifica. A direção **PGD → FIP** precisa de uma pequena API do lado do FioDMP:
um `GET /api/plans/{id}` devolvendo JSON no padrão **RDA DMP Common Standard (maDMP) 1.1**, mais um campo opcional no plano com o URL do FIP.
Com isso, o FIP Manager consegue pré-preencher um FIP a partir de um PGD existente (§4 mostra o mapeamento campo a campo) e o FioDMP consegue
mostrar o FIP ao lado do plano (uma página HTML pronta a embutir, §2). Nada é obrigatório para planos privados: propomos começar apenas com
planos públicos, sem autenticação (§5). Este documento é a base para uma reunião de 60 minutos (§7).

## 1. Purpose and the two directions

FIP Manager (built for the FIP workshop at CONFOA 2026, Faro, 6 Oct 2026) records, per community, which FAIR Enabling Resources it uses for
each of the 21 FIP questions, with a status of `current`, `planned`, `planned-development`, `planned-replacement` or `none`. A DMP says what a
project *will do*; a FIP says what a community *has standardised on*. Linked, they answer each other's weakest question: a DMP gains
justification for its metadata, identifier and licence choices; a FIP gains evidence that the choices are actually in use.

| Direction | Status | What it needs |
|---|---|---|
| **FIP → DMP** | works today, no FioDMP change | FIP Manager stores plan URLs and per-declaration evidence (§2 of spec 06) |
| **DMP → FIP** | blocked | a read-only JSON endpoint on FioDMP (§3) and one optional plan field pointing at a FIP |

We looked for a machine-readable export on FioDMP (Sep 2026) and found only `/publico/{ID}/pdf`. Everything in §3 is therefore a proposal,
sized to be small: one endpoint, one optional field, one versions list. If FioDMP prefers to expose its **own** JSON instead of maDMP, that is
acceptable — the mapping cost moves to us — provided the field names are documented and stable.

## 2. What FIP Manager exposes for FioDMP (implemented in v2, Nov 2026)

All three are readable without authentication for a FIP whose `visibility` is `public` or `link` (a FIP that is `private` returns 404 to
anyone but its owner). Base URL to be fixed when hosting is decided; assume `https://fipm.example.org` until then.

| Endpoint | Media type | Use in FioDMP |
|---|---|---|
| `GET /api/fips/{id}` | `application/json` | render the FIP inside a Blade template (server-side fetch) |
| `GET /fips/{id}/embed` | `text/html` | drop-in `<iframe>`: compact summary, no JS, inline CSS, responsive |
| `GET /api/fips/{id}/export.jsonld` | `application/ld+json` | RDF (FIP Ontology `https://w3id.org/fair/fip/terms/`); `export.ttl` for Turtle |

`GET /api/fips/{id}` (full schema in the OpenAPI file) returns camelCase: `id`, `visibility`, `questionnaireId`, `questionnaireVersion`,
`language`, `license`, `updatedAt`, `community` (`name`, `description`, `domain`, `dataSteward.orcid`), `relatedDmps[]`
(`url`, `version`, `system`, `dmpId`), `answers[]` (`questionId`, `declarations[]` with `ferId`/`ferFreeText`, `status`, `note`,
`dmpEvidence`), plus two fields added for this integration: **`embedUrl`** (the §2 iframe URL) and **`summary`**
(`answeredQuestions`, `totalQuestions`, `declarations`, `byStatus`) — enough for a one-line badge such as "FIP: 18/21 answered, 14 in use"
without parsing the answers.

The embed is framed by FioDMP, so FIP Manager sends `Content-Security-Policy: … frame-ancestors 'self' https://fiodmp.fiocruz.br`
(configurable). **Please tell us the exact origin(s)** that will frame it. There is no CORS header on `/api/*`: fetch it server-side, or ask us
to allow the FioDMP origin explicitly.

## 3. What we ask FioDMP to expose

### 3.1 `GET /api/plans/{id}` → RDA maDMP 1.1 JSON

Standard: **RDA DMP Common Standard** — https://github.com/RDA-DMP-Common/RDA-DMP-Common-Standard (machine-actionable DMP, version 1.1;
JSON Schema in `examples/JSON/JSON-schema/1.1/`). `{id}` is the short public plan id already in the URL (e.g. `KQU5N0C`). Response
`{"dmp": { … }}`, `Content-Type: application/json`, no authentication for a plan that is already public (§5).

Minimal subset we can work with (everything else in maDMP is welcome but unused):

| maDMP path | Why we need it |
|---|---|
| `dmp.dmp_id` `{identifier, type}`, `dmp.title`, `dmp.modified`, `dmp.language` | identity, freshness, and the FIP's language |
| `dmp.contact.contact_id` `{identifier, type: "orcid"}` | the community's data steward |
| `dmp.dataset[].dataset_id` `{identifier, type}`, `dataset[].title` | F1 (data) — which identifier service is in use |
| `dmp.dataset[].metadata[].metadata_standard_id` `{identifier, type}` | F2, I3 — metadata schema / semantic model |
| `dmp.dataset[].distribution[].license[].license_ref` | R1.1 — data usage licence |
| `dmp.dataset[].distribution[].host` `{title, url, pid_system[], availability}` | F4, F1, A1.1 — registry, identifier service, protocol |
| `dmp.dataset[].distribution[].data_access`, `dataset[].security_and_privacy[]` | A1.2 — authentication & authorisation |
| `dmp.dataset[].distribution[].format[]` | I1 — knowledge representation language |
| `dmp.dataset[].preservation_statement`, `distribution[].available_until` | A2 — metadata preservation policy |

Nice to have: `ETag` + `If-None-Match` (we poll nothing, but prefill would re-read on demand), and a documented rate limit (60 req/min is
plenty). A 404 for an unknown or non-public plan is fine; please do not distinguish "private" from "absent" in the body.

### 3.2 One optional plan field: the FIP URL

We ask FioDMP to add an optional field **"FAIR Implementation Profile (URL)"** to its templates — starting with *PGD – Modelo FAIR*, Section
A — and to expose it in the JSON. Two shapes work for us; ICTIC picks one:
`dmp.fair_implementation_profile: "https://fipm.example.org/fips/7Q2M8XKD"` (simplest) or
`dmp.extension: [{"fiodmp": {"fair_implementation_profile": "…"}}]` (keeps the plan valid against a strict maDMP schema).
That single field makes the link bidirectional and lets FioDMP render the §2 iframe next to the plan.

### 3.3 `GET /api/plans/{id}/versions` → the version list

FioDMP plans are versioned ("Versão: 13") and a FIP declaration cites a *version* as evidence. We ask for
`{"plan_id": "KQU5N0C", "versions": [{"version": "13", "modified": "2026-05-14T10:02:00Z", "url": "https://fiodmp.fiocruz.br/KQU5N0C"}]}`,
newest first, plus — ideally — `GET /api/plans/{id}?version=12` for an older revision. If versions are not addressable, we store the version
string as a label only and say so in the UI.

## 4. Mapping: maDMP → FIP questions

Extends the table in `docs/PLAN.md` §6 (FioDMP sections A–G) to maDMP paths. Confidence says how safely a prefill can propose the answer:
**high** = propose it, **medium** = propose it flagged for review, **low** = show as a hint only, never as a declaration.

| maDMP path | FIP question (FER type) | Conf. |
|---|---|---|
| `dataset[].dataset_id.type` (`doi`, `handle`, `ark`, `url`) | F1-data — identifier service | high |
| `distribution[].host.pid_system[]` | F1-metadata / F1-data — identifier service | high |
| `dataset[].metadata[].metadata_standard_id.identifier` | F2 — metadata schema | high |
| `dataset[].metadata[].metadata_standard_id.identifier` | I3-metadata — semantic model | medium |
| `distribution[].host.title` + `host.url` | F4-metadata / F4-data — registry | high |
| `distribution[].access_url` scheme, `host.availability` | A1.1-metadata / A1.1-data — communication protocol | medium |
| `distribution[].data_access` (`open\|shared\|closed`) + `dataset[].security_and_privacy[].title` | A1.2-metadata / A1.2-data — auth service | medium |
| `dataset[].preservation_statement`, `distribution[].available_until`, `host.backup_type` | A2 — metadata preservation policy | medium |
| `distribution[].format[]` (IANA media types) | I1-data — knowledge representation language | medium |
| `dataset[].keyword[]`, `dataset[].metadata[].description` | I2-metadata / I2-data — structured vocabulary | low |
| `distribution[].license[].license_ref` | R1.1-data — data usage licence | high |
| `dataset[].data_quality_assurance[]` | R1.2-metadata / R1.2-data — provenance model | low |
| `dmp.title`, `dmp.description` | community `name`, `description` | high |
| `dmp.contact.contact_id.identifier` (ORCID) | community `dataSteward.orcid` | high |
| `dmp.project[].title` | community `domain` | low |
| `dmp.language` (ISO 639-3: `eng`, `por`, `spa`) | FIP `language` (`en`, `pt-BR`, `es`) | high |
| `dmp.dmp_id.identifier` | the FIP's `relatedDMPs[].url` (not an answer) | high |
| `dmp.fair_implementation_profile` (§3.2) | the reverse link, DMP → FIP | – |

Prefill semantics, so nothing is silently invented: every proposed declaration gets `status: "current"` (a DMP describes what the project
does), a `note` naming the maDMP path it came from, and a `dmpEvidence` pointing at the plan and version. Nothing is stored until the user
confirms it on a review screen; **low**-confidence rows are never pre-selected. Values are matched against FIP Manager's ~60-entry FER
catalogue by IRI and label, and otherwise kept as free text.

## 5. Authentication

- **Public plans: none.** A plan already readable at `https://fiodmp.fiocruz.br/{ID}` is readable at `/api/plans/{ID}`. This covers the pilot.
- **Private plans: bearer token, out of scope for v1** of the integration. If ICTIC wants it later, the smallest workable shape is an
  opaque per-user token (`Authorization: Bearer …`) issued in the FioDMP UI, scoped to that user's plans, revocable, and passed by FIP Manager
  only on an explicit "prefill from my private plan" action. OAuth2/Login Único Fiocruz would be the fuller answer; FIP Manager already plans
  Login Único sign-in (PLAN §5 v2), so a later authorisation-code flow is not wasted work.
- FIP Manager side: `GET /api/fips/{id}` and the embed need no token for `public`/`link` FIPs; `private` FIPs are simply invisible.

## 6. Privacy

FIP Manager stores, per linked plan, **only** `url`, `version`, `system` and the short id — never plan content. During a prefill the fetched
plan is held in memory, mapped to *proposed* declarations, and discarded; only what the user confirms is stored, in a FIP that is CC0 by
default and visible per its own `visibility`. Personal data in a plan (contact name, e-mail, contributors) is **not** copied; the data
steward's ORCID is offered as a suggestion the user must accept. Logs record the plan id and status code, not the plan body. FIP Manager holds
accounts with e-mail, display name and password hash only, offers self-service deletion, and is hosted either in the EU or by ICTIC
(undecided, PLAN §9.3) — relevant to both GDPR and the LGPD, and worth a line in each side's privacy notice.

## 7. Proposed sequence (Oct–Dec 2026) and questions for the meeting

| When | Who | What |
|---|---|---|
| 13–17 Oct | us | send this document + `fiodmp-openapi.yaml`; book a 60-minute call |
| by 31 Oct | both | call: confirm the two directions, pick the §3.2 field shape, ICTIC sizes §3.1; agree a pilot plan id |
| November | us | ship spec 06 (plan links, per-declaration evidence, embed, `summary`) on a stable URL; mock-based prefill behind a flag |
| November | ICTIC | add the FIP URL field to *PGD – Modelo FAIR*; render the embed next to a plan (one `<iframe>`) |
| Nov–Dec | ICTIC | prototype `GET /api/plans/{id}` on staging (2 public plans is enough to start) |
| December | both | joint test with 3 real plans; measure how many of the 21 questions a plan can actually prefill; short joint report |

Open questions: (1) Does FioDMP embed third-party HTML at all, or would you rather render `GET /api/fips/{id}` yourselves — and from which
origin(s)? (2) maDMP 1.1, or a FioDMP-native JSON you already have internally? (3) Where does the FIP URL live — a template question, or a
plan attribute independent of the template — and is it per version? (4) Are plan versions addressable (`?version=12`), and are version numbers
stable? (5) Is a public-plans-only, unauthenticated read acceptable for the pilot? (6) Who hosts FIP Manager long-term — a FAIR-related domain
or a Fiocruz domain (PLAN §9.3)? FIP URLs must stay stable either way. (7) Which plans (and which template) do we use for the December test?
