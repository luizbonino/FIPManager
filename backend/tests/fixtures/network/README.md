# Network fixtures

Byte-for-byte captures of real responses from the Nanopublication Query
service (`https://query.knowledgepixels.com`), recorded **2026-09-10** (spec
`docs/specs/11-nanopub-network.md` §0/§3.1/§6). `fipm.network`'s tests never
make a live network call; they monkeypatch `fipm.network._post_sparql` /
`fipm.network._get_grlc` to return these files instead (`conftest.py`'s
autouse guard fails any test that forgets to patch one of those seams).

Re-record any file by re-running its command below and overwriting the file.
The queries are the exact SPARQL/grlc templates in spec §3.1 (also asserted
byte-identical to the module constants in `fipm/network.py` by
`test_ac_11_05_network_safety.py`).

## fip-communities.json

```sh
curl -s "https://query.knowledgepixels.com/api/RAoQRAype8NkynHDgj5ofRSjFmkeXYIeybunn1EnGpyyQ/fip-communities" \
  -H "Accept: application/sparql-results+json" \
  -o fip-communities.json
```

Q0, the registered grlc query. As of this recording: 84 rows / 79 distinct
community IRIs, several communities (not only `ACTRIS-ARES`, spec §0.1's
example) appearing twice under two labels from two nanopub versions — the
dedupe-by-longest-label-max-fip_count logic (spec §3.2) is exercised against
this real duplication, not a synthetic one.

## parc-fips.json

```sh
curl -s "https://query.knowledgepixels.com/repo/type/92efd7a0ea4be4e01ec0817ccec87f975203b30addcc3166a204498ffed73b66" \
  -H "Accept: application/sparql-results+json" \
  --data-urlencode 'query=<Q1 from spec §3.1, ?COMMUNITY replaced with
    <http://purl.org/np/RAoZsfUhNx4sYz-IXfsp1xPBH1-YgTGtHpp3BbMQtWHJg#PARCToxicology>>' \
  -o parc-fips.json
```

Q1 for the PARC Toxicology community. Newest FIP nanopub
`https://w3id.org/np/RAKa7vUwc8qVbktDqDSpuq7lRrrKcjPKvkB4Tn7WHvr7E` (created
2026-09-07), index `https://w3id.org/np/RATReWJWVaVcOU7UrhKTkMPuNW4P_hmuD07FyOm4UtN3U`.

## parc-declarations.json

```sh
curl -s "https://query.knowledgepixels.com/repo/full" \
  -H "Accept: application/sparql-results+json" \
  --data-urlencode 'query=<Q2 from spec §3.1, ?INDEX replaced with
    <https://w3id.org/np/RATReWJWVaVcOU7UrhKTkMPuNW4P_hmuD07FyOm4UtN3U>>' \
  -o parc-declarations.json
```

Q2 over the newest FIP's declaration index: 89 declarations (matches spec
§3.1's measurement exactly), across the 21 mapped `fip:FIP-Question-*`
individuals plus several `fip:FIP-S-Question-*` (FSR) rows that must land in
`unmapped`.

## parc-resources.json

```sh
curl -s "https://query.knowledgepixels.com/repo/full" \
  -H "Accept: application/sparql-results+json" \
  --data-urlencode 'query=<Q3 from spec §3.1, ?RESOURCES a `values` block of
    the 45 distinct resource IRIs referenced by parc-declarations.json>' \
  -o parc-resources.json
```

Q3 over every distinct `?resource` IRI appearing in `parc-declarations.json`
(45 IRIs, 162 result rows) -- multi-row-per-resource (one per `fip:` type ×
label variant × nanopub version), the exact post-processing case of §3.1.

## fer-search-orcid.json

```sh
curl -s "https://query.knowledgepixels.com/repo/text" \
  -H "Accept: application/sparql-results+json" \
  --data-urlencode 'query=<Q4 from spec §3.1, ?QUERY="orcid", limit 5>' \
  -o fer-search-orcid.json
```

Q4 full-text search for `"orcid"`, top 5 hits by Lucene score.
