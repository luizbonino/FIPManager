# FIP Manager – Roadmap

Today: Mon 8 Sep 2026. Workshop: Tue 6 Oct 2026, CONFOA, Faro. Scope freeze for v1: Fri 12 Sep. Code freeze: Fri 3 Oct.

## Week 1 · 8–12 Sep · Foundations
- [x] Questionnaire: GO FAIR mini-questionnaire as-is, editable knowledge model (decided 8 Sep).
- [x] Licence: MIT for the tool, CC0 default for exported FIPs (decided 8 Sep).
- [ ] Shortlist hosting (FAIR domain vs Fiocruz) — see PLAN.md §9.
- [ ] Repo scaffold: FastAPI + Vue 3 + Docker Compose, CI running tests and build.
- [ ] Data model implemented (User, Questionnaire, FIP, FER, Session) with ownership and visibility fields, JSON import/export.
- [ ] Accounts: register, sign in/out, argon2id hashing, cookie sessions, CSRF, roles user/admin, first admin from env.
- [x] Languages: en, pt-PT, pt-BR at launch; browser locale default, English fallback (decided 8 Sep).
- [ ] `data/knowledge-models/gofair-fip-mini-1.0.0.json`: the 21 GO FAIR questions in en, with pt-PT and pt-BR drafts.
- [ ] `data/fers/seed.json`: ~60 typed FERs.
- [ ] Deliverable: running skeleton where a user can register, sign in, create a FIP and read it back via API.

## Week 2 · 15–19 Sep · Core flows
- [ ] Participant flow: join session by link, fill questionnaire, pick/enter FERs with status, save, get FIP URL.
- [ ] i18n wiring: UI strings in en, pt-PT, pt-BR; questionnaire content per language; browser-locale detection with English fallback; switcher remembered per browser.
- [ ] Export FIP as JSON and CSV; print view.
- [ ] Personal workspace: my FIPs, my sessions, my knowledge models; visibility private / link / public; change password; delete account.
- [ ] Anonymous session FIPs: per-FIP edit token in the browser; signed-in user can claim a FIP into their workspace.
- [ ] Facilitator flow (signed-in user): create session, choose questionnaire version, join link + QR.
- [ ] Deliverable: end-to-end demo with a colleague on a phone.

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
