# Spec 12 — Understanding, assurance and a FIP dashboard (proposal)

Status: proposal, 10 Sep 2026. Captures three design threads from the conversation with the
project lead so they are not lost. Nothing here is implemented. Sections A and B answer the
lead's criticism of FIPs; section C is a feature idea with an assessment. §D says what could
go before CONFOA and what is v2.

## 0. The criticism

A FIP is a set of self-assertions: "community X uses resource Y for question F1". The only claim
about FAIRness is the resource's type. Nobody checks that the resource has the enabling property,
or that the community uses it in a way that realises the principle. Two distinct problems hide
behind this:

1. **Assurance.** Even a well-understood declaration is unverified (§B).
2. **Understanding.** More fundamentally, the questionnaire presupposes that the person answering
   knows what F1 or I2 entails. Most do not, and a checklist of familiar names feels answerable even
   when the concept behind the question is not understood (§A).

Evidence from this project: of the 385 options in the co-facilitator's area document, 65 name a
resource whose FER type does not match the question's type (a metadata schema offered under an
identifier question, and so on) — see `data/workshop/import-report-2026-09-10.md`, "Type
mismatches". A competent, motivated facilitator; one in six options.

The tool cannot supply understanding. It can make its absence visible at the moment of choice, to
the participant and to the facilitator, instead of burying it in an export that looks like a FAIR
implementation.

## A. Understanding layer

### A1. Entailments as first-class content
Each question in a knowledge model carries what the principle *requires*, decomposed, shown before
the options, in the participant's language, short. Example for F1: an identifier that is globally
unique, persistent, and resolvable; both metadata and data get one; the identifier is recorded in
the metadata.

- Content model: `question.entailments: [{ text: LangMap }]` (max 8, same LangMap rules as
  `suggestedPhrases`). Inherited by forks, so the five CONFOA area drafts get them from the GO FAIR
  model unless overridden.
- Sources for drafting: the principles' text (Wilkinson et al. 2016), the GO FAIR interpretations
  per principle, the RDA FAIR Data Maturity Model indicators, F-UJI metrics. Drafted by the
  fair-expert agent in en and pt-BR, corrected by the project lead.
- UI: collapsed by default under the question text ("What this principle requires"), expanded by
  the facilitator's demo; print view lists them.

### A2. Type conformance at declaration time
The ontology types FERs and each question expects a type. When a participant declares a resource
whose type differs from the question's, the editor says so and asks whether they meant another
question, with a one-tap "move to question X" where X is the question expecting that type. A
prompt, never a block: cross-type declarations remain legal (some resources are genuinely
multi-role). Free-text declarations are exempt. This catches live exactly the 65 cases above.

- Frontend only for catalogue FERs (type known). Network FERs: type known when `ferTypeKey`
  resolved.
- Log the prompt outcome in the declaration (`typeMismatchAcknowledged: true`) so the facilitator
  sees deliberate cross-type choices in the matrix.

### A3. Cross-answer coherence rules
Some misunderstandings show only between questions. A small declarative rule set, stored as data
per knowledge model (`content.coherenceRules`), raises "these answers pull in different directions"
and asks for a reason, which becomes part of the profile (`answer.coherenceNote`). Starter rules:
- A1.1 open protocol declared *and* A1.2 "access only on formal request" declared as current.
- R1.1 licence declared for data *and* A1 says data are not accessible externally.
- F4 declares a repository as the search engine *and* the same repository is not an F4-typed
  registry in the catalogue.
- I2 declares vocabularies but I1 has no representation language ("apenas texto não estruturado").
Rules match on question id + FER type/id/phrase; evaluation is client-side, advisory, and shown in
the editor and the matrix.

### A4. Positive and negative examples
Per question, one resource that satisfies the requirement and one that looks like it does but does
not, with the reason (`question.examples: [{ resource, satisfies: bool, why: LangMap }]`). Learning
happens on the negative example. Shown with the entailments.

### A5. Reflection in the workshop flow
The facilitator script runs principle by principle in twenty minutes. Turn each section into "what
does this principle require, in your words" (one free-text line per section, `sectionReflection`)
before "what do you use". Visible to the group and to the facilitator on the matrix, not exported
to RDF.

## B. Assurance layer

### B1. Separate the claim from its grounds
Per FER type, criteria derived from the principle text (`data/fers/fer-type-criteria.json`: F1 →
unique, persistent under a stated policy, resolvable). A FER can record which criteria it meets and
how (`fer.criteria: [{ key, met: bool|null, evidence: url|text }]`). "We use DOIs" becomes "we use
DOIs, which are unique, persistent under the DOI Foundation's policy, and resolvable".

### B2. Evidence on the declaration
The implementation gap is the community's, so ask for a pointer per declaration: an example record
with a DOI, the repository policy, a schema instance. Generalise `dmpEvidence` to
`evidence: [{ url|text, kind: example|policy|assessment|dmp }]`.

### B3. Assurance level in the matrix
Derived per cell: `declared` (no evidence), `evidenced` (B2 present), `assessed` (B4 present),
`certified` (resource carries a recognised certification, e.g. CoreTrustSeal for repositories),
`not-assessable` (practices, training, software declared as supporting resources). Shown as a
badge; exported in CSV and as `fipmx:assuranceLevel` in RDF.

### B4. External assessments as separate, signed claims
On the nanopublication network an assessor, a FAIRsharing curator or a certification body publishes
"resource Y satisfies criterion Z" as its own signed nanopublication. The FIP stays the community's
claim; assessments accumulate around the resource. FIP Manager reads them first (spec 11's proxy,
a query for assessment nanopubs about a FER IRI) and shows them on the FER and in the matrix;
writing assessments is later and needs the publishing decisions of spec 11 §7.

### B5. Automated probes
Where a property is machine-checkable: identifier resolves; resolution returns metadata; licence is
machine-readable; registry answers a query. Server-side, cached, rate-limited, opt-in per FER,
never a gate. Results feed B3 as `evidenced` with `kind: probe`.

Cautions. Gatekeeping at declaration time would kill the workshop's purpose, which is convergence
and transparency. Supporting resources (software, practices, training) are further from
verifiable; the assurance vocabulary needs `not-assessable`.

## C. FIP dashboard (feature idea, with assessment)

Idea from the project lead: a dashboard to inspect properties across FIPs, e.g. target FAIR
principle (or sub-principle), similarity between FIPs.

Assessment: worthwhile, and cheapest as an extension of what exists. The session matrix already
computes per-question convergence for one session; the network proxy already yields ~80
communities' FIPs. A dashboard generalises both.

### C1. Scope: which FIPs
Selectable population: one session; all public FIPs on this instance; network FIPs (via spec 11);
any union. Everything below is computed on the selected population.

### C2. Views
- **Principle coverage.** Per principle and sub-principle (F1…R1.3, metadata/data split): share of
  FIPs with a `current` declaration, `planned`, `none`, not applicable. Heat map, plus B3 assurance
  mix once available. Answers "where are we collectively weak?"
- **Resource adoption.** Per FER: number of FIPs declaring it, by status, by area; long tail of
  free-text answers that map to no catalogue FER (candidates for the catalogue). The network already
  exposes `fipCount` per community; this is the FER-centric inverse.
- **Similarity and convergence.** Per pair of FIPs, a per-question Jaccard over declared FER
  identities (spec 03's convergence key), averaged with equal weight per principle; a
  nearest-neighbours list ("communities closest to yours") and a simple clustering (hierarchical,
  no external dependency). This is the FIP programme's actual purpose — convergence — made
  navigable. Include "distance to a chosen reference FIP" so an area can compare itself with, say,
  a network FIP from the same domain.
- **Gaps and coherence.** Questions left at `none` or not applicable; A3 coherence flags across the
  population; A2 type mismatches acknowledged.
- **Evolution.** For FIPs with several versions or `planned` declarations: what is planned per
  principle, planned-replacement pairs (successor FERs), migration history.

### C3. Design constraints
- Computation server-side over stored answers; population up to a few hundred FIPs is trivial;
  network FIPs fetched through spec 11's cache, never live per view.
- Read-only, respects visibility (private FIPs never enter a population unless owned by the viewer).
- Same principle × row layout as the matrix so the room recognises it; desktop-first.
- With 40 workshop FIPs statistics are anecdotal; the value grows with the network population, so
  the network population is the default outside a session.

## D. What before CONFOA, what v2

Before CONFOA (small, no external decisions): A1 entailments as content (fair-expert draft, lead
review; new per-question field; editor and print view), A2 type-conformance prompt, B3 assurance
badge limited to `declared` / `evidenced` with B2 evidence links (generalising `dmpEvidence`).
Estimated as one builder round each plus content review. Decide by the scope freeze, 12 Sep.

v2: A3 coherence rules, A4 examples, A5 reflection, B1 criteria per FER type, B4 assessments from
the network, B5 probes, C dashboard (start with C2 coverage and similarity on the session and
network populations).

## E. Open questions for the lead
1. Do A1 entailments follow the 2016 principle text strictly, or the GO FAIR interpretations, where
   they differ (e.g. F1 "both metadata and data")?
2. Is `not-assessable` acceptable as an explicit level, or should supporting resources be excluded
   from assurance entirely?
3. For similarity, weight per principle equally, or per question (which favours F and A with their
   metadata/data splits)?
