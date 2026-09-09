# FIP Manager – Tool Plan

Status: draft v0.6, 2026-09-08. All four initial decisions closed; v0.5 added multi-user accounts and personal workspaces; v0.6 aligns statuses and FER types with the FIP ontology (see docs/specs/00-fip-ontology-mapping.md). Owners: L. O. Bonino da Silva Santos + 2 co-facilitators.
First milestone: FIP workshop at CONFOA 2026, Faro (PT), 6 October 2026.

## 1. Why a new tool

| Option | Verdict |
|---|---|
| FIP Wizard (fip-wizard.ds-wizard.org) | Locked to the full GO FAIR knowledge model. A self-hosted DSW with a forked model is possible but heavy, and offers no path to FioDMP integration. |
| REDCap at Fiocruz (redcap.icict.fiocruz.br, v14.5.8) | Generic survey tool. No FER concept, no FIP-shaped output, no link to FioDMP. Kept as zero-development fallback for the workshop only. |
| **FIP Manager (this project)** | Editable, multilingual FIP questionnaire; FIP-shaped output (JSON, CSV, RDF per FIP ontology); designed to link with FioDMP. |

## 2. Goals

1. Let a community (or a workshop group) declare a FAIR Implementation Profile by answering an editable questionnaire.
2. Use the GO FAIR FIP mini-questionnaire v2.0.0 as-is (21 questions, 12 FER types; content licensed CC BY-SA 4.0 by the GO FAIR Foundation, attribution required) for the workshop. Treat the questionnaire as an editable, versioned *knowledge model* in the DSW sense: editors can translate, reorder, hide, add or split questions and publish a new version without code changes; every FIP records which version it answers.
3. Be multilingual from day one: English (`en`), European Portuguese (`pt-PT`) and Brazilian Portuguese (`pt-BR`), for the interface *and* the questionnaire content. Default language comes from the browser's locale; English is the fallback. Spanish (`es`, a FioDMP language) was added as a draft on 9 Sep 2026 (UI, questionnaire and FER types); fallback es → en.
4. Produce standards-based output: JSON, CSV, RDF/Turtle following the FIP ontology (https://w3id.org/fair/fip/terms/), nanopublications later.
5. Integrate bidirectionally with FioDMP (https://fiodmp.fiocruz.br): a DMP can cite a FIP, and a FIP can point at answers in a DMP.
6. Work well in a room: participants need no account, join by link, live side-by-side comparison of the FIPs produced by the groups.
7. Be multi-user from day one: anyone can create an account and gets a personal workspace holding their own FIPs, workshop sessions, knowledge-model versions and FER additions. Everything outside a workshop session belongs to a user; a workshop session is a workspace object that accepts anonymous contributions by link.

Non-goals for v1: replacing the FIP Wizard for full GO FAIR FIP publication, team or organisation workspaces, single sign-on, FER curation at scale.

## 3. What we learned about FioDMP (integration target)

- Custom Laravel application built by ICTIC/Fiocruz (not DSW, DMPonline or Argos). Login via "Login Único Fiocruz" or local account. UI in PT-BR, EN, ES.
- Public plans are addressed by short IDs: `https://fiodmp.fiocruz.br/{ID}` (e.g. KQU5N0C), versioned ("Versão: 13"). Only export found: `/publico/{ID}/pdf`. No public JSON, maDMP or API was found.
- Four templates: *Modelo Simplificado*, *Modelo Detalhado*, *PGD – Modelo FAIR*, *Pesquisa Clínica – Modelo Detalhado*. Sections A (admin), B (data), C (metadata), D (storage/security), E (ethics/legal), F (sharing/licence/identifier), G (resources/roles).
- Consequence: the DMP→FIP direction needs a small API (or JSON export) on the FioDMP side. We will propose an API contract to the ICTIC team (see §6). The FIP→DMP direction works today by URL.

## 4. Core concepts and data model

Users and workspaces. A `User` (email, password hash, display name, role `user | admin`, preferred language) owns one implicit personal workspace: every `KnowledgeModel`, `FIP`, `Session` and user-contributed `FER` carries an `ownerId`. System content (the GO FAIR model, the seed FER catalogue) has no owner and is read-only for everyone except admins. Each owned object has a `visibility`: `private` (owner only), `link` (anyone with the URL can read), `public` (listed). FIPs created anonymously inside a workshop session have `ownerId = null`, belong to the session, and carry an `editToken` (kept in the participant's browser) so only that device can edit them; a signed-in participant can *claim* such a FIP into their workspace at any time.

Knowledge model (DSW-style). The questionnaire is a versioned knowledge model: `gofair-fip-mini` v1.0.0 is the untouched GO FAIR questionnaire; edits produce new versions (semantic versioning, changelog per version). A FIP always points to one version. Migrating a FIP to a newer version (as DSW does for projects) is a v2 feature; in v1 old FIPs simply keep answering the version they were created with.

```
User                               Session (workshop)
├─ id, email, passwordHash         ├─ id, joinCode, ownerId (facilitator)
├─ displayName, role, language     ├─ questionnaireRef, defaultLanguage
└─ createdAt                       ├─ title, status: open | closed
                                   └─ fips[] (anonymous or owned)

Questionnaire / Knowledge model    FIP (an instance)
├─ id, version, status            ├─ id (short, URL-stable), version
├─ ownerId | null (system)        ├─ ownerId | null, sessionId | null, editToken
├─ visibility                     ├─ visibility
├─ title{lang}, description{lang} ├─ questionnaireRef (id+version)
└─ sections[]                     ├─ community{ name, description, links, domain, dataSteward(ORCID) }
   └─ questions[]                 ├─ relatedDMPs[] { url, version, system:"FioDMP" }
      ├─ id (e.g. F1-metadata)    ├─ answers[] (one per question)
      ├─ principle (F1…R1.3)      │   ├─ questionId
      ├─ scope (metadata|data|-)  │   ├─ declarations[]
      ├─ text{lang}, help{lang}   │   │   ├─ fer (ref to FER or free text)
      ├─ ferType                  │   │   ├─ status: current | planned | planned-development | planned-replacement | none
      └─ required, allowMultiple  │   │   └─ note{lang}, dmpEvidence (DMP url + question ref)
                                  │   └─ comment
FER (FAIR Enabling Resource)      └─ createdAt, updatedAt, language, license
├─ id (IRI, nanopub if known)
├─ label{lang}, type (12 FER types), homepage
├─ ownerId | null (seed)
└─ source: seed | user | nanopub
```

User-contributed FERs are visible in their owner's workspace and in any FIP that uses them; an admin can promote one to the global catalogue.

The declaration statuses mirror the FIP ontology one-to-one: `current` → `fip:declares-current-use-of`, `planned` → `fip:declares-planned-use-of`, `planned-development` → `fip:declares-planned-development-of`, `planned-replacement` → `fip:declares-planned-replacement-of`, and `none` → a `fip:FIP-No-Choice-Declaration`. The earlier "considered" state was dropped on 8 Sep because the ontology has no such term; deliberation goes into the declaration's `note`, exported as `fip:considerations`. Question ids follow the ontology: F1, F4, A1.1, A1.2, I1, I2, I3, R1.1 and R1.2 have metadata and data variants; F2, F3 and A2 are unscoped; there is no R1.3 question (the community description answers it). Verified terms, IRIs and a Turtle example are in docs/specs/00-fip-ontology-mapping.md.

## 5. Functional scope

### v1 (workshop, by 3 Oct)
- Accounts: register with email and password, sign in/out, change password, delete account. Personal workspace with three lists: my FIPs, my sessions, my knowledge models. Visibility per object (private / link / public). Admin role: list users, reset a password, promote a FER, manage system knowledge models.
- Facilitator (any signed-in user): create workshop session, pick questionnaire version, get join link/QR code, see all FIPs of the session in a comparison matrix (principle × group), export all.
- Participant/group: open link (no account needed), name the community, answer questions (pick a FER from the seed catalogue or type a new one, set status), save, share FIP URL, export JSON/CSV, print view. The device that created the FIP keeps its edit token; a participant who signs in can claim the FIP into their own workspace.
- Signed-in user outside a session: create a FIP directly from any published knowledge model in their workspace.
- Knowledge model editor (in the owner's workspace): edit texts in all languages, hide/unhide, reorder, add or split questions, change FER type, publish as a new version with changelog. JSON import/export. Three ways to start a model: **fork** an existing one (e.g. GO FAIR 1.0.0, which itself is read-only), **create from scratch** (empty model, add sections and questions), or **import** a JSON file. Questions in a from-scratch model may still be tagged with FAIR principle and FER type so the comparison matrix and RDF export keep working; untagged questions are exported as plain answers.
- i18n: UI strings and questionnaire content in `en`, `pt-PT`, `pt-BR` (BCP 47 tags). Default from the browser's `Accept-Language` / `navigator.languages`, English as fallback; fallback chain `pt-PT ⇄ pt-BR → en` so a string missing in one Portuguese variant borrows the other before English. Manual switcher overrides and is remembered per browser. Per-FIP language recorded; a workshop session may pin a default language.
- FER seed catalogue: ~60 common FERs (DOI, Handle, PURL, ORCID, Dublin Core, DCAT, schema.org, DataCite, ISO 19115, HTTPS, OAI-PMH, SPARQL, OAuth2/OIDC, RDF, OWL, SKOS, JSON-LD, CC0/CC BY variants, PROV-O, DataCite Commons, Google Dataset Search, B2FIND…), typed by FER type.
- RDF export (Turtle/JSON-LD) using the FIP ontology.

### v2 (post-workshop, Oct–Dec 2026)
- ~~FioDMP link: paste a FioDMP URL, validate it, store id+version; per-answer evidence pointing to a DMP section/question; embeddable FIP summary + `GET /api/fips/{id}` for FioDMP to render.~~ Done 9 Sep (docs/specs/06-dmp-linkage.md; contract draft in docs/integration/).
- Prefill from DMP once FioDMP exposes JSON (mapping table in §6).
- FER lookup in the nanopublication network (Nanopub Query) and publish FIPs as nanopublications (Python `nanopub` library).
- ~~FIP migration between knowledge-model versions (DSW-style), with a diff view of changed questions.~~ Done 9 Sep (docs/specs/07-mail-and-migration.md).
- ~~Successor FER on `planned-replacement` declarations~~ Done 9 Sep (docs/specs/05-v1-completion.md).
- Sign-in with ORCID and Login Único Fiocruz next to email/password. ~~Email verification and self-service password reset~~ done 9 Sep; active once FIPM_MAIL_BACKEND=smtp is configured.
- Team workspaces: share a session, FIP or knowledge model with named collaborators; public gallery of FIPs.

## 6. FioDMP ↔ FIP Manager integration design

**FIP → DMP (works with FioDMP as-is):** a FIP stores one or more `relatedDMPs` by URL and version. Individual declarations can carry `dmpEvidence` (URL + section letter / question text) so a FIP answer such as "Dublin Core for F2" is justified by Section C of the DMP.

**DMP → FIP (needs ICTIC cooperation):**
1. FioDMP adds an optional field "FAIR Implementation Profile (URL)" to its templates, or to the *PGD – Modelo FAIR* template first.
2. FIP Manager exposes `GET /api/fips/{id}` (JSON) and `GET /fips/{id}/embed` (compact HTML summary) so FioDMP can display the FIP next to the plan.
3. FioDMP exposes `GET /api/plans/{id}` (JSON, ideally RDA maDMP) so FIP Manager can prefill a FIP from an existing DMP. Proposed mapping:

| FioDMP section / question | FIP question |
|---|---|
| C – metadata standard adopted | F2 metadata schema, I3 metadata schema |
| F – licence applied to the data | R1.1 licence (data) |
| F – persistent identifier (DOI) registration | F1 identifier (data) |
| F – sharing channel (repository) | F4 search engines / registries, A1.1 protocol |
| B – provenance recording method | R1.2 provenance model |
| D – storage locations | A1.2 authentication & authorisation (partial) |

Deliverable to ICTIC: a 2-page API contract (OpenAPI) + this mapping, to be discussed after the workshop.

## 7. Architecture

- **Backend:** Python 3.12, FastAPI, SQLite (Postgres-ready via SQLAlchemy), `rdflib` for RDF export, `nanopub` later. OpenAPI generated for free (useful for the ICTIC conversation).
- **Frontend:** Vue 3 + Vite + vue-i18n, single-page app served by the backend. Works on phones/tablets (participants will use them).
- **Content as data:** questionnaires, FER seed catalogue and translations live in versioned JSON files under `data/`, importable into the DB. Nothing about the questionnaire is hard-coded.
- **Deployment:** Docker Compose, one container + volume, fully domain-agnostic (base URL, FIP identifier prefix and branding come from environment variables). Two hosting candidates, decision pending: one of the FAIR-related domains owned by L. O. Bonino, or a Fiocruz domain hosted by ICTIC. FIP URLs must stay stable after the workshop, so if the tool starts on a FAIR domain and later moves to Fiocruz, the old domain keeps redirecting. Offline fallback: run the container on a facilitator laptop with a local Wi-Fi hotspot.
- **Identity:** email + password accounts from v1. Passwords hashed with argon2id; server-side sessions in an HttpOnly, SameSite cookie; CSRF protection on state-changing requests; login rate limiting. Roles `user` and `admin`; the first admin is created from environment variables at startup. Workshop participants stay anonymous and are identified by a per-FIP edit token stored in the browser. Email verification and self-service password reset depend on SMTP settings; without SMTP, an admin resets passwords. ORCID and Login Único Fiocruz are v2.
- **Authorization:** every read and write is checked against `ownerId`, `visibility`, session membership (join code) or edit token. Anonymous access exists only through a session join link or a `link`/`public` object URL.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Room Wi-Fi fails | Laptop-hosted container + hotspot; printed questionnaire as last resort. |
| Translations wrong or late | EN is the source; facilitators review pt-PT and pt-BR by W3; per-string fallback pt-PT ⇄ pt-BR → en. |
| Scope creep before 6 Oct | Freeze v1 scope on 12 Sep; anything else goes to v2. |
| FioDMP has no API | Integration v2 designed to work by URL first; prefill only when API exists. |
| FER catalogue too thin | Free-text FER always allowed; catalogue grows from workshop input. |
| Accounts and workspaces add 2–3 days to weeks 1–2 | Keep auth minimal (email + password, no verification at launch); if week 2 slips, move the knowledge model editor to v2, since the workshop uses the GO FAIR model as-is. |
| Account data is personal data (EU workshop) | Privacy notice on sign-up and join pages; store only email, name, password hash; self-service account deletion. |

## 9. Open decisions (need the three facilitators)

1. ~~Which questions to hide for the workshop version~~ Decided 8 Sep: use the GO FAIR questionnaire as-is; the knowledge model stays editable for later.
2. ~~Language default~~ Decided 8 Sep: browser locale decides, English is the fallback; languages at launch are en, pt-PT, pt-BR (es later). Groups answer in whichever language their browser or the switcher gives them.
3. Hosting: one of L. O. Bonino's FAIR-related domains, or a Fiocruz domain via ICTIC. Decide by 26 Sep so week 4 can deploy; the build is domain-agnostic either way.
4. ~~Licence~~ Decided 8 Sep: the tool is MIT (see `LICENSE`). Exported FIPs default to CC0 1.0, shown on the export and editable per FIP.
5. Sign-up policy at launch: open registration, or invite-only (admin creates accounts) to avoid spam before SMTP-based verification exists. Default if undecided: open registration with a rate limit.
6. Whether CONFOA participants are encouraged to create accounts and claim their group's FIP after the workshop (recommended: yes, mention it on the closing slide).
7. Content licence: the GO FAIR questionnaire text is CC BY-SA 4.0, so the `gofair-fip-mini` knowledge model, forks of it and FIP exports that embed its question texts must carry CC BY-SA 4.0 with attribution (GO FAIR Foundation, CODATA; Schultes, Magagna, Schultes 2020/2023). The MIT licence covers the code only. Proposed: a `data/knowledge-models/LICENSE` note plus a UI footer credit; exported FIP *answers* stay CC0 by default. Needs facilitator confirmation.
8. Assumptions taken on 8 Sep while facilitators were away (see docs/specs/01-foundations.md §9): one FIP per group in a session; open registration with rate limit behind a config flag; anonymous session FIPs default to `link` visibility so the room can compare; account deletion anonymises FIPs rather than deleting them.
