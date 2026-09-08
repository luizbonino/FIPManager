# FIP ontology mapping for FIP Manager

Status: verified 2026-09-08. Supersedes the informal mapping sentence at the end of PLAN §4.

## 1. Sources verified

| What | Where | Licence |
|---|---|---|
| FIP Ontology (all terms below) | `https://w3id.org/fair/fip/terms/` → nanopub `.../FIP-Ontology`; machine copy: `https://raw.githubusercontent.com/peta-pico/FAIR-nanopubs/master/fip.ttl` | CC0 1.0 (`dct:license`) |
| FIP mini-questionnaire v2.0.0 (question wording) | `http://bit.ly/FIPminiquestionnaire` → Google Sheet `1tDIRW-_W-bxaFyhc18Z_0VLE45j8XnF7Ll_hW7FP2xM`; fillable form: `https://zenodo.org/records/10417536` | **CC BY-SA 4.0** |
| GO FAIR website FIP page | `https://www.go-fair.org/how-to-go-fair/fair-implementation-profile/` | CC BY 4.0 by GO FAIR |

Namespace: `@prefix fip: <https://w3id.org/fair/fip/terms/>` (`vann:preferredNamespacePrefix "fip"`).
Ontology creators: Erik Schultes (0000-0001-8888-635X), Tobias Kuhn (0000-0002-1267-0234), Barbara Magagna (0000-0003-2195-3997).

## 2. Declaration-status enum (recommended, one-to-one with the ontology)

All four properties are `rdf:Property`, subject = a `fip:FIP-Declaration`, object = a FER.
No domain/range axioms are asserted in the ontology (verified: none of the terms carry `rdfs:domain`/`rdfs:range`).

| FIP Manager `status` | RDF emitted on the declaration | Ontology definition |
|---|---|---|
| `current` | `fip:declares-current-use-of` | resource the community "declares to currently use" |
| `planned` | `fip:declares-planned-use-of` | resource it "declares to plan to use in the future" |
| `planned-development` | `fip:declares-planned-development-of` | resource it "declares to plan to develop" |
| `planned-replacement` | `fip:declares-planned-replacement-of` | resource it plans to replace; the ontology note says the same declaration **should also** carry `fip:declares-planned-use-of` for the successor |
| `none` | no `declares-*` property; type the declaration `fip:FIP-No-Choice-Declaration` | "A declaration stating that no choice has been made (yet)" |

Exact IRIs: `https://w3id.org/fair/fip/terms/` + `declares-current-use-of`, `declares-planned-use-of`,
`declares-planned-development-of`, `declares-planned-replacement-of`, `FIP-No-Choice-Declaration`.

**`considered` has no ontology counterpart.** There is no "declares-considered-use-of" property and no
`Considered-...` class. Recommendation: **drop `considered` from the status enum**. A community's deliberation
is expressed by `fip:considerations` ("Considerations that led to a given FIP declaration"), a free-text
property on the declaration — so map FIP Manager's per-declaration `note{lang}` to `fip:considerations` and, if
facilitators insist on keeping a "considered" state in the UI, export it as `status = none` plus a
`fip:considerations` string naming the resource. Never invent a property for it.

Other verified declaration/FIP properties worth using in the export:
`fip:refers-to-question`, `fip:refers-to-principle`, `fip:declared-by`, `fip:has-declaration-index`,
`fip:declared-for-digital-object-type`, `fip:has-research-domain`, `fip:has-data-steward`,
`fip:availability-in-years`, `fip:metadata-availability-in-years`.
Classes: `fip:FIP-Declaration`, `fip:FAIR-Implementation-Profile`, `fip:FAIR-Implementation-Community`
(subclasses `fip:Mature-Community`, `fip:Emerging-Community`), `fip:FAIR-Enabling-Resource`,
`fip:Available-FAIR-Enabling-Resource`, `fip:FAIR-Enabling-Resource-to-be-Developed`.

## 3. FER types — 12, not 11

PLAN §2 says "11 FER types". The mini-questionnaire v2.0.0 and the ontology both give **12**: one per FAIR
(sub)principle covered by the 21 questions. Short keys below are the `key` values in `data/fers/fer-types.json`
and the `ferType` values in the knowledge model.

| key | IRI (`fip:` + local name) | UI label (en) | Question |
|---|---|---|---|
| `identifier-service` | `Identifier-service` | Identifier service | F1 |
| `metadata-schema` | `Metadata-schema` | Metadata schema | F2 |
| `metadata-data-linking-schema` | `Metadata-data-linking-schema` | Metadata-data linking schema | F3 |
| `registry` | `Registry` | Registry | F4 |
| `communication-protocol` | `Communication-protocol` | Communication protocol | A1.1 |
| `authentication-authorization-service` | `Authentication-and-authorization-service` | Authentication and authorization service | A1.2 |
| `metadata-preservation-policy` | `Metadata-preservation-policy` | Metadata preservation policy | A2 |
| `knowledge-representation-language` | `Knowledge-representation-language` | Knowledge representation language | I1 |
| `structured-vocabulary` | `Structured-vocabulary` | Structured vocabulary | I2 |
| `semantic-model` | `Semantic-model` | Semantic model | I3 |
| `data-usage-license` | `Data-usage-license` | Data usage license | R1.1 |
| `provenance-model` | `Provenance-model` | Provenance model | R1.2 |

English labels are the ontology's own `rdfs:label`. The sheet uses cosmetic variants ("Authentication &
authorisation service", "Structured vocabularies", "Metadata-Data linking schema"); prefer the ontology labels.
`Registry` has two subclasses usable for faceting the FER catalogue: `fip:Generalist-Registry`,
`fip:Domain-Specific-Registry`.

## 4. The 21 questions

The ontology defines exactly 21 `fip:FIP-Question` individuals: `fip:FIP-Question-F1-MD`, `-F1-D`, `-F2`,
`-F3`, `-F4-MD`, `-F4-D`, `-A1.1-MD`, `-A1.1-D`, `-A1.2-MD`, `-A1.2-D`, `-A2`, `-I1-MD`, `-I1-D`, `-I2-MD`,
`-I2-D`, `-I3-MD`, `-I3-D`, `-R1.1-MD`, `-R1.1-D`, `-R1.2-MD`, `-R1.2-D`. Each carries
`fip:refers-to-principle` to a `https://w3id.org/fair/principles/terms/` (sub)principle.

Reconciliation with the task brief's guess: **F2, F3 and A2 have no metadata/data split** (one question each,
no `-MD`/`-D` suffix), and **there is no R1.3 question**. The sheet's last row, "Who is the community, and what
are their domain-relevant community standards?", is answered by "This FAIR Implementation Profile" itself — it
is a rubric row, not a question, and has no ontology individual. 2×9 scoped + 3 unscoped = 21.

Mapping: knowledge-model question id `F1-metadata` → `fip:FIP-Question-F1-MD`, `F1-data` → `...-F1-D`,
`F2`/`F3`/`A2` → `...-F2`/`-F3`/`-A2` (these carry `scope: null`, following the ontology rather than reading
"metadata" into them). R1.3 is covered by the FIP's own `community` field, not by a question.

Wording note: the ontology's A2 definition is the v1.0 phrasing "Which metadata longevity plan do you use?";
v2.0.0 of the sheet says "What is your metadata preservation policy?". The knowledge model uses the v2.0.0
wording, which is the currently published questionnaire.

## 5. Turtle example — one FIP, two declarations

```turtle
@prefix fip:  <https://w3id.org/fair/fip/terms/> .
@prefix fair: <https://w3id.org/fair/principles/terms/> .
@prefix ex:   <https://fip.example.org/> .
@prefix dct:  <http://purl.org/dc/terms/> .

ex:fip/K7QX2 a fip:FAIR-Implementation-Profile ;
  dct:title "FIP of the CONFOA 2026 group A"@en ;
  dct:license <https://creativecommons.org/publicdomain/zero/1.0/> ;
  fip:declared-by ex:community/confoa-group-a ;
  fip:has-declaration-index ex:fip/K7QX2/declarations .

ex:community/confoa-group-a a fip:FAIR-Implementation-Community ;
  dct:title "CONFOA 2026 workshop, group A"@en ;
  fip:has-research-domain "Public health"@en ;
  fip:has-data-steward <https://orcid.org/0000-0002-1825-0097> .

# status = current
ex:fip/K7QX2/decl-F1-D a fip:FIP-Declaration ;
  fip:declared-by ex:community/confoa-group-a ;
  fip:refers-to-question fip:FIP-Question-F1-D ;
  fip:refers-to-principle fair:F1 ;
  fip:declares-current-use-of <https://www.doi.org/> .

# status = planned-replacement (+ the successor, as the ontology asks)
ex:fip/K7QX2/decl-R1.1-D a fip:FIP-Declaration ;
  fip:declared-by ex:community/confoa-group-a ;
  fip:refers-to-question fip:FIP-Question-R1.1-D ;
  fip:refers-to-principle fair:R1.1 ;
  fip:declares-planned-replacement-of <https://creativecommons.org/licenses/by-nc/4.0/> ;
  fip:declares-planned-use-of <https://creativecommons.org/licenses/by/4.0/> ;
  fip:considerations "Non-commercial clause blocks reuse by industry partners."@en .
```

## 6. Attribution and licence obligations

- **Ontology terms, FER type labels and definitions: CC0 1.0.** No obligation; attribution given anyway.
- **Question wording: CC BY-SA 4.0.** The mini-questionnaire v1.0 was created in 2020 by Erik Schultes,
  Barbara Magagna and Jacintha Schultes (GO FAIR Foundation, in cooperation with CODATA); v2.0.0 in November
  2023 by the same three authors (GO FAIR Foundation).
- Consequence for PLAN §9.4 (tool licence MIT): **share-alike applies to the questionnaire content, not to the
  code.** `data/knowledge-models/gofair-fip-mini-1.0.0.json` and any version forked from it are adaptations of
  a CC BY-SA 4.0 work and must be distributed under CC BY-SA 4.0 with the attribution above. Facilitator
  decision needed: state this in the repo (a `data/knowledge-models/LICENSE` note) and show the attribution in
  the UI footer and in every export of a FIP answered against this model. Knowledge models created from
  scratch in FIP Manager are unaffected.
- Required attribution string: *"FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, Barbara Magagna,
  Jacintha Schultes / GO FAIR Foundation, CC BY-SA 4.0."*
