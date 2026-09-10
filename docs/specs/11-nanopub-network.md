# Spec 11 – Nanopublication network: read existing FIPs, prepare ours for publishing

Status: draft, 2026-09-10. Author: fair-expert/architect. Driver: the user's 10 Sep goal — *"integrate with the
FIPs already in the nanopublication network"*, in two halves: **(a) read** the FIPs already in the network — 79
distinct FIP communities and 173 non-retracted `fip:FAIR-Implementation-Profile` nanopubs, measured
2026-09-10 — and show them in FIP Manager, and **(b) prepare for export** — produce our FIPs as
nanopublications ready to publish, but **publish nothing** in this iteration (no signing keys, no network
writes).

Everything in §0 was fetched live on 2026-09-10 and is quoted verbatim below. Anything I could not verify is
marked **UNVERIFIED** and never used as a load-bearing assumption.

Related: docs/specs/00-fip-ontology-mapping.md (the term mapping this spec reuses unchanged),
03-matrix-and-rdf.md §2 (`rdf.py`, whose FER/status/question mapping is reused), 08-workshop-picklists.md §1.3
(FER promotion, whose `source=` model this spec extends), 09-standalone-fips.md (the FIP kinds a network
import can create).

---

## 0. Sources verified live, 2026-09-10

| What | Endpoint / IRI, verified | Result |
|---|---|---|
| FIP Ontology, machine copy | `https://raw.githubusercontent.com/peta-pico/FAIR-nanopubs/master/fip.ttl` | 200, 64 108 bytes, 734 lines. Confirms every term spec 00 lists, and exactly **21** `fip:FIP-Question-*` `owl:NamedIndividual`s. |
| FIP Ontology, human page | `https://w3id.org/fair/fip/terms/` | 302 → `https://nanodash.knowledgepixels.com/resource?id=https://w3id.org/fair/fip/terms/FIP-Ontology` |
| Nanopub Query service root | `https://query.knowledgepixels.com/` | 200. General repos: `admin`, `empty`, `full`, `last30d`, `meta`, `spaces`, `text`, `trust`. Plus Pubkey Repos and Type Repos. |
| SPARQL endpoint (all nanopubs) | `POST https://query.knowledgepixels.com/repo/full` (`query=` form-encoded) | 200. `Access-Control-Allow-Origin: *`. Content negotiation: `text/csv`, `application/sparql-results+json`. |
| SPARQL endpoint (one type) | `POST https://query.knowledgepixels.com/repo/type/<sha256 of the type IRI, lowercase hex>` | 200. `sha256("https://w3id.org/fair/fip/terms/FIP-Declaration")` = `4ad845e860a6db3a69160adb7aec894e622280ff9881e41a600756ad1abcfa23`; `FAIR-Implementation-Community` = `6a09747868afc83837e38d1bac79362fbcc3e2032cff2f2d244f4e24cbd085c6`; `FAIR-Enabling-Resource` = `3ef5b11551ebc44e34f4bca614b387204447656ce195314532769ca7b20143fe`; `FAIR-Implementation-Profile` = `92efd7a0ea4be4e01ec0817ccec87f975203b30addcc3166a204498ffed73b66`. All four repos exist (each appears in `GET /types`). |
| Full-text repo | `POST https://query.knowledgepixels.com/repo/text` with `?np search:matches [ search:query "…"; search:score ?s ]`, `search:` = `http://www.openrdf.org/contrib/lucenesail#` | 200, 0.45 s. |
| grlc query API | `GET https://query.knowledgepixels.com/api/<artifactCode>/<queryName>` | 200. Verified: `RAoQRAype8NkynHDgj5ofRSjFmkeXYIeybunn1EnGpyyQ/fip-communities` (10 522 B CSV), `RADOxxVDmDAP-SS4Rw2mvNc86VtfkcHHseQmr3eWFloi4/fip-domains`, `RAy9osazqjqrBXua2IJGMzOSML0RAjFaktCOys3zpnRNw/get-reference-fips`, `RAoyVY3PFKl2LgnV4O4JmyepekSn8jxCGq0T2CsXv6AMs/get-fip-decl-details`. `OPTIONS` → `204`, `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods: GET, HEAD, POST, OPTIONS`, `Access-Control-Allow-Headers: *`. |
| Mirror | `https://query.petapico.org/api/…` and `https://query.petapico.org/repo/full` | both 200, byte-identical CSV for `fip-communities`. |
| Nanopub fetch by URI | `GET https://w3id.org/np/<artifactCode>` with `Accept: application/trig`, and `GET https://np.knowledgepixels.com/<artifactCode>` | both 200, `Content-Type: application/trig;charset=UTF-8`, `Access-Control-Allow-Origin: *`. `http://purl.org/np/<artifactCode>` also resolves (older nanopubs use that base). |
| nanopub-py constants | `https://raw.githubusercontent.com/Nanopublication/nanopub-py/main/nanopub/definitions.py` | `NP_TEMP_PREFIX = "http://purl.org/nanopub/temp/"`, `NP_PREFIX = "https://w3id.org/np/"`, `DUMMY_NANOPUB_URI = "http://purl.org/nanopub/temp/np"`, `DUMMY_NAMESPACE = DUMMY_NANOPUB_URI + "/"`, `RSA_KEY_SIZE = 2048`, `MAX_NP_PER_INDEX = 1100`, `MAX_TRIPLES_PER_NANOPUB = 1200`, `NANOPUB_REGISTRY_URLS = [registry.petapico.org/np/, registry.knowledgepixels.com/np/, registry.np.trustyuri.net/np/]`, `NANOPUB_QUERY_URLS = [query.knowledgepixels.com/api/, query.petapico.org/api/]`. |
| nanopub-py signing | `nanopub/sign_utils.py` `replace_trusty_in_graph` | `if str(dummy_ns).startswith(NP_TEMP_PREFIX): np_uri = NP_PREFIX + trusty_artefact`. **Any** dummy base under `http://purl.org/nanopub/temp/` is rewritten to `https://w3id.org/np/RA…` — so our own path segment under that prefix is fine. |
| nanopub-py TriG input | `nanopub/nanopub.py` `Nanopub.__init__(rdf: Union[Dataset, Path])`; `nanopub/utils.py` `extract_np_metadata` | A `Path` to a TriG file is a first-class input. `extract_np_metadata` finds the nanopub by SPARQL over the Head graph and derives the `#`-vs-`/` separator from the nanopub URI's last character, falling back to the head-graph URI. |
| nanopub-java | `https://raw.githubusercontent.com/Nanopublication/nanopub-java/master/README.md` | `MakeKeys.make("~/.nanopub/id", SignatureAlgorithm.RSA)`, `SignNanopub.signAndTransform(np, TransformContext.makeDefault())`, `PublishNanopub.publish(signedNp)`. CLI installed by `curl -LsSf https://nanopublication.github.io/nanopub-java/install.sh \| bash`; commands include `sign / SignNanopub` and `publish / PublishNanopub`; `sign` takes a YAML profile with `orcid_id`, `public_key`, `private_key`. |

### 0.1 Statistics measured (2026-09-10)

Scale: `fip-communities` returns **84 rows / 79 distinct community IRIs** (5 duplicate rows, §3.1); the
`FAIR-Implementation-Profile` type repo holds **173** non-retracted FIP nanopubs.

Predicates on `fip:FIP-Declaration` subjects, network-wide (repo `type/4ad845e8…`):

| Predicate | Occurrences |
|---|---|
| `rdf:type` | 25 074 |
| `fip:declared-by` | 24 551 |
| `fip:refers-to-question` | 24 551 |
| `fip:considerations` | 23 737 |
| `fip:declares-current-use-of` | 18 690 |
| `dcat:startDate` / `dcat:endDate` | 16 421 each |
| `fip:declares-planned-use-of` | 5 299 |
| `schema:version` | 1 790 |
| `fip:declared-for-digital-object-type` | 372 |
| `fip:declared-for-sample-digital-object` | 213 |
| `fip:declares-planned-replacement-of` | **179** |
| `fip:declared-for-case-study` | 137 |
| `fip:declares-replacement-from` / `-to` | 34 each (**unofficial** — not in `fip.ttl`; the wizard's own query nanopub comments them `# unofficial`) |
| `fip:declares-planned-development-of` | **0** |
| `fip:FIP-No-Choice-Declaration` instances (repo `full`) | 2 688 |

Two facts that matter for us: **`declares-planned-development-of` is used by nobody** (our
`planned-development` status has an ontology property but no network precedent — we still emit it, §2.5), and
**`FIP-No-Choice-Declaration` is heavily used**, so our `status: "none"` maps onto a real, common network
pattern.

Publishing agents (`dct:creator` in the admin graph, declarations only):

| Agent IRI | Declarations | Latest |
|---|---|---|
| `https://fip-wizard.ds-wizard.org` | 18 194 | 2023-11-04 |
| `https://fip-wizard.ds-wizard.org/wizard` | 4 993 | 2025-04-22 |
| `https://fip.fair-wizard.com/wizard` | 1 364 | 2026-09-07 |

The current FIP Wizard software-agent IRI is therefore **`https://fip.fair-wizard.com/wizard`**. Our analogue
will be `{FIPM_BASE_URL}` (§7 Q1).

### 0.2 What the FIP Wizard actually publishes — real TriG, quoted

The Wizard uses **no nanopub templates** for FIPs: unlike FER nanopubs (which carry
`nt:wasCreatedFromTemplate <http://purl.org/np/RAWMMyUanP-BtP9YhjIgNp7Ndeju_J8S0JgK-JlO2CSIU>`), community,
declaration, index and FIP nanopubs carry no `nt:` triple at all — the Wizard builds the TriG itself. It also
never authors `npx:hasNanopubType`: that lives in the registry's `npa:graph`, derived from the assertion's
`rdf:type`. **So we do not emit `nt:` or `npx:hasNanopubType` either.**

A FIP in the network is therefore **four kinds of nanopublication**, and the answer to "is there a FIP nanopub
that lists declarations?" is: *yes, indirectly* — a `fip:FAIR-Implementation-Profile` nanopub points via
`fip:has-declaration-index` at a **`npx:NanopubIndex` nanopub** whose assertion is a flat
`npx:includesElement` list of declaration nanopub URIs.

**(1) Community** — `GET http://purl.org/np/RAoZsfUhNx4sYz-IXfsp1xPBH1-YgTGtHpp3BbMQtWHJg`:

```trig
sub:Head {
  this: a np:Nanopublication;
    np:hasAssertion sub:assertion; np:hasProvenance sub:provenance; np:hasPublicationInfo sub:pubinfo .
}
sub:assertion {
  sub:PARCToxicology a fip:FAIR-Implementation-Community;
    dcterms:isPartOf <http://purl.org/np/RAvuwR9iDrKdPeDCZAxMhW_wDmwuIYDSOcQaZ_QBFZs8M#PARC>;
    rdfs:comment "PARC Chemical Toxicology Community is the grouping of PARC partners …";
    rdfs:label "PARCToxicology | PARC Chemicals Toxicology Community";
    rdfs:seeAlso <https://www.eu-parc.eu>;
    fip:has-research-domain <http://edamontology.org/topic_0208>, <http://purl.obolibrary.org/obo/NCIT_C15206>, … .
}
sub:provenance { sub:assertion dcterms:creator orcid:0000-0003-4250-4584 . }
sub:pubinfo {
  sub:sig npx:hasAlgorithm "RSA"; npx:hasPublicKey "MIGfMA0…"; npx:hasSignature "SbQhsmj1…";
    npx:hasSignatureTarget this: .
  this: dcterms:created "2023-03-15T15:11:12Z"^^xsd:dateTime;
    dcterms:creator <https://fip-wizard.ds-wizard.org>;
    dcterms:license <https://creativecommons.org/publicdomain/zero/1.0/>;
    npx:introduces sub:PARCToxicology;
    npx:supersedes <http://purl.org/np/RAeHApHLHTgyKZWSd7_1K-aXE9kov2jiaU51ktW_i4V3M>;
    prov:wasDerivedFrom <https://w3id.org/fip/wizard/93f8627e-c7ca-4147-a409-fa4f2768d1c7> .
}
```

**(2) Declaration** — `GET https://w3id.org/np/RAzGbv2f7tCb74PZjHDeoEPdy69EsS8vNMiYmPThv_qwM`:

```trig
sub:assertion {
  sub:declaration a fip:FIP-Declaration;
    fip:considerations "The data and metadata organization are described in: Argo user's manual, …";
    fip:declared-by <http://purl.org/np/RA84m3skQV7YJg2crQjRHHoE6PaPkL1ew8GD0sa3tTj8g#ArgoGdac>;
    fip:declares-current-use-of <http://purl.org/np/RAm-5N-Essj5oekn7Qd_KgooUYAk9Szk3bBK9R3jcGnlM#NetCDF_CF1.7>;
    fip:refers-to-question fip:FIP-Question-F2;
    dcat:endDate "2019-12-31"^^xsd:date;
    dcat:startDate "2019-01-01"^^xsd:date .
}
sub:provenance { sub:assertion dct:creator orcid:0000-0003-2700-4020 . }
sub:pubinfo {
  sub:sig npx:hasAlgorithm "RSA"; npx:hasPublicKey "MIGfMA0…"; npx:hasSignature "PBDVxNe3…";
    npx:hasSignatureTarget this: .
  this: dct:created "2024-01-22T20:06:51Z"^^xsd:dateTime;
    dct:creator <https://fip-wizard.ds-wizard.org/wizard>;
    dct:license <https://creativecommons.org/publicdomain/zero/1.0/>;
    prov:wasDerivedFrom <https://w3id.org/fip/wizard/7b143e27-4b1c-444e-be4a-fa8d0839981f> .
}
```

Note: **no `npx:introduces` on a declaration** (the declaration node is not an introduced concept), and the
declaration is *not* linked from the community — the arrow points declaration → community.

A no-choice declaration (`GET https://w3id.org/np/RAy0IWPZxqHV6_i7UK08-XOtzyOF8D-sx79twx3BE3A6c`) is the
same shape with a different type and **no `declares-*` predicate at all**:

```trig
sub:assertion {
  sub:declaration a fip:FIP-No-Choice-Declaration;
    fip:considerations "Aggregated CDI records will be distributed via spra";
    fip:declared-by <http://purl.org/np/RAge5lgbVKMXb0zu5CUpFaCiwg7lUXa_5QGhRw68zaq2g#SeaDataNet-CDI>;
    fip:refers-to-question fip:FIP-Question-A1.1-D;
    dcat:endDate "2019-12-31"^^xsd:date; dcat:startDate "2019-01-01"^^xsd:date .
}
```

**(3) Declaration index** — `GET https://w3id.org/np/RA7UpAcMN5tmQR8cfFd1CzzUm1H2XVWPtChzEJRVQSkXE`:

```trig
sub:assertion {
  this: npx:includesElement <https://w3id.org/np/RA-EyAMJepwUbIULkbt_NjtxbI2Vz6POCSIDEbngXIZpY>,
      <https://w3id.org/np/RA1tmLOUZxgscJzUE986D3t276BzNL3uRbKsFA30Y9t-w>, … .   # 36 elements
}
sub:provenance { sub:assertion a npx:IndexAssertion; dct:creator orcid:0000-0003-4250-4584 . }
sub:pubinfo {
  sub:sig … ;
  this: a npx:NanopubIndex;
    <http://purl.org/dc/elements/1.1/title> "PARC TOXRIC FIP";
    dct:created "2024-01-22T20:09:10Z"^^xsd:dateTime;
    dct:creator <https://fip-wizard.ds-wizard.org/wizard>;
    dct:license <https://creativecommons.org/publicdomain/zero/1.0/>;
    npx:supersedes <http://purl.org/np/RA2dJUopl8drwH1t1E2wS9DJpJBt57-VcsYT0M0GpR9bM>;
    prov:wasDerivedFrom <https://w3id.org/fip/wizard/d7433dfc-41bc-42d4-b386-0d7be2472530> .
}
```

Three details worth copying exactly: the index's subject is **`this:` itself** (not a `sub:` concept); the
provenance graph is typed **`npx:IndexAssertion`**; the title uses **`dc:title` (`dc/elements/1.1/`)**, not
`dct:title`.

**(4) FIP** — `GET https://w3id.org/np/RAllERFvC1zFXu7uTmQ1Dibvrh-VIr4l1XKM54oQKeZog`:

```trig
sub:assertion {
  sub:fip a fip:FAIR-Implementation-Profile;
    dct:description "PARC TOXRIC FIP: This is the FIP of PARC TOXRIC";
    rdfs:label "PARC TOXRIC FIP";
    fip:declared-by <http://purl.org/np/RAoZsfUhNx4sYz-IXfsp1xPBH1-YgTGtHpp3BbMQtWHJg#PARCToxicology>;
    fip:has-declaration-index <https://w3id.org/np/RA7UpAcMN5tmQR8cfFd1CzzUm1H2XVWPtChzEJRVQSkXE>;
    dcat:endDate "2026-04-30"^^xsd:date; dcat:startDate "2023-04-14"^^xsd:date .
}
sub:provenance { sub:assertion dct:creator orcid:0000-0003-4250-4584 . }
sub:pubinfo {
  sub:sig … ;
  this: dct:created "2024-01-22T20:09:10Z"^^xsd:dateTime;
    dct:creator <https://fip-wizard.ds-wizard.org/wizard>;
    dct:license <https://creativecommons.org/publicdomain/zero/1.0/>;
    npx:introduces sub:fip;
    npx:supersedes <http://purl.org/np/RA2dJUopl8drwH1t1E2wS9DJpJBt57-VcsYT0M0GpR9bM>;
    prov:wasDerivedFrom <https://w3id.org/fip/wizard/d7433dfc-41bc-42d4-b386-0d7be2472530> .
}
```

**(5) FER** (a resource a declaration points at) — `GET http://purl.org/np/RAm-5N-Essj5oekn7Qd_KgooUYAk9Szk3bBK9R3jcGnlM`:

```trig
sub:assertion {
  sub:NetCDF_CF1.7 a fip:Available-FAIR-Enabling-Resource, fip:Data-schema, fip:FAIR-Enabling-Resource,
      fip:Metadata-schema, fip:Provenance-model, fip:Structured-vocabulary;
    rdfs:comment "NetCDF compliant with Climate and Forecasts (CF) Metadata Convention v1.7";
    rdfs:label "NetCDF CF-1.7";
    skos:exactMatch <http://cfconventions.org/Data/cf-conventions/cf-conventions-1.7/cf-conventions.html> .
}
```

**Consequence for §3:** a network FER's identity is a *nanopub-fragment IRI*
(`http://purl.org/np/RA…#NetCDF_CF1.7`), not the resource's homepage. Its homepage, when it has one, is
`skos:exactMatch`. It carries **several** `fip:` type classes at once. Labels are frequently
`"SHORT | Long name"` and vary between nanopub versions (`"HTTPS|Hypertext…"` vs `"HTTPS | Hypertext…"`).

---

## 1. Goal and scope

**In scope, this iteration:**

1. **Read.** Backend-proxied, read-only access to the nanopublication network so FIP Manager can list FIP
   communities, show one community's latest FIP as declarations laid out against our 21 questions, and (v2
   roadmap) look up FERs. §3.
2. **Prepare for export.** A downloadable, complete, *unsigned* nanopublication bundle for one FIP Manager
   FIP — one TriG file per nanopub in a zip, plus `index.json` and `MANIFEST.md` saying exactly what a later
   signing step must do and what is still missing. §2.
3. **Use a network FIP as a starting point** for a new FIP Manager FIP. §3.6.

**Explicitly out of scope, this iteration** (and each is a hard "no", not a "later in this spec"):

- **No writes to the network.** No `POST` to any registry, no `nanopub` dependency added, no key material
  generated, stored, read or referenced. The exported bundle is inert data.
- **No signing.** Not even with a throwaway key. The bundle's whole point is that it is the *input* to
  someone else's signing step.
- **No ORCID login.** Nothing in this iteration authenticates a user to anything external.
- **No caching of network data in the database.** The network cache is in-process and volatile (§3.4); the
  only network-derived rows that reach the database are FERs a human explicitly imported (§3.6, §4).
- **No FSR / R-FIP / SIP support.** The network also holds `fip:FSR-Declaration`, `fip:SIP-Declaration` and
  `fip:FIP-S-Question-*` individuals (89 declarations of the current PARC Toxicology FIP include four
  `FIP-S-Question-*` rows). They are surfaced read-only under `unmapped` and never imported.

---

## 2. Mapping: a FIP Manager FIP → nanopublications

### 2.1 The bundle

One FIP Manager FIP becomes **N + 3 nanopublications**, where N is the number of declarations that survive
the filter in §2.5:

| n | Role | Assertion subject | `npx:introduces` |
|---|---|---|---|
| 1 | community | `…/1/community` | yes |
| 2 … N+1 | one per declaration | `…/{n}/declaration` | no |
| N+2 | declaration index | `this:` (`…/{N+2}/`) | no |
| N+3 | FIP | `…/{N+3}/fip` | yes |

This is the Wizard's own decomposition (§0.2), so a FIP Manager FIP published later is indistinguishable in
shape from a Wizard FIP and is picked up by the network's existing FIP queries (`fip-communities`,
`get-fip-decl-in-index`, `fip_search`) with no changes on their side.

### 2.2 Placeholder base IRIs

Every nanopub in the bundle gets its **own** base under nanopub-py's `NP_TEMP_PREFIX`:

```
this:  http://purl.org/nanopub/temp/fipm/{fipId}/{n}/
sub:   http://purl.org/nanopub/temp/fipm/{fipId}/{n}/
```

so the four graphs are `…/{n}/Head`, `…/{n}/assertion`, `…/{n}/provenance`, `…/{n}/pubinfo` and the concept is
`…/{n}/community` · `…/{n}/declaration` · `…/{n}/fip`.

Why this exact form:

- `replace_trusty_in_graph` (§0) rewrites **any** dummy base starting with `http://purl.org/nanopub/temp/` to
  `https://w3id.org/np/RA<artifactCode>`, so `…/fipm/{fipId}/{n}/` is rewritten correctly with no patch to
  nanopub-py.
- The base **ends in `/`**, matching nanopub-py's own `DUMMY_NAMESPACE` (`http://purl.org/nanopub/temp/np/`).
  `extract_np_metadata` derives the `#`-vs-`/` separator from the nanopub URI's last character, so a trailing
  slash is unambiguous. (`#` would also work — the Wizard uses it — but only the `/` form matches what
  nanopub-py mints itself, so it is the form its round-trip is best tested against.)
- `{fipId}` and `{n}` keep every nanopub in one bundle distinct, which matters because §2.3's cross-references
  are resolved by string substitution.

`{fipId}` is the FIP Manager id verbatim (it is already `[A-Za-z0-9]`-safe, `fipm/ids.py`); `{n}` is
`1`-based.

### 2.3 Cross-references and the signing order

A signed nanopub's IRI is a hash of its own content, so a nanopub cannot reference a *not yet signed* sibling
by its final IRI. The bundle therefore contains temp cross-references, and `index.json` states the order and
substitutions a signing step must apply. **This is the one thing a consumer of the bundle must get right, so
it is data in the manifest, not prose.**

Required order, and what each step unblocks:

1. **community** — every declaration and the FIP reference it via `fip:declared-by`.
2. **declarations** (any order among themselves) — the index references each one.
3. **index** — the FIP references it via `fip:has-declaration-index`.
4. **FIP** — references nothing unsigned.

`index.json` carries a machine-readable `rewrites` list: after signing nanopub `n`, replace every occurrence
of `http://purl.org/nanopub/temp/fipm/{fipId}/{n}/` in the *remaining* files with the trusty base
`https://w3id.org/np/RA…/` (and the concept IRI accordingly). nanopub-py does **not** do this for you — it
only rewrites a nanopub's own dummy namespace — which is exactly why we say so explicitly.

### 2.4 Contents, nanopub by nanopub

Notation: `fipmSettings` = `fipm.config.Settings`; `L(x)` = `exporters.resolve_lang` on the FIP's language with
the pt-PT ⇄ pt-BR → en fallback; `T(x)` = the same but returning the language key too
(`rdf._resolve_lang_pair`). Every literal that is human text is language-tagged with the key `T` returned —
the network's own FIP nanopubs use untagged literals, but a tagged literal is strictly more informative and
CONFOA's content is pt-BR (see §7 Q5 for the one place this could bite).

Common to all four pubinfo graphs:

```trig
sub:pubinfo {
  this: dct:created "<generatedAt, xsd:dateTime, UTC, second precision>"^^xsd:dateTime;
    dct:creator <{FIPM_BASE_URL}>;
    dct:license <https://creativecommons.org/publicdomain/zero/1.0/>;   # or the FIP's own, mapped
    prov:wasDerivedFrom <{fip_url(fip)}> .
}
```

- `dct:creator` is the **software agent**, exactly as the Wizard uses `https://fip.fair-wizard.com/wizard`.
  Ours is `{FIPM_BASE_URL}` for now; §7 Q1 is the facilitator decision about a stable IRI.
- `dct:license` reuses `rdf.LICENSE_IRI_MAP[fip.license]`; an unmapped licence string means the triple is
  **omitted** (never a guessed IRI, never a literal in object position of `dct:license` in a pubinfo graph).
- `prov:wasDerivedFrom` points at the FIP's own FIP Manager URL (`exporters.fip_url`) — the analogue of the
  Wizard's `https://w3id.org/fip/wizard/<uuid>`. It is the only place a FIP Manager URL appears, and only for
  a FIP that is already `visibility: "public"`/`"link"`; for a `private` FIP the triple is omitted (§5).
- **No signature triples.** `sub:sig` does not exist in the bundle. The signing step adds it.
- **No `npx:supersedes`.** We have never published, so there is nothing to supersede. §7 Q4 covers republishing.

**(1) Community**, `n = 1`:

| Triple | Source in FIP Manager |
|---|---|
| `sub:community a fip:FAIR-Implementation-Community` | always |
| `rdfs:label "…"@lang` | `fip.community.name` (`T`). Falls back to `fip.title`, then `"FIP {fip.id}"`. |
| `rdfs:comment "…"@lang` | `fip.community.description` |
| `fip:has-research-domain <IRI>` | `fip.community.domain` **only when it is an `http(s)` IRI** (it is an ObjectProperty — the same rule `rdf._is_http_iri` already enforces) |
| `dct:subject "…"@lang` | `fip.community.domain` when it is *not* an IRI |
| `fip:has-data-steward <https://orcid.org/…>` | `fip.community.dataSteward.orcid` when it matches `rdf.ORCID_RE` |
| `foaf:Person` node + `rdfs:label`/`foaf:name` | `dataSteward.name` with no valid ORCID, mirroring `rdf.fip_graph`'s `#data-steward` node |
| provenance: `sub:assertion dct:creator <https://orcid.org/…>` | the FIP owner's ORCID **if we have one** — we do not today (§7 Q2). Until then the provenance graph carries `sub:assertion prov:wasAttributedTo <{FIPM_BASE_URL}>` and the manifest flags the missing ORCID as a publish blocker. |
| pubinfo: `npx:introduces sub:community` | always |

**(2..N+1) Declaration**, one per `(answer, declaration)` pair, in the knowledge model's question order then
the declaration's array index — reusing exactly `rdf.STATUS_PREDICATE` and
`rdf._question_individual_local`:

| Triple | Rule |
|---|---|
| `sub:declaration a fip:FIP-Declaration` | always, **except** `status == "none"` → `a fip:FIP-No-Choice-Declaration` (matching the network's 2 688 real instances; `FIP-Declaration` is **not** additionally asserted, per the quoted example) |
| `fip:declared-by <…/1/community>` | always (temp IRI, rewritten per §2.3) |
| `fip:refers-to-question fip:FIP-Question-<X>` | `rdf._question_individual_local(questionId)`; `None` (a non-GO-FAIR question id from a forked knowledge model) → **the declaration is skipped entirely** and listed in `index.json`'s `skipped` (§2.5) |
| `fip:refers-to-principle fair:<P>` | `question.principle` when in `rdf.KNOWN_PRINCIPLE_IDS`. Not used by the Wizard, but valid (`fip.ttl` gives `refers-to-question` domain `FIP-Declaration`, and `refers-to-principle` is a plain property) and already emitted by `rdf.py`. |
| `fip:declares-current-use-of` / `-planned-use-of` / `-planned-development-of` / `-planned-replacement-of` | `rdf.STATUS_PREDICATE[status]`, object = the FER IRI resolved by §2.4.1. Omitted for `status == "none"`. |
| `fip:declares-planned-use-of <successor>` | additionally, when `status == "planned-replacement"` and a `successorFerId`/`successorFreeText` exists — the ontology's own note, already implemented in `rdf.fip_graph` |
| `fip:considerations "…"@lang` | one per `(lang, text)` in `declaration.note`; plus, for `status == "none"`, `rdf._none_declaration_text` (so a "none" declaration's FER label is not silently dropped); plus the answer-level `comment` when the answer has exactly one declaration (see §2.5 for the multi-declaration case) |
| `dcat:startDate` / `dcat:endDate` | **omitted.** We have no validity period per declaration (§2.5). |
| provenance | `sub:assertion prov:wasAttributedTo <{FIPM_BASE_URL}>` (same ORCID gap as above) |

#### 2.4.1 The FER IRI in a declaration

Priority, first match wins:

1. `declaration.ferId` **and** the `fers` row has `source == "network"` → use `Fer.id` verbatim. It *is* a
   network nanopub-fragment IRI (`http://purl.org/np/RA…#HTTPS`), so the declaration links straight into the
   network's existing FER graph. This is the case that makes a network-seeded FIP round-trip cleanly.
2. `declaration.ferId` (any other source) → use `Fer.id` verbatim, and additionally emit a **FER description
   block** inside the same declaration nanopub's assertion:
   `<ferId> a fip:FAIR-Enabling-Resource, <fip type class>, <availability class>; rdfs:label "…"@lang .`
   using `rdf._fer_type_class` and `rdf.STATUS_AVAILABILITY_CLASS`. Repeating the FER inside every
   declaration that uses it is deliberate: the alternative (a separate FER nanopub per catalogue FER) doubles
   the bundle size and would mint FIP-Manager-owned duplicates of resources the network already describes.
   §7 Q3 is the facilitator question about whether to publish FER nanopubs for genuinely new resources.
3. `declaration.ferFreeText` → mint `{FIPM_BASE_URL}/fers/text/{rdf._free_text_hash(text)}` — byte-identical
   to what `rdf._emit_fer` already mints — with the same FER description block plus
   `{fipmx}free-text true`.

`{fipmx}` is `Settings.ext_ns` (default `https://w3id.org/fipm/ns#`), unchanged from spec 03.

**(N+2) Declaration index:**

```trig
sub:assertion { this: npx:includesElement <…/2/>, <…/3/>, … .   # every declaration nanopub, temp IRIs
}
sub:provenance { sub:assertion a npx:IndexAssertion; prov:wasAttributedTo <{FIPM_BASE_URL}> . }
sub:pubinfo {
  this: a npx:NanopubIndex;
    <http://purl.org/dc/elements/1.1/title> "<the FIP's title>";
    dct:created …; dct:creator <{FIPM_BASE_URL}>; dct:license …; prov:wasDerivedFrom … .
}
```

Note `npx:includesElement` takes the **nanopub** IRI (`…/{n}/`), not the declaration concept IRI. If N > 1 100
(`MAX_NP_PER_INDEX`) the bundle is rejected with `413 too_many_declarations` — a FIP Manager FIP has at most
21 questions and a handful of declarations each, so this is a guard, not a real case.

**(N+3) FIP:**

| Triple | Source |
|---|---|
| `sub:fip a fip:FAIR-Implementation-Profile` | always |
| `rdfs:label "…"@lang` | `fip.title`, falling back to `fip.community.name`, then `"FIP {fip.id}"` |
| `dct:description "…"@lang` | `fip.community.description` when present |
| `fip:declared-by <…/1/community>` | always |
| `fip:has-declaration-index <…/{N+2}/>` | always |
| `dcat:startDate` / `dcat:endDate` | **omitted** (no such field, §2.5) |
| `dct:conformsTo <{FIPM_BASE_URL}/knowledge-models/{id}/{version}>` | added on top of the Wizard's shape: it is the one piece of FIP Manager provenance a reader genuinely needs to interpret a forked questionnaire, and it is already what `rdf.fip_graph` emits |
| pubinfo: `npx:introduces sub:fip` | always |

### 2.5 FIP Manager data with no nanopublication counterpart

Nothing here is invented into the network's vocabulary. Each row says what happens and why.

| FIP Manager data | In the bundle | Why |
|---|---|---|
| `answer.notApplicable: true` (spec 08 §2) | **Omitted from every nanopub**; listed in `index.json` → `notRepresented.notApplicable[questionId]`. | The ontology has `FIP-No-Choice-Declaration` for "no choice made *yet*", which is a different claim from "this question does not apply to us". Publishing the former for the latter would misstate the community's position. There is no third class, and inventing `fipmx:not-applicable` inside a nanopub the network will index would put a FIP-Manager-private term into shared FIP data. |
| `status: "planned-development"` | Emitted as `fip:declares-planned-development-of`. | The property **is** in `fip.ttl` and is the correct one. Flagged here only because §0.1 measured **zero** network uses, so ours would be the first — that is a compatibility note for the facilitators, not a reason to drop it. |
| `declaration.note{lang}` | `fip:considerations`, one literal per language. | Direct counterpart (spec 00 §2). 23 737 network uses. |
| `answer.comment` | `fip:considerations` on the answer's **single** declaration when there is exactly one; otherwise omitted and listed in `index.json` → `notRepresented.answerComments[questionId]`. | `fip:considerations` has no subject that means "the answer as a whole" — its domain is a declaration. Attaching one answer comment to several declarations would duplicate a claim onto statements it was not written about. |
| `declaration.dmpEvidence` (spec 06) | **Omitted**; listed in `index.json` → `notRepresented.dmpEvidence`. | The FIP ontology has no DMP-evidence property, and `fipmx:dmp-evidence` is ours. A DMP URL is also frequently an internal FioDMP link — publishing it into a global, immutable, unretractable graph is a privacy decision nobody has taken (§5, §7 Q6). |
| `declaration.successorFerId` / `successorFreeText` | **Represented**, as the extra `fip:declares-planned-use-of` on the same `planned-replacement` declaration — the ontology's own instruction. | The 179 real `declares-planned-replacement-of` declarations do the same. The unofficial `fip:declares-replacement-from`/`-to` (34 uses each) are **not** used: they are absent from `fip.ttl`. |
| `fip.relatedDmps` | **Omitted**, listed in `index.json` → `notRepresented.relatedDmps` (count only, no URLs). | Same reason as `dmpEvidence`, plus no ontology property. |
| `fip.orphanedAnswers` (spec 07 §4.4) | **Omitted silently.** | By construction these are answers the current questionnaire no longer has a question for; they have no `fip:refers-to-question` object and so cannot be a declaration. `rdf.py` already only surfaces them as Turtle comments. |
| A question id with no `fip:FIP-Question-*` counterpart (forked knowledge model, e.g. the CONFOA area models' own ids) | Declaration **skipped**; listed in `index.json` → `skipped[]` with `questionId` and reason `no_question_individual`. | `fip:refers-to-question`'s range is `fip:FIP-Question`; minting `fip:FIP-Question-confoa-2026-x` would fabricate an ontology individual. This is the same rule `rdf._question_individual_local` already applies. |
| Hidden questions (spec 04 §4) | Skipped, no entry. | Already invisible in every export. |
| `fip.migratedFrom` | Omitted. | FIP-Manager-internal versioning; `dct:conformsTo` on the FIP nanopub already names the current questionnaire. |
| Per-declaration validity period | Omitted (`dcat:startDate`/`endDate` absent) | We have no such field. 16 421 network declarations have one; ours will simply not. Adding one is a v2 data-model question, not something to synthesise from `created_at`. |

### 2.6 Output format

`GET /api/fips/{id}/export/nanopubs.zip` → `application/zip`,
`Content-Disposition: attachment; filename="{fipId}-nanopubs.zip"`.

```
{fipId}-nanopubs/
  index.json
  MANIFEST.md
  np/0001-community.trig
  np/0002-decl-F1-MD-0.trig
  np/0003-decl-F1-D-0.trig
  …
  np/00NN-index.trig
  np/00NN-fip.trig
```

File names are `{n:04d}-{role}.trig`, so **lexicographic file order is the signing order** (§2.3) — a
consumer who does nothing clever still gets it right. `role` for a declaration is
`decl-{questionLocalName}-{declarationIndex}`.

`index.json` — the machine-readable half:

```json
{
  "schema": "fipm-nanopub-bundle/1",
  "generator": {"tool": "FIP Manager", "agent": "https://fipm.example.org", "generatedAt": "2026-09-10T12:00:00Z"},
  "fip": {"id": "K7QX2", "url": "https://fipm.example.org/fips/K7QX2", "title": "FIP of the CONFOA 2026 group A",
          "language": "pt-BR", "license": "CC0-1.0",
          "questionnaire": {"id": "gofair-fip-mini", "version": "1.0.0"}},
  "tempBase": "http://purl.org/nanopub/temp/fipm/K7QX2/",
  "signed": false,
  "nanopubs": [
    {"n": 1, "role": "community", "file": "np/0001-community.trig",
     "tempNanopubIri": "http://purl.org/nanopub/temp/fipm/K7QX2/1/",
     "conceptIri": "http://purl.org/nanopub/temp/fipm/K7QX2/1/community",
     "introduces": "http://purl.org/nanopub/temp/fipm/K7QX2/1/community",
     "referencedBy": [2, 3, 24]},
    {"n": 2, "role": "declaration", "file": "np/0002-decl-F1-MD-0.trig",
     "tempNanopubIri": "http://purl.org/nanopub/temp/fipm/K7QX2/2/",
     "conceptIri": "http://purl.org/nanopub/temp/fipm/K7QX2/2/declaration",
     "questionId": "F1-metadata", "questionIri": "https://w3id.org/fair/fip/terms/FIP-Question-F1-MD",
     "declarationIndex": 0, "status": "current",
     "resourceIri": "http://purl.org/np/RAtIFnvA0nuTJjr4QEBw8j_CNW-8D7xLAC42qLxSZqDMo#ORCID",
     "resourceOrigin": "network", "references": [1], "referencedBy": [23]}
  ],
  "signingOrder": [1, 2, 3, "…", 23, 24],
  "rewrites": [
    {"afterSigning": 1, "replacePrefix": "http://purl.org/nanopub/temp/fipm/K7QX2/1/",
     "withPrefix": "<the trusty base of nanopub 1>", "inFiles": ["np/0002-…", "…", "np/0024-fip.trig"]}
  ],
  "counts": {"nanopubs": 24, "declarations": 21, "skipped": 2},
  "skipped": [{"questionId": "confoa-omics-1", "declarationIndex": 0, "reason": "no_question_individual"}],
  "notRepresented": {
    "notApplicable": ["A2"],
    "answerComments": ["F2"],
    "dmpEvidence": [{"questionId": "F4-metadata", "declarationIndex": 0}],
    "relatedDmps": 2
  },
  "publishPrerequisites": {
    "satisfied": [],
    "missing": [
      {"what": "orcid", "detail": "No ORCID iD is recorded for this FIP's author. Every network nanopub's provenance graph names a person by ORCID; the bundle currently attributes the assertion to the FIP Manager agent IRI instead."},
      {"what": "signing-key", "detail": "An RSA 2048 keypair, generated by `np setup` (nanopub-py) or `MakeKeys.make(\"~/.nanopub/id\", SignatureAlgorithm.RSA)` (nanopub-java). FIP Manager holds no key material."},
      {"what": "key-declaration", "detail": "A published nanopub linking that public key to the ORCID iD (`np setup` offers to publish it)."},
      {"what": "signing-tool", "detail": "nanopub-py >= (whatever is current) or the nanopub-java `np` CLI. Neither is a FIP Manager dependency."},
      {"what": "cross-reference-rewrite", "detail": "Apply `rewrites` in `signingOrder`; nanopub-py rewrites only each nanopub's own temp namespace."},
      {"what": "publication-decision", "detail": "Publishing is irreversible in practice: a nanopub can be retracted but not deleted. See MANIFEST.md."}
    ]
  }
}
```

`MANIFEST.md` — the human half. Same information, plus a copy-pasteable recipe. It states plainly, at the
top: **this bundle is unsigned and has not been published; publishing it is irreversible.** Draft body:

```markdown
# What this is
An unsigned nanopublication bundle for FIP <id>, generated by FIP Manager on <date>.
Nothing here has been published. Nothing here is signed. No key material was used.

# What is still needed to publish
1. An ORCID iD for the person who takes responsibility for these declarations.
2. An RSA 2048 keypair for that ORCID:  `np setup`   (nanopub-py)
   or  MakeKeys.make("~/.nanopub/id", SignatureAlgorithm.RSA)   (nanopub-java)
3. A published key declaration linking the key to the ORCID (`np setup` offers this).
4. A signing tool: nanopub-py, or the nanopub-java `np` CLI.
5. Apply index.json's `rewrites` in `signingOrder` order — see "Order matters" below.

# Order matters
Signing changes a nanopub's IRI (it becomes a hash of its content), so siblings that
reference it must be updated afterwards. Sign in this order — which is also the file
order in np/:
  1. the community nanopub
  2. every declaration nanopub
  3. the declaration index
  4. the FIP nanopub
After each step, replace that nanopub's temp base (index.json → `tempBase`, `nanopubs[].tempNanopubIri`)
with its new trusty base in the files listed under `rewrites[].inFiles`.
nanopub-py does NOT do this for you: `replace_trusty_in_graph` rewrites only the nanopub's own namespace.

# What is in the bundle
<the table from index.json, rendered>

# What FIP Manager data is NOT in the bundle, and why
<the notRepresented / skipped rows, each with its one-line reason from spec 11 §2.5>

# Publishing is irreversible
A published nanopublication is immutable and is replicated across the network. It can be
retracted (a further nanopub saying so) or superseded, but not deleted. Do not publish a FIP
whose community has not agreed to publish it.
```

### 2.7 Endpoints

| Endpoint | Auth | Response |
|---|---|---|
| `GET /api/fips/{id}/export/nanopubs.zip` | `_get_readable_fip` — **anyone who can read the FIP** (owner, admin, public/link visibility, or `X-Edit-Token`), identical to the four existing `export.*` endpoints | `application/zip` |
| `GET /api/fips/{id}/export/nanopubs/preview.trig?n=1` | same | `application/trig; charset=utf-8`, the single nanopub `n`, for the UI's "what will this look like" panel. `n` defaults to the FIP nanopub (the last one). Out-of-range → `404 nanopub_not_found`. |
| `GET /api/fips/{id}/export/nanopubs/index.json` | same | the `index.json` body alone, so the UI can render the manifest without downloading a zip |

Deliberately the same authorization as the other exports and not stricter: the bundle contains strictly less
than `export.ttl` already does (no `dmpEvidence`, no `relatedDmps`, no orphaned answers) and publishes
nothing.

---

## 3. Reading from the network

### 3.1 Verified upstream calls

All four are `POST`s of a SPARQL query to a Nanopub Query repo, `Accept: application/sparql-results+json`,
except `Q0` which is a `GET` of a registered grlc query. Each was run on 2026-09-10 with the timing shown.

**Q0 — communities that have at least one FIP.** Registered query, so the network's own definition of "has a
FIP" (latest non-invalidated FIP nanopub, `dct:created > 2022`) is reused rather than reimplemented:

```
GET {FIPM_NANOPUB_QUERY_URL}/api/RAoQRAype8NkynHDgj5ofRSjFmkeXYIeybunn1EnGpyyQ/fip-communities
Accept: application/sparql-results+json
```

→ 200, 10 522 B as CSV / 39 601 B as JSON, columns `community`, `community_label`, `fip_count`. Sample rows:

```
https://w3id.org/np/RAReiL3Iytsie9Yuxe9a-tyiFQyMsQOFdPtPCg9uUtMA8#FTF,FAIR Technical Framework Community,8
http://purl.org/np/RANS1FDYGKYE6IzIP6QuofHtLpvPfGQsCw1gyBmR_n9Ls#ACTRIS-ASC,ACTRIS ASC community | ACTRIS Atmospheric simulation chamber data centre unit,5
http://purl.org/np/RA39E3Dj61wCQkWCkK707UWBEBvRj2-hUDH5V5BicUgrg#ACTRIS-ARES,ACTRIS ARES community | ACTRIS Data Center unit for Aerosol REmote Sensing,4
http://purl.org/np/RA39E3Dj61wCQkWCkK707UWBEBvRj2-hUDH5V5BicUgrg#ACTRIS-ARES,ACTRIS Data Center unit for Aerosol REmote Sensing,4
```

**The last two rows are the same community with two labels** (from two nanopub versions). Dedupe by
`community` IRI, keeping the longest label and the maximum `fip_count`. This is not optional — the raw list
has duplicates.

**Q1 — the FIPs of one community, newest first.** Endpoint `POST {base}/repo/type/92efd7a0…`:

```sparql
prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#>
prefix fip:  <https://w3id.org/fair/fip/terms/>
prefix dct:  <http://purl.org/dc/terms/>
prefix npa:  <http://purl.org/nanopub/admin/>
prefix npx:  <http://purl.org/nanopub/x/>
prefix np:   <http://www.nanopub.org/nschema#>
prefix dcat: <https://www.w3.org/ns/dcat#>
select distinct ?fip_np ?label ?index ?created ?startDate ?endDate where {
  graph npa:graph {
    ?fip_np npa:hasValidSignatureForPublicKey ?pk ;
            npx:hasNanopubType fip:FAIR-Implementation-Profile ;
            dct:created ?created ; np:hasAssertion ?a .
    filter not exists { ?x npx:invalidates ?fip_np ; npa:hasValidSignatureForPublicKey ?pk }
    filter not exists { ?y npx:supersedes  ?fip_np ; npa:hasValidSignatureForPublicKey ?pk }
  }
  graph ?a {
    ?fip a fip:FAIR-Implementation-Profile ;
         fip:declared-by ?COMMUNITY ;
         rdfs:label ?label .
    optional { ?fip fip:has-declaration-index ?index }
    optional { ?fip dcat:startDate ?startDate }
    optional { ?fip dcat:endDate   ?endDate }
  }
} order by desc(?created)
```

→ 200, 781 B, 0.29 s for `?COMMUNITY` = `<http://purl.org/np/RAoZsfUhNx4sYz-IXfsp1xPBH1-YgTGtHpp3BbMQtWHJg#PARCToxicology>`, returning 4 FIPs:

```
https://w3id.org/np/RAKa7vUwc8qVbktDqDSpuq7lRrrKcjPKvkB4Tn7WHvr7E,PARC Toxicology ,https://w3id.org/np/RATReWJWVaVcOU7UrhKTkMPuNW4P_hmuD07FyOm4UtN3U,2026-09-07T12:48:22.000Z,,
https://w3id.org/np/RAllERFvC1zFXu7uTmQ1Dibvrh-VIr4l1XKM54oQKeZog,PARC TOXRIC FIP,https://w3id.org/np/RA7UpAcMN5tmQR8cfFd1CzzUm1H2XVWPtChzEJRVQSkXE,2024-01-22T20:09:10.000Z,2023-04-14,2026-04-30
```

**Q2 — the declarations of one FIP, via its index.** Endpoint `POST {base}/repo/full`:

```sparql
prefix fip:  <https://w3id.org/fair/fip/terms/>
prefix np:   <http://www.nanopub.org/nschema#>
prefix npx:  <http://purl.org/nanopub/x/>
prefix dcat: <https://www.w3.org/ns/dcat#>
select distinct ?decl_np ?question ?rel ?resource ?considerations ?nochoice ?startDate ?endDate where {
  graph ?ih { ?INDEX np:hasAssertion ?ia }
  graph ?ia { ?INDEX npx:includesElement ?decl_np }
  graph ?dh { ?decl_np np:hasAssertion ?da }
  graph ?da {
    ?decl fip:refers-to-question ?question .
    optional { ?decl ?rel ?resource .
      filter(?rel in (fip:declares-current-use-of, fip:declares-planned-use-of,
                      fip:declares-planned-replacement-of, fip:declares-planned-development-of)) }
    optional { ?decl fip:considerations ?considerations }
    optional { ?decl dcat:startDate ?startDate }
    optional { ?decl dcat:endDate   ?endDate }
    optional { ?decl a fip:FIP-No-Choice-Declaration . bind(true as ?nochoice) }
  }
} order by ?question
```

→ 200, 19 354 B, 0.37 s, **89 declarations** for
`?INDEX` = `<https://w3id.org/np/RATReWJWVaVcOU7UrhKTkMPuNW4P_hmuD07FyOm4UtN3U>`.

Three things this query got right the obvious version got wrong, all verified the hard way:

- **Never hardcode `#assertion`.** Older nanopubs use `<np>#assertion`, newer ones `<np>/assertion`. Joining
  through `graph ?ih { ?INDEX np:hasAssertion ?ia }` works for both; hardcoding `#assertion` returned **0
  rows** for this very index.
- **`select distinct` is mandatory.** Without it the same query returned 356 rows for the same 89
  declarations.
- Questions include `fip:FIP-S-Question-F1-Persistency-Policy`, `…-F2-Metadata-Editor`,
  `…-F4-Persistency-Policy`, `…-FAIR-Enrichment-Service` — FSR questions, not among the 21. They go to
  `unmapped` (§3.3).

**Q3 — labels and types for a batch of resource IRIs.** Endpoint `POST {base}/repo/full`, `?RESOURCES` a
`values` block of at most 100 IRIs:

```sparql
prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#>
prefix fip:  <https://w3id.org/fair/fip/terms/>
prefix skos: <http://www.w3.org/2004/02/skos/core#>
prefix dct:  <http://purl.org/dc/terms/>
prefix npa:  <http://purl.org/nanopub/admin/>
prefix npx:  <http://purl.org/nanopub/x/>
prefix np:   <http://www.nanopub.org/nschema#>
select distinct ?resource ?label ?comment ?match ?type ?date where {
  values ?resource { ?RESOURCES }
  graph npa:graph {
    ?np npa:hasValidSignatureForPublicKey ?pk ; np:hasAssertion ?a ; dct:created ?date .
    filter not exists { ?x npx:invalidates ?np ; npa:hasValidSignatureForPublicKey ?pk }
  }
  graph ?a {
    ?resource a fip:FAIR-Enabling-Resource ; rdfs:label ?label .
    optional { ?resource rdfs:comment ?comment }
    optional { ?resource skos:exactMatch ?match }
    optional { ?resource a ?type . filter(strstarts(str(?type), "https://w3id.org/fair/fip/terms/")) }
  }
}
```

→ 200, 4 080 B, 0.29 s for three IRIs. Post-processing is required and non-obvious:

- One resource returns **many rows** (one per `fip:` type × per label variant × per nanopub version). Group by
  `?resource`; keep the `?label`/`?comment`/`?match` from the row with the **maximum `?date`**; union all
  `?type` values.
- Do **not** add `filter not exists { ?y npx:supersedes ?np … }` here: it silently dropped
  `…#NetCDF_CF1.7`, whose describing nanopub has been superseded but whose IRI is still the one 5 000+
  declarations point at. Filter retractions (`npx:invalidates`) only.

**Q4 — FER full-text search** (v2 roadmap, §3.2). Endpoint `POST {base}/repo/text`:

```sparql
prefix rdfs:   <http://www.w3.org/2000/01/rdf-schema#>
prefix fip:    <https://w3id.org/fair/fip/terms/>
prefix npa:    <http://purl.org/nanopub/admin/>
prefix npx:    <http://purl.org/nanopub/x/>
prefix search: <http://www.openrdf.org/contrib/lucenesail#>
select distinct ?np ?label (max(?score) as ?s) where {
  graph npa:graph {
    ?np rdfs:label ?label ; npa:hasValidSignatureForPublicKey ?pk .
    filter exists { ?np npx:hasNanopubType fip:FAIR-Enabling-Resource }
    filter not exists { ?x npx:invalidates ?np ; npa:hasValidSignatureForPublicKey ?pk }
  }
  ?np search:matches [ search:query ?QUERY ; search:score ?score ]
} group by ?np ?label order by desc(?s) limit ?LIMIT
```

→ 200, 630 B, 0.45 s for `?QUERY` = `"orcid"`, top hit
`https://w3id.org/np/RAncf2hj1w4rywAclhA_R0vx54K-OJNGdUjyeycfWF6i0` /
`"FAIR-enabling resource: ORCID-AAI | Open Researcher and Contributor ID AAI service"`.

**Deliberately not used:** the registered `get-fip-decl-details` query
(`RAoyVY3PFKl2LgnV4O4JmyepekSn8jxCGq0T2CsXv6AMs`). It takes **no parameters** and returns *every* declaration
in the network: measured **11 326 539 bytes, 24 237 rows, 3.77 s**. Q1+Q2 answer the same question for one
community in **19 KB and 0.66 s combined**. The registered query is still the right *reference* for the
network's semantics (its SPARQL is quoted in §0.2's spirit and informed Q2), but it cannot sit behind a
request-time proxy.

### 3.2 Our endpoints

All three are `GET`, unauthenticated (a workshop participant has no account), and read-only.

| Endpoint | Upstream | Response |
|---|---|---|
| `GET /api/network/fip-communities?q=&limit=&offset=` | Q0, then filter/paginate **in-process** | `{"items":[{"iri","label","fipCount"}],"total":n,"cachedAt":"…"}` |
| `GET /api/network/fips/{communityIri}` | Q1 → newest FIP → Q2 → Q3 for its resources | §3.3 |
| `GET /api/network/fers?q=&limit=` | Q4, then Q3 for labels/types | `{"items":[{"iri","label","comment","homepage","types","ferTypeKey"}],"total":n}` — **v2 roadmap item**, shipped behind the same flag but not wired into the FER picker for CONFOA |

`communityIri` is a full IRI and therefore path-encoded (`%3A`, `%2F`, `%23`). FastAPI decodes it once;
the handler **must** validate it before use (§5).

- `q` is matched case-insensitively, NFC-normalised, as a substring of the label — in Python, over the cached
  Q0 result. It is **never** interpolated into SPARQL.
- `limit` default 50, max 200. `offset` default 0.
- Every response carries `cachedAt` (when the upstream call actually happened) and `source`
  (`FIPM_NANOPUB_QUERY_URL`), so a stale UI is diagnosable.

Errors, all as `{"detail": "<code>"}`:

| Code | Status | When |
|---|---|---|
| `network_disabled` | 503 | `FIPM_NETWORK_ENABLED=false` |
| `network_unavailable` | 502 | upstream timeout, connection error, non-2xx, or a response that is not the expected JSON shape |
| `network_response_too_large` | 502 | upstream body exceeded the cap (§5) |
| `invalid_community_iri` | 400 | the path segment is not an `http(s)` IRI |
| `network_fip_not_found` | 404 | Q1 returned no FIP for that community |

### 3.3 `GET /api/network/fips/{communityIri}` — the shape, and the question mapping

```json
{
  "community": {"iri": "http://purl.org/np/RAoZ…#PARCToxicology",
                "label": "PARCToxicology | PARC Chemicals Toxicology Community"},
  "fip": {"nanopubIri": "https://w3id.org/np/RAKa7vUwc8qVbktDqDSpuq7lRrrKcjPKvkB4Tn7WHvr7E",
          "label": "PARC Toxicology", "indexIri": "https://w3id.org/np/RATReWJ…",
          "created": "2026-09-07T12:48:22Z", "startDate": null, "endDate": null,
          "otherVersions": [{"nanopubIri": "…", "label": "PARC TOXRIC FIP", "created": "2024-01-22T20:09:10Z"}]},
  "questions": [
    {"questionId": "F1-metadata", "questionIri": "https://w3id.org/fair/fip/terms/FIP-Question-F1-MD",
     "declarations": [
       {"nanopubIri": "https://w3id.org/np/RA…", "status": "current",
        "resource": {"iri": "http://purl.org/np/RAtIF…#ORCID", "label": "ORCID | Open Researcher and Contributor ID",
                     "comment": "…", "homepage": "https://fairsharing.org/…",
                     "types": ["https://w3id.org/fair/fip/terms/Identifier-service", "…"],
                     "ferTypeKey": "identifier-service",
                     "inCatalogue": {"ferId": "https://orcid.org/", "matchedBy": "homepage"}},
        "considerations": "…", "startDate": null, "endDate": null}
     ]}
  ],
  "unmapped": [
    {"questionIri": "https://w3id.org/fair/fip/terms/FIP-S-Question-F1-Persistency-Policy",
     "declarations": [ … same shape … ]}
  ],
  "cachedAt": "2026-09-10T12:00:00Z", "source": "https://query.knowledgepixels.com"
}
```

- `questions` is **all 21**, in `gofair-fip-mini` order, each with a possibly empty `declarations` — so the
  detail view renders our familiar layout with visible gaps, which is the point of showing a network FIP at
  all.
- The mapping is the **inverse of `rdf._question_individual_local`**: strip
  `https://w3id.org/fair/fip/terms/FIP-Question-`, then `-MD` → `-metadata`, `-D` → `-data`, unsuffixed
  unchanged; accept only the 21 in `rdf.KNOWN_QUESTION_INDIVIDUALS`. Ship it as a new
  `rdf.question_id_from_individual(iri) -> str | None` next to its inverse, with a test asserting the two are
  mutually inverse over all 21 — one function, one place, no second table to drift.
- Anything else (an `FIP-S-Question-*`, an `FSR` question, a future 22nd question) goes to `unmapped`,
  keyed by IRI, rendered read-only.
- `status` is the inverse of `rdf.STATUS_PREDICATE`, plus `?nochoice → "none"`.
- `ferTypeKey` is derived from the resource's `types` by inverting `data/fers/fer-types.json`'s `iri` field
  (via `fer_types.get_fer_types`). A resource carrying several of the 12 (common — `HTTPS` is both
  `Communication-protocol` and `Authentication-and-authorization-service`) resolves to the one matching the
  question's own `ferType`; failing that, the first in `fer-types.json` order; failing that, `null`.
- `inCatalogue` is filled by matching the network resource against our `fers` table, in this order:
  (1) `Fer.id == resource.iri` (a FER we already imported, `source="network"`);
  (2) `Fer.homepage == resource.homepage` or `Fer.id == resource.homepage` — the `skos:exactMatch` case, which
  is how `http://purl.org/np/RA…#ORCID` finds our seed row `https://orcid.org/`;
  (3) exact case-folded label match against `Fer.label_search`.
  `matchedBy` records which rule fired, so the UI can show "same as your catalogue's *ORCID*" with the right
  confidence.

### 3.4 Config, caching, timeouts

| Setting | Default | Meaning |
|---|---|---|
| `FIPM_NETWORK_ENABLED` (`Settings.network_enabled: bool`) | `true` | `false` → all three endpoints `503 network_disabled` and the frontend hides the Network FIPs nav entry (`GET /api/health` reports it) |
| `FIPM_NANOPUB_QUERY_URL` (`Settings.nanopub_query_url: str`) | **`https://query.knowledgepixels.com`** (verified §0) | Scheme + host only, no trailing slash. Every upstream URL is built as `{this}/repo/…` or `{this}/api/…`. The verified mirror `https://query.petapico.org` is a drop-in alternative. |
| `FIPM_NETWORK_TIMEOUT_SECONDS` (`Settings.network_timeout_seconds: float`) | `10.0` | Total per upstream request (`httpx.Timeout(10.0, connect=5.0)`) |
| `FIPM_NETWORK_CACHE_TTL_SECONDS` (`Settings.network_cache_ttl_seconds: int`) | `900` (15 min) | Per cache entry |
| `FIPM_NETWORK_MAX_RESPONSE_BYTES` (`Settings.network_max_response_bytes: int`) | `8 * 1024 * 1024` | §5 |

Cache: a new `fipm/network.py` module with a process-local `dict[str, tuple[float, Any]]` guarded by a
`threading.Lock`, keyed by the logical call (`"communities"`, `f"fips:{communityIri}"`,
`f"fers:{q}:{limit}"`, `f"resources:{sorted_iris_hash}"`), capped at 256 entries with
least-recently-used eviction, and a `reset_network_cache()` for tests — the same shape and the same testing
affordance as `fipm.auth.reset_rate_limits()`. **No DB table, no disk.** A restart empties it; that is fine
for a 15-minute TTL and keeps the offline-laptop story ("nothing to clean up") intact.

A cache **hit is served even when stale** if the upstream call fails, with `cachedAt` telling the truth and a
`"stale": true` flag — a flaky conference wifi should degrade to yesterday's list, not to a 502. A miss plus a
failure is a 502.

`httpx` moves from `[dependency-groups] dev` to `[project] dependencies` in `backend/pyproject.toml`. It is
already installed in every dev and CI environment (the test client uses it), so this is a declaration fix, not
a new dependency in practice.

Concurrency: Q1→Q2→Q3 are sequential (each needs the previous result). Q0 and Q4 are single calls. No endpoint
makes more than 3 upstream requests; with a 10 s timeout each, worst case is 30 s, so these handlers run in a
threadpool (plain `def`, which is what FastAPI does with sync handlers, matching every other router here) and
the frontend shows a spinner with a cancel.

### 3.5 Frontend: the Network FIPs pages

| Route | Component | Content |
|---|---|---|
| `/network` | `views/NetworkFipList.vue` | Search box (debounced 300 ms, filters client-side over the fetched list — the backend also accepts `q`, used on first load only), a table of communities: label, `fipCount`, and a link. Empty state distinguishes "no results for *x*" from `network_disabled` from `network_unavailable` (with a Retry). |
| `/network/:communityIri` | `views/NetworkFipDetail.vue` | The community header (label, FIP label, `created`, a link to the FIP nanopub on `https://nanodash.knowledgepixels.com/explore?id=…`), then the 21 questions in `components/QuestionCard.vue`'s **read-only** layout, reusing `StatusBadge.vue` for the status and showing the resource label with its `inCatalogue` hint. An `<details>` "Other declarations found (not part of the FIP mini-questionnaire)" holds `unmapped`. A version switcher offers `fip.otherVersions`. |

Both routes are `meta: { requiresAuth: false }` and both are hidden from the nav when
`GET /api/health` reports `networkEnabled: false`.

`frontend/src/api/network.ts` mirrors the three endpoints; `frontend/src/types/` gains the response types.
i18n keys under `network.*` in `data/i18n/` for en, pt-PT, pt-BR (translator, not builder).

**"Prepare nanopublications"** appears in two places, both calling the §2.7 endpoints:

- `views/FipRead.vue`: a button next to the existing exports, opening a dialog that fetches
  `…/export/nanopubs/index.json`, renders `counts`, `skipped`, `notRepresented` and `publishPrerequisites`
  as three short lists, shows the `preview.trig` of the FIP nanopub in a `<pre>`, and offers **Download
  bundle (.zip)**. The dialog's first line is the manifest's first line: *unsigned, not published*.
- `components/ExportButtons.vue`: a plain **Nanopublications (.zip)** entry alongside JSON/CSV/TTL/JSON-LD,
  for people who already know what they want.

### 3.6 "Use as starting point"

On `/network/:communityIri`, a primary action **Use as starting point** → a small form (FIP title, language,
and — if signed in — owned vs standalone) → one `POST /api/fips` with a prefilled `answers` array, landing the
user in `FipEditor.vue` on a normal, fully editable FIP. It creates a FIP; it does not create a link, a
subscription or a sync.

The prefill is computed **server-side** by a new
`POST /api/fips/from-network` (body `{communityIri, title?, language?, visibility?, sessionId?}`), not
client-side, for two reasons: the mapping needs the `fers` table and `fer-types.json`, and the FER-import
side effect below must be transactional with the FIP creation. It reuses `create_fip`'s authorization ladder
verbatim (session participant / signed-in user / anonymous standalone under `FIPM_ANONYMOUS_FIPS`, spec 09
§1), the same rate limit, and the same `visibility` rules.

Per network declaration, in order:

1. Question not among the 21 → **dropped**, counted in the response's `skipped`.
2. `status: "none"` → an answer with a single declaration `{status: "none", ferFreeText: <the
   considerations text, truncated to 500 chars>}` if there is one, else the question is left unanswered.
   (`Declaration` requires exactly one of `ferId`/`ferFreeText`, so a bare "none" needs *some* text; where
   there is none, an unanswered question is the honest result.)
3. Resource already in our catalogue (`inCatalogue.matchedBy` fired) → `{ferId: <our Fer.id>, status}`.
4. Otherwise → **create a `fers` row** with `id = <the network resource IRI>`, `source = "network"`,
   `label = {<the FIP's language>: <the network label>}`, `label_search` = the label lowercased,
   `type = <ferTypeKey>` (falling back to the question's `ferType`), `homepage = <skos:exactMatch or null>`,
   `owner_id = <the creating user, or NULL>` — then `{ferId: <that IRI>, status}`.
5. `considerations` → `note: {<language>: <text>}` on the declaration.

**Decision: import as a catalogue FER with `source="network"`, not as `ferFreeText`.** Justification, since
the brief asks for one:

- Our `Declaration.ferId` validator already accepts exactly this shape:
  `_FER_IRI_RE = ^(?:https?://|urn:)\S+$` matches `http://purl.org/np/RA…#HTTPS`. No schema change, no new
  validator, no migration.
- `ferFreeText` would **destroy the network identity**: `rdf._emit_fer` mints
  `{base_url}/fers/text/{sha256[:16]}` for free text and stamps `fipmx:free-text true`. The one thing worth
  keeping from a network import is the IRI that ties our declaration to the same resource 5 000 other
  declarations point at. A hash of a label does not do that.
- A catalogue row makes the whole application work unchanged: the FER picker lists it, the convergence matrix
  (which groups by `ferId`, spec 03 §1) puts our group and the network FIP in the same column, and
  §2 exports it back out as the same IRI — a genuine round-trip.
- Catalogue pollution is the real cost, and it is bounded and reversible: rows are created **only** when a
  human clicks "use as starting point" (never while browsing), only for resources we could not already
  match, and the existing admin FER **promote/merge** tool (spec 05 §1) folds a network row into a seed row
  afterwards. `GET /api/fers`'s anonymous source filter gains `"network"` alongside
  `("seed", "user-promoted", "model")` so participants see them.
- An existing row with that id is **left untouched** whatever its source, exactly like spec 08 §1.3's inline-FER
  promotion. Import is idempotent.

Response: `{fip: <the normal FIP payload>, editToken?, imported: {declarations: n, fersCreated: n, fersMatched: n}, skipped: [{questionIri, reason}]}`.
`FipEditor.vue` shows a one-time banner: *"Prefilled from the ⟨community⟩ FIP in the nanopublication network
(⟨date⟩). n declarations imported, m skipped. Everything here is editable and nothing is sent back to the
network."*

---

## 4. Data model changes

Two, both additive, `SCHEMA_VERSION` **6 → 7**.

| Change | Shape | Why minimal |
|---|---|---|
| `fers.source` gains the value `"network"` | no DDL — `source` is already a free `String` with an application-level vocabulary (`seed`, `user`, `user-promoted`, `model`) | §3.6. The only code change is adding `"network"` to the anonymous-visible tuple in `routers/fers.py` and to the `source` filter's documented values. |
| `fips.network_origin` | JSON nullable — `{"communityIri": str, "fipNanopubIri": str, "indexIri": str \| null, "fetchedAt": "<iso>"}`; NULL for every FIP not created from the network | One `_EXPECTED_COLUMNS` entry (`("fips", "network_origin", "JSON")`), no new table, no data migration (NULL is the pre-v7 value and means "not from the network"). Read by `FipEditor.vue`'s banner, by `build_export_json` (as `networkOrigin`) and by `rdf.fip_graph` as `prov:wasDerivedFrom <fipNanopubIri>` on the FIP node — which is a *true* provenance statement and the one thing a reader of our RDF would want. |

Deliberately **not** added:

- No table of network communities, FIPs or declarations. The cache is in-process (§3.4); persisting a mirror
  of someone else's immutable, queryable data buys staleness and a migration burden and nothing else.
- No `fers.network_nanopub_iri`: for a `source="network"` row the `id` **is** the nanopub IRI.
- No column for the exported bundle. It is computed on demand, deterministically, from data we already have.
- No `fips.published_nanopubs`: we publish nothing.

---

## 5. Security and privacy

| Concern | Measure |
|---|---|
| SSRF | Every upstream URL is built as `f"{settings.nanopub_query_url}/repo/full"` etc. — a **fixed** base from config plus a **literal** path. No user input reaches the URL: `communityIri` and `q` go into the SPARQL body or into in-process filtering, never into a path or host. `FIPM_NANOPUB_QUERY_URL` is validated at startup (`check_network_safety()`, alongside `check_mail_safety()`): `https` scheme, a hostname, no userinfo, no path — refuse to start otherwise. `httpx` is called with `follow_redirects=False`: a redirect is a `network_unavailable`, never a hop to another host. |
| SPARQL injection | `communityIri` is substituted as `<{iri}>` **only after** passing `rdf._is_http_iri` **and** a reject-list of `>`, `<`, `"`, `\`, `{`, `}`, `|`, `^`, backtick, space and any C0/DEL character — i.e. exactly the characters that could terminate an IRI literal in SPARQL. Anything else → `400 invalid_community_iri`. Resource IRIs in Q3's `values` block get the identical treatment, and any that fail are dropped from the batch rather than failing the request. `q` **never** reaches SPARQL: `/fip-communities` and `/fers` filter in Python; Q4's `?QUERY` is a Lucene string bound via a `values` clause, length-capped at 100 characters and stripped of `"` and `\`. |
| Response size | `httpx.stream` with a running byte counter, aborted at `FIPM_NETWORK_MAX_RESPONSE_BYTES` (8 MiB) → `502 network_response_too_large`. This is a real risk, not a theoretical one: the network's own `get-fip-decl-details` returns 11.3 MB (§3.1). |
| No user data leaves the deployment | This iteration sends **only** a SPARQL query built from the fixed templates in §3.1, whose sole variable parts are a network-supplied community IRI, a network-supplied resource IRI, and a search string the user typed *for the purpose of searching*. No FIP content, no FIP id, no community name, no email, no session, no edit token, no `User-Agent` carrying an install identifier. `httpx` is configured with an explicit `headers={"Accept": …, "User-Agent": "FIPManager"}` so no version or host leaks by default. |
| The export sends nothing | `GET …/nanopubs.zip` makes **no** outbound request. It is pure local serialisation. |
| Private FIP content in the bundle | `prov:wasDerivedFrom <fip_url>` is omitted for a `visibility: "private"` FIP (§2.4) so a bundle that leaves the building does not advertise a private URL. `dmpEvidence` and `relatedDmps` are omitted for every FIP (§2.5), which also removes the FioDMP-URL leak. |
| Log hygiene | Upstream failures log the endpoint path, the status and the elapsed time — never the response body, never the query string. |
| Rate limiting | The 15-minute cache is the rate limiter for the upstream: a hot cache means at most 4 upstream calls per 15 minutes for the whole deployment regardless of traffic. No per-IP limit on these read endpoints (they are cheap and cached); the existing global body-size middleware does not apply to `GET`. **UNVERIFIED:** Nanopub Query publishes no rate limit, result-size limit or query timeout that I could find — neither `query.knowledgepixels.com` (no `/api` docs endpoint, `GET /api/` is 404) nor the `knowledgepixels/nanopub-query` README. The measured headers expose `Nanopub-Query-Version: 1.28.1`, `Nanopub-Query-Status: READY` and load counters but no rate-limit headers. We therefore behave conservatively by construction (cache-first, ≤3 requests per handler, 10 s timeout) rather than relying on a documented allowance. |

---

## 6. Tests

Recorded fixtures only. **No test makes a live network call**, and CI must pass with no outbound network.

New directory `backend/tests/fixtures/network/`, each file a byte-for-byte capture of a real 2026-09-10
response, recorded with the commands given (so anyone can re-record):

| File | Recorded from | Content | Size |
|---|---|---|---|
| `fip-communities.json` | `GET https://query.knowledgepixels.com/api/RAoQRAype8NkynHDgj5ofRSjFmkeXYIeybunn1EnGpyyQ/fip-communities` with `Accept: application/sparql-results+json` | The real community list, **including** the duplicated `ACTRIS-ARES` rows, so the dedupe in §3.2 is tested against the actual defect | ~40 KB |
| `parc-fips.json` | Q1 with `?COMMUNITY = <http://purl.org/np/RAoZsfUhNx4sYz-IXfsp1xPBH1-YgTGtHpp3BbMQtWHJg#PARCToxicology>` | 4 FIP versions, newest `RAKa7vUwc8qVbktDqDSpuq7lRrrKcjPKvkB4Tn7WHvr7E`, index `RATReWJ…`, two with `dcat:startDate`/`endDate` and two without | ~1.5 KB |
| `parc-declarations.json` | Q2 with `?INDEX = <https://w3id.org/np/RATReWJWVaVcOU7UrhKTkMPuNW4P_hmuD07FyOm4UtN3U>` | 89 declarations across 21 mapped questions **and 4 `FIP-S-Question-*` rows** | ~35 KB |
| `parc-resources.json` | Q3 over the ~40 distinct resource IRIs in the file above | Multi-row-per-resource, multi-label, multi-type — the exact post-processing case of §3.1 | ~60 KB |
| `fer-search-orcid.json` | Q4 with `?QUERY = "orcid"` | 5 hits | ~1 KB |

Recording is a documented one-liner per file in `backend/tests/fixtures/network/README.md` (the curl commands
from §3.1 verbatim), so re-recording after an upstream change is mechanical and reviewable as a diff.

Fixtures are injected by monkeypatching one seam — `fipm.network._post_sparql` /
`fipm.network._get_grlc` — not by patching `httpx` globally, so a test that forgets to patch fails with
a clear "no fixture registered for this call" rather than attempting a real request. `conftest.py` gains an
autouse fixture that **raises** on any un-patched call into `fipm.network`, which is what actually enforces
"no live network in tests".

### 6.1 Backend tests

`backend/tests/test_ac_11_01_network_communities.py`
1. `GET /api/network/fip-communities` → 200; the duplicated `ACTRIS-ARES` IRI appears **once**, with the
   longer label and `fipCount: 4`.
2. `?q=actris` matches case-insensitively and matches the second label half after the `|`.
3. `?limit=2&offset=1` paginates; `total` is the unpaginated count.
4. A second call within the TTL performs **no** second upstream call (the seam is called once).
5. TTL expiry (monkeypatched to 0) performs a second call.
6. Upstream failure with a warm cache → 200 with `"stale": true`; with a cold cache → `502 network_unavailable`.
7. `FIPM_NETWORK_ENABLED=false` → `503 network_disabled` on all three endpoints (env + `get_settings.cache_clear()`, the spec-09 pattern).

`backend/tests/test_ac_11_02_network_fip_detail.py`
8. `GET /api/network/fips/{encoded PARCToxicology IRI}` → 200; `questions` has exactly 21 entries in
   `gofair-fip-mini` order; the F1-MD entry's declarations carry `status: "current"` and a resolved label.
9. The 4 `FIP-S-Question-*` declarations land in `unmapped`, keyed by IRI, and in **no** `questions` entry.
10. A resource with several `fip:` type classes resolves `ferTypeKey` to the one matching the question's
    `ferType`.
11. `inCatalogue.matchedBy == "homepage"` for a network resource whose `skos:exactMatch` equals a seed FER's
    id, and `null` for one with no match.
12. `fip.otherVersions` lists the 3 older FIPs, newest excluded.
13. A community IRI containing `>` → `400 invalid_community_iri`, and the seam is **never** called.
14. `rdf.question_id_from_individual` is the exact inverse of `rdf._question_individual_local` over all 21
    ids, and returns `None` for `FIP-S-Question-F1-Persistency-Policy` and for a bare
    `https://example.org/x`.

`backend/tests/test_ac_11_03_nanopub_export.py`
15. `GET /api/fips/{id}/export/nanopubs.zip` on a FIP with 3 declarations → 200, `application/zip`, 6 entries
    under `np/` plus `index.json` and `MANIFEST.md`; file names sort into `signingOrder`.
16. Every `.trig` parses as TriG into an rdflib `Dataset` with exactly 4 named graphs, and each has
    `this: a np:Nanopublication` with `np:hasAssertion`/`hasProvenance`/`hasPublicationInfo` — i.e. every file
    satisfies `extract_np_metadata`'s query (asserted by running that SPARQL, not by eyeballing).
17. **No `npx:hasSignature`, `npx:hasPublicKey`, `npx:hasAlgorithm` or `npx:hasSignatureTarget` anywhere in
    the bundle**, and no `nt:` triple. (The regression test that this stays an *unsigned* export.)
18. Every IRI in every file that is not in the bundle's temp base, the `fip:`/`npx:`/`dct:`/`prov:`/`dcat:`
    namespaces or a resolvable resource, is absent — concretely: every temp IRI in the bundle starts with
    `http://purl.org/nanopub/temp/fipm/{fipId}/`, and every `{n}` referenced in `rewrites` exists.
19. A `status: "current"` declaration emits `fip:declares-current-use-of`; `"planned-replacement"` with a
    successor emits both `declares-planned-replacement-of` and `declares-planned-use-of`; `"none"` emits
    `a fip:FIP-No-Choice-Declaration` and **no** `declares-*`; `"planned-development"` emits
    `declares-planned-development-of`.
20. An `answer.notApplicable: true` produces **no** nanopub and appears in
    `index.json.notRepresented.notApplicable`.
21. A declaration on a question with no `fip:FIP-Question-*` counterpart (a CONFOA area model) is absent from
    `np/` and present in `index.json.skipped` with `reason: "no_question_individual"`.
22. `dmpEvidence` and `relatedDmps` appear nowhere in any `.trig` and are counted in `notRepresented`.
23. The index nanopub's `npx:includesElement` set equals exactly the set of declaration nanopub temp IRIs, and
    its provenance graph carries `a npx:IndexAssertion`.
24. The FIP nanopub's `fip:has-declaration-index` is the index nanopub's temp IRI and its `fip:declared-by` is
    nanopub 1's concept IRI.
25. A `visibility: "private"` FIP's bundle contains **no** `prov:wasDerivedFrom` to the FIP URL.
26. `preview.trig?n=1` returns the community nanopub as `application/trig`; `n=999` → `404`.
27. Authorization: the bundle is downloadable by an anonymous caller for a `link`-visibility FIP, by the
    edit-token holder, by the owner and by an admin; `403` for an anonymous caller on a `private` FIP —
    i.e. identical to `export.ttl` (asserted by comparing status codes across the two endpoints in a loop).
28. Determinism: two calls produce **byte-identical** zips except for `generatedAt` (asserted by generating
    with a frozen clock).

`backend/tests/test_ac_11_04_network_prefill.py`
29. `POST /api/fips/from-network` with the PARC fixtures → 201; the created FIP has declarations on the mapped
    questions; `imported.fersCreated + imported.fersMatched` equals the number of imported declarations.
30. A network resource matching a seed FER by homepage reuses the **seed** `ferId` and creates no row.
31. An unmatched network resource creates one `fers` row with `source="network"`, `id` = the nanopub-fragment
    IRI, and the ferTypeKey from §3.3; a second import of the same community creates **no** duplicate row.
32. `GET /api/fers` as an anonymous caller lists the `source="network"` row.
33. `fips.network_origin` is set to the `{communityIri, fipNanopubIri, indexIri, fetchedAt}` of the import,
    and `rdf.fip_graph` emits `prov:wasDerivedFrom <fipNanopubIri>` on the FIP node.
34. `export.json` round-trips `networkOrigin` through `POST /api/fips/import`.
35. `FIPM_ANONYMOUS_FIPS=false` → `403 anonymous_fips_disabled` for an anonymous caller, unchanged from
    spec 09 §3.
36. `SCHEMA_VERSION` 6 → 7 upgrade adds `fips.network_origin` to an existing database and leaves existing rows
    NULL (the `test_ac_05_7_schema_upgrade.py` pattern).

`backend/tests/test_ac_11_05_network_safety.py`
37. `check_network_safety()` raises for `FIPM_NANOPUB_QUERY_URL` with an `http://` scheme, with a path, with
    userinfo, or empty.
38. `follow_redirects` is `False` on the client (asserted on the constructed client, and by a fixture that
    returns a 302 → `502 network_unavailable`).
39. A fixture whose body exceeds the cap → `502 network_response_too_large`.
40. `q` with `"` / `\` / a 500-character string is length-capped and character-stripped before it reaches
    Q4's `values` block (asserted on the generated SPARQL string).

### 6.2 Frontend tests

`frontend/src/views/NetworkFipList.test.ts` — renders the deduped list from a mocked `api/network`; the
search box filters; `network_disabled` renders the disabled state with no retry button;
`network_unavailable` renders a retry that re-calls.

`frontend/src/views/NetworkFipDetail.test.ts` — renders 21 question cards with the mocked detail payload;
empty questions render as gaps, not omissions; the `unmapped` `<details>` shows 4 entries; **Use as starting
point** posts to `from-network` once and navigates to the editor.

`frontend/src/components/ExportButtons.test.ts` (extended) — the nanopublication entry appears and links to
`…/export/nanopubs.zip`.

---

## 7. Decisions taken, and open questions for the facilitators

Decisions taken here so implementation is not blocked (recorded per the working-style note in PLAN §9):

- **D1.** One nanopub per declaration plus community, index and FIP nanopubs — the Wizard's shape exactly
  (§2.1), because it makes a FIP Manager FIP indexable by the network's existing FIP queries with no
  cooperation needed from anyone.
- **D2.** FER identity from the network is imported as a `fers` row with `source="network"` and the
  nanopub-fragment IRI as its id, not as free text (§3.6, with the full argument).
- **D3.** `notApplicable` is **not** published as `FIP-No-Choice-Declaration` — those are different claims
  (§2.5).
- **D4.** The bundle carries temp cross-references plus an explicit, machine-readable rewrite plan rather than
  omitting the index (§2.3), so the bundle is complete and self-describing.
- **D5.** Reading uses our own parameterised SPARQL for the per-community path (Q1/Q2/Q3) and the network's
  registered query only for the community list (Q0), because the registered per-declaration query returns
  11.3 MB unfiltered (§3.1).

Open questions, each with a recommendation and a cost of deciding late:

- **Q1 — whose agent IRI?** The Wizard uses `https://fip.fair-wizard.com/wizard` as `dct:creator`.
  Recommendation: a stable, resolvable IRI for FIP Manager itself, e.g.
  `https://w3id.org/fipm/agent` (a w3id redirect we would have to request) rather than
  `{FIPM_BASE_URL}`, which changes with deployment and would fragment our own provenance across the network.
  Cost of deciding late: **low** while nothing is published; **high** afterwards (published nanopubs are
  immutable).
- **Q2 — publish under a GO FAIR FIP Manager ORCID, or each community's own?** Every network FIP's
  provenance graph names a **person** by ORCID (`dct:creator orcid:0000-0003-4250-4584` on PARC's, a real
  data steward). FIP Manager has no ORCID field on a user or a FIP today. Recommendation: **each community's
  own** — a declaration is a community's claim, not the tool's, and a shared "FIP Manager" ORCID would make
  every FIP look like it came from the same author, which is both misleading and a single point of
  reputational failure. That means adding an optional ORCID to `fips.community.dataSteward` (it already
  exists!) *and* to the publishing user, and the manifest listing a missing ORCID as a blocker (§2.6). Cost
  of deciding late: **low** — it changes one triple in the provenance graph and one manifest line.
- **Q3 — do we publish FER nanopubs for genuinely new resources?** Today a catalogue FER that the network
  does not know is described inline in each declaration nanopub that uses it (§2.4.1 case 2). The Wizard
  instead publishes a separate FER nanopub per resource, via a nanodash template. Recommendation: keep inline
  for now; revisit only if a CONFOA community coins FERs it wants others to reuse. Cost of deciding late:
  **low**.
- **Q4 — republishing.** Once a FIP is published, editing it in FIP Manager and re-exporting produces a new
  bundle with no `npx:supersedes`. Recommendation: v2 — store the published FIP nanopub IRI on the FIP and
  emit `npx:supersedes` on the next bundle. Not needed while nothing is published. Cost of deciding late:
  **low**, since it is additive.
- **Q5 — language tags.** The network's FIP nanopubs use **untagged** literals for labels and considerations.
  We emit `"…"@pt-BR`. A network consumer filtering `FILTER(lang(?l) = "")` would miss ours. Recommendation:
  keep the tag (it is more correct, and pt-BR content is the point of this project) but **also** emit an
  untagged `rdfs:label` on the community and the FIP for discoverability. Facilitator input welcome; this is
  the one place where "more correct" and "more findable" differ. Cost of deciding late: **low**.
- **Q6 — may DMP evidence ever be published?** Currently omitted (§2.5). It is often an internal FioDMP URL.
  Recommendation: never publish it without an explicit per-FIP opt-in. Cost of deciding late: **none**, the
  safe default is in place.
- **Q7 — which community IRI scheme for our own communities?** Network communities are nanopub-fragment IRIs
  minted by the publishing nanopub (`http://purl.org/np/RA…#PARCToxicology`), i.e. the scheme is *decided by
  signing*, not by us. Our unsigned bundle therefore mints a temp IRI that becomes
  `https://w3id.org/np/RA…/community` on signing (§2.2). The real question is **community identity across
  FIPs**: if the same community publishes twice, the Wizard reuses the *same* community IRI (PARC's
  community nanopub is from 2023, its FIP from 2026). We cannot do that until we have published once.
  Recommendation: v2 — a `communities` table keyed by a FIP Manager id, holding the published nanopub IRI
  once known, so the second bundle reuses it instead of minting a second community. Until then, one bundle =
  one community nanopub, and the manifest says so. Cost of deciding late: **medium** — a community published
  twice under two IRIs cannot be merged retroactively, only linked with `owl:sameAs`. This is the one open
  question worth answering before anyone signs anything.
- **Q8 — CONFOA scope.** `GET /api/network/fers` (§3.2) is specified and testable but is a **v2 roadmap
  item**: it is not wired into `FerPicker.vue` for the workshop, because a network FER lookup during a live
  session on conference wifi is a failure mode with no upside. Recommendation: ship the endpoint, wire the
  picker after CONFOA.

---

## 8. Implementation plan

Two briefs, independent after the API contract in §3.2/§3.3/§2.7 is fixed (it is, above). Run in parallel.
Both go through `verifier`, then `reviewer`, then `scribe`. The i18n strings both need are `translator`'s
job, not theirs: builders add **en** keys only and list them for the translator.

### 8.1 Builder brief A — backend

**Goal.** Implement, with tests, (a) the read-only nanopublication-network proxy of spec 11 §3, (b) the
unsigned nanopublication bundle export of spec 11 §2, and (c) the network prefill endpoint of §3.6.

**Read first, in this order.** `docs/specs/11-nanopub-network.md` (this spec — §0.2 has the real TriG shapes
you must match, §3.1 has the exact SPARQL you must use, verbatim, already verified against the live
service), `docs/specs/00-fip-ontology-mapping.md` (the term mapping — do not re-derive it),
`backend/fipm/rdf.py` (you are reusing `STATUS_PREDICATE`, `STATUS_AVAILABILITY_CLASS`,
`KNOWN_QUESTION_INDIVIDUALS`, `KNOWN_PRINCIPLE_IDS`, `_question_individual_local`, `_free_text_hash`,
`_fer_type_class`, `_is_http_iri`, `ORCID_RE`, `_resolve_lang_pair` — **reuse, do not reimplement**),
`backend/fipm/exporters.py` (`fip_url`, `resolve_lang`), `backend/fipm/routers/fips.py` (the four
`export.*` handlers your new ones must mirror, and `create_fip`'s authorization ladder your prefill endpoint
must reuse), `backend/fipm/config.py`, `backend/fipm/migration.py` + `db.py` (the `SCHEMA_VERSION` /
`_EXPECTED_COLUMNS` mechanism), `backend/tests/test_ac_05_7_schema_upgrade.py` and
`backend/tests/test_standalone_fips.py` (the env-override-plus-`get_settings.cache_clear()` test pattern).

**Files to create.**

- `backend/fipm/network.py` — the proxy. Exports `get_fip_communities(settings)`,
  `get_community_fip(settings, community_iri)`, `search_fers(settings, q, limit)`,
  `reset_network_cache()`, and the two injectable seams `_post_sparql(settings, repo, query)` and
  `_get_grlc(settings, artifact_code, query_name)`. Contains the SPARQL templates from §3.1 **verbatim** as
  module constants, the IRI validation of §5, the LRU+TTL cache of §3.4, and the stale-on-failure behaviour.
  No FastAPI imports here — this module is pure and unit-testable.
- `backend/fipm/nanopub_export.py` — the bundle. Exports
  `build_bundle(db, fip, settings, now) -> NanopubBundle` where `NanopubBundle` carries
  `files: list[tuple[str, str]]` (path, TriG text), `index: dict`, `manifest: str`, and
  `zip_bytes() -> bytes`. One nanopub is one `rdflib.Dataset`; serialise with `format="trig"`. **Sort
  triples deterministically** so §6.1 test 28 (byte-identical output) passes — serialise each graph via
  `sorted()` over its triples into a fresh graph, or set `rdflib`'s canonical serialisation; whichever you
  choose, prove it with the test.
- `backend/fipm/routers/network.py` — `GET /api/network/fip-communities`,
  `GET /api/network/fips/{community_iri:path}`, `GET /api/network/fers`. Registered in `fipm/main.py`.
- `backend/tests/fixtures/network/{fip-communities,parc-fips,parc-declarations,parc-resources,fer-search-orcid}.json`
  + `README.md` with the re-record curl commands from §3.1.
- `backend/tests/test_ac_11_01_network_communities.py`, `…_02_network_fip_detail.py`,
  `…_03_nanopub_export.py`, `…_04_network_prefill.py`, `…_05_network_safety.py` — tests 1–40 of §6.1.

**Files to change.**

- `backend/fipm/config.py` — `network_enabled`, `nanopub_query_url`, `network_timeout_seconds`,
  `network_cache_ttl_seconds`, `network_max_response_bytes` with the §3.4 defaults; `check_network_safety()`
  called from `main.py` alongside `check_mail_safety()`.
- `backend/fipm/models.py` — `Fip.network_origin: Mapped[dict | None]` (JSON, nullable).
- `backend/fipm/db.py` / `migration.py` — `SCHEMA_VERSION` 6 → 7, one `_EXPECTED_COLUMNS` entry
  `("fips", "network_origin", "JSON")`.
- `backend/fipm/schemas.py` — `networkOrigin` on the FIP out/import schemas (shape per §4; validate it as a
  fixed-key object, the `MigratedFromImport` pattern, not an unvalidated blob).
- `backend/fipm/rdf.py` — add `question_id_from_individual(iri) -> str | None` (the inverse of
  `_question_individual_local`, sharing `KNOWN_QUESTION_INDIVIDUALS`); emit
  `prov:wasDerivedFrom <fipNanopubIri>` on the FIP node when `fip.network_origin` is set.
- `backend/fipm/exporters.py` — `networkOrigin` in `build_export_json`.
- `backend/fipm/routers/fips.py` — the three §2.7 endpoints (each starting with `_get_readable_fip`, exactly
  like `export_fip_ttl`), and `POST /api/fips/from-network` per §3.6 (reusing `create_fip`'s ladder, the
  anonymous rate limit and the `visibility` rules — refactor the shared part out rather than copying it).
- `backend/fipm/routers/fers.py` — `"network"` in the anonymous-visible source tuple (**two** places).
- `backend/pyproject.toml` — move `httpx>=0.27` from `[dependency-groups] dev` to `[project] dependencies`.
- `backend/tests/conftest.py` — autouse fixture that raises on any un-patched call into `fipm.network`.
- `.env.example` — the five new `FIPM_NETWORK*` / `FIPM_NANOPUB_QUERY_URL` variables, with the verified
  default and a one-line comment each.
- `backend/fipm/routers/health.py` — report `networkEnabled` so the frontend can hide the nav entry.

**Acceptance criteria.**

1. `cd backend && uv run pytest -q` passes; the count rises by the 40 tests of §6.1 (currently 483 → 523).
2. `uv run ruff check .` and `uv run ruff format --check .` clean.
3. **No test performs a live network request.** Proven by the autouse conftest guard: temporarily delete one
   fixture registration and the test must fail with that guard's message, not with a timeout.
4. The four SPARQL templates in `network.py` are byte-identical to §3.1 (a test asserts the constants against
   the strings, so a "helpful" edit that reintroduces `#assertion` or drops `distinct` fails loudly).
5. `GET /api/fips/{id}/export/nanopubs.zip` output: every `.trig` satisfies `extract_np_metadata`'s SPARQL
   (§6.1 test 16); no signature or `nt:` triple anywhere (test 17); two runs with a frozen clock are
   byte-identical (test 28).
6. Authorization on all three export endpoints is *identical* to `export.ttl`, asserted by comparing status
   codes across both endpoints for the same six caller/visibility combinations (test 27).
7. `FIPM_NETWORK_ENABLED=false` → `503 network_disabled` on all three network endpoints, and
   `GET /api/health` reports it.
8. `check_network_safety()` refuses to start on an `http://`, pathful, or userinfo-bearing
   `FIPM_NANOPUB_QUERY_URL`.
9. Schema 6 → 7 upgrades an existing `fipm.db` in place with existing rows' `network_origin` NULL.
10. Nothing in `fipm/` imports `nanopub`, generates or reads a key, or makes an outbound POST. Grep for
    `nanopub`, `private_key`, `sign` in the diff and confirm.

**Report back:** the test count before/after; the four SPARQL constants' names; the list of new `network.*`
i18n keys you did **not** add (for the translator); anything in §2.4/§3.3 the code could not do as specified,
with what you did instead.

### 8.2 Builder brief B — frontend

**Goal.** Implement, with tests, the two Network FIPs pages, the "Use as starting point" flow, and the
"Prepare nanopublications" entry points of spec 11 §3.5 and §3.6.

**Read first.** `docs/specs/11-nanopub-network.md` §3.2 (the exact endpoint contracts), §3.3 (the exact
response shape you render), §3.5 (what each page contains), §3.6 (the prefill flow and the banner text), §2.6
(what `index.json` contains, which is what the Prepare dialog renders). Then, in the repo:
`frontend/src/api/fips.ts` and `client.ts` (the API-module conventions), `frontend/src/views/FipRead.vue` and
`frontend/src/components/ExportButtons.vue` (where your two entry points go),
`frontend/src/components/QuestionCard.vue` and `StatusBadge.vue` (the read-only layout you reuse for a network
FIP — reuse them, do not fork them), `frontend/src/views/FipNew.vue` and `frontend/src/lib/editTokens.ts`
(how a created FIP's edit token is stored and how the editor is entered), `frontend/src/router/index.ts`,
`frontend/src/views/Home.test.ts` (the component-test pattern with a mocked api module).

**Files to create.**

- `frontend/src/api/network.ts` — `listCommunities({q, limit, offset})`, `getCommunityFip(communityIri)`,
  `searchFers({q, limit})`, `createFipFromNetwork(body)`, `getNanopubIndex(fipId)`,
  `getNanopubPreview(fipId, n)`, and the `nanopubZipUrl(fipId)` helper. `communityIri` is
  `encodeURIComponent`-encoded exactly once.
- `frontend/src/types/network.ts` — the response types transcribed from §3.2/§3.3/§2.6.
- `frontend/src/views/NetworkFipList.vue` + `NetworkFipList.test.ts`.
- `frontend/src/views/NetworkFipDetail.vue` + `NetworkFipDetail.test.ts`.
- `frontend/src/components/NanopubExportDialog.vue` + `NanopubExportDialog.test.ts` — the §3.5 dialog.

**Files to change.**

- `frontend/src/router/index.ts` — `/network` → `NetworkFipList`, `/network/:communityIri` →
  `NetworkFipDetail`, both `meta: { requiresAuth: false }`, `props: true`.
- `frontend/src/App.vue` (or wherever the nav lives) — a **Network FIPs** entry, hidden when
  `GET /api/health`'s `networkEnabled` is false.
- `frontend/src/views/FipRead.vue` — the **Prepare nanopublications** button opening the dialog.
- `frontend/src/components/ExportButtons.vue` (+ its test) — a **Nanopublications (.zip)** entry.
- `frontend/src/views/FipEditor.vue` — the one-time "prefilled from the network" banner when the loaded FIP
  has `networkOrigin`.
- `data/i18n/en.json` — **en only**, all new keys under `network.*` and `nanopubExport.*`. List them in your
  report for the translator; do **not** touch `pt-PT.json` / `pt-BR.json` / `es.json`.

**Acceptance criteria.**

1. `cd frontend && npm run test` passes; `npm run build` and `npx vue-tsc --noEmit` clean.
2. `NetworkFipDetail.vue` renders **all 21** questions from a mocked payload, in the payload's order,
   including the ones with an empty `declarations` (rendered as an explicit "no declaration" gap, not
   omitted), and reuses `QuestionCard.vue`/`StatusBadge.vue` rather than new markup.
3. `unmapped` renders inside a collapsed `<details>` labelled from an i18n key, never mixed into the 21.
4. Each of the three network error codes renders a distinct state: `network_disabled` (no retry),
   `network_unavailable` (retry re-calls the api exactly once per click), `network_fip_not_found`.
5. **Use as starting point** calls `createFipFromNetwork` exactly once per click (guard against
   double-submit), stores any returned `editToken` via `setToken()` before navigating, and navigates to
   `FipEditor`.
6. The Prepare dialog's first visible line states that the bundle is unsigned and unpublished; it renders
   `counts`, `skipped`, `notRepresented` and `publishPrerequisites.missing` from `index.json` and shows the
   `preview.trig` text; the download is a plain link to `nanopubZipUrl(fipId)` (no `fetch`-then-blob, so the
   browser handles it and the `Content-Disposition` filename is honoured).
7. No hard-coded English outside `data/i18n/en.json`. No new dependency in `package.json`.
8. The frontend makes **no** request to any host other than its own `/api` — grep the diff for
   `knowledgepixels`, `petapico`, `w3id.org` and confirm the only occurrences are display-only link `href`s
   to nanodash (`https://nanodash.knowledgepixels.com/explore?id=…`), which are `target="_blank"
   rel="noopener noreferrer"`.

**Report back:** the test count before/after; the full list of new i18n keys with their en strings (for the
translator); any place §3.3's shape was awkward to render, with what you'd change in the contract.
