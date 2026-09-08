# FIP Manager – Roadmap

Today: Mon 8 Sep 2026. Workshop: Tue 6 Oct 2026, CONFOA, Faro. Scope freeze for v1: Fri 12 Sep. Code freeze: Fri 3 Oct.

## Week 1 · 8–12 Sep · Foundations
- [x] Questionnaire: GO FAIR mini-questionnaire as-is, editable knowledge model (decided 8 Sep).
- [x] Licence: MIT for the tool, CC0 default for exported FIPs (decided 8 Sep).
- [ ] Shortlist hosting (FAIR domain vs Fiocruz) — see PLAN.md §9.
- [x] Repo scaffold: FastAPI + Vue 3 + Docker Compose, CI workflow for tests and build (done 8 Sep; CI runs once a GitHub remote exists).
- [x] Data model implemented (User, Questionnaire, FIP, FER, Session) with ownership and visibility fields, JSON import/export (done 8 Sep, docs/specs/01-foundations.md).
- [x] Accounts: register, sign in/out, argon2id hashing, cookie sessions, CSRF, roles user/admin, first admin from env (done 8 Sep; review fixes in progress).
- [x] Languages: en, pt-PT, pt-BR at launch; browser locale default, English fallback (decided 8 Sep).
- [x] `data/knowledge-models/gofair-fip-mini-1.0.0.json`: the 21 GO FAIR questions in en, with pt-PT and pt-BR drafts (done 8 Sep; 12 FER types in `data/fers/fer-types.json`; content is CC BY-SA 4.0, see PLAN §9.7).
- [x] `data/fers/seed.json`: 69 typed FERs (done 8 Sep; needs a FAIR-expert spot check of IRIs).
- [x] Deliverable: running skeleton where a user can register, sign in, create a FIP and read it back via API (done 8 Sep; 14/14 acceptance criteria verified, Docker image runs).

## Week 2 · 15–19 Sep · Core flows
- [x] Participant flow: join session by link, fill questionnaire, pick/enter FERs with status, save, get FIP URL (done 8 Sep, docs/specs/02-core-flows.md; verified in a 375 px browser run).
- [x] i18n wiring: UI strings in en, pt-PT, pt-BR (191 keys, parity checked); questionnaire content per language; browser-locale detection with English fallback; switcher remembered per browser (done 8 Sep; Portuguese is a draft pending facilitator review).
- [x] Export FIP as JSON and CSV; print view (done 8 Sep; CSV has a formula-injection guard).
- [x] Personal workspace: my FIPs, my sessions, my knowledge models; visibility private / link / public; change password; delete account (done 8 Sep).
- [x] Anonymous session FIPs: per-FIP edit token in the browser; signed-in user can claim a FIP into their workspace (done 8 Sep).
- [x] Facilitator flow (signed-in user): create session, choose questionnaire version, join link + QR, live list of FIPs, export all, close (done 8 Sep).
- [ ] Deliverable: end-to-end demo with a colleague on a phone (automated phone-viewport run passed 8 Sep; a real phone and a real colleague still needed).

## Week 3 · 22–26 Sep · Workshop features and content
- [ ] Comparison matrix (principle × group) with per-principle convergence view; export all FIPs of a session.
- [ ] Knowledge model editor in the owner's workspace (texts, hide/show, reorder, add, FER type, publish new version with changelog). First candidate to move to v2 if week 2 slips.
- [ ] RDF/Turtle + JSON-LD export following the FIP ontology.
- [ ] Facilitators review pt-PT and pt-BR translations of the GO FAIR model.
- [ ] Hosting decision (FAIR domain vs Fiocruz) taken by Fri 26 Sep.
- [ ] Deliverable: dry run of the whole workshop exercise (30 min) with the three facilitators.

## Week 4 · 29 Sep–3 Oct · Hardening and deployment
- [ ] Deploy to the chosen domain with HTTPS; backup script for the SQLite file; base URL from env so a later move to Fiocruz keeps FIP IDs.
- [ ] Admin pages: list users, reset password, promote user FER to global catalogue.
- [ ] Privacy notice on sign-up and join pages; login rate limiting checked.
- [ ] Register the `fipm` w3id (https://w3id.org/fipm/ns#) used by the RDF export's extension vocabulary; publish a terms page.
- [ ] Offline fallback tested: container on laptop + hotspot.
- [ ] Bug fixing from dry run; loading/latency check with ~40 concurrent users.
- [ ] Slides and facilitator script referencing the tool; printed questionnaire fallback.
- [ ] Fri 3 Oct: code freeze, tag `v1.0-confoa`.

## 6 Oct · Workshop
- Collect FIPs, export session, gather feedback (short form in the tool or paper).

## Oct–Dec 2026 · v2 – Integration
- [ ] Write the FioDMP API contract (OpenAPI) + DMP→FIP mapping; meeting with ICTIC.
- [ ] `relatedDMPs` and per-answer `dmpEvidence` (works by URL today).
- [ ] `GET /api/fips/{id}` and `/fips/{id}/embed` for FioDMP to display FIPs.
- [ ] Prefill from FioDMP JSON once available.
- [ ] Spanish (es) translation.
- [ ] FER lookup via Nanopub Query; publish FIPs as nanopublications.
- [ ] FIP migration between knowledge-model versions (DSW-style).
- [ ] ORCID and Login Único Fiocruz sign-in; email verification and password reset via SMTP.
- [ ] Team workspaces (share sessions, FIPs, models with collaborators); public FIP gallery.
- [ ] Paper or report on the workshop results and the FIP–DMP linkage.

## Definition of done for v1
Anyone can register and sign in to a workspace that shows only their own FIPs, sessions and models. A signed-in facilitator can create a session in under a minute, 40 participants on phones can each produce a FIP in 20 minutes in English or either Portuguese, the room can see all FIPs side by side, and every FIP is downloadable as JSON, CSV and Turtle.
