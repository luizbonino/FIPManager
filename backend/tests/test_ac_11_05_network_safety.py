"""spec 11-nanopub-network.md §5/§6, builder brief A tests 37-40 (+ AC4: the
four SPARQL templates are byte-identical to spec §3.1).

`fipm.network` is pure (no FastAPI, no DB) -- every test here calls it
directly, monkeypatching either the two seams (`_post_sparql`/`_get_grlc`)
or, for the transport-level tests (follow_redirects, size cap), `httpx.Client`
itself (the autouse `_guard_network_calls` fixture in conftest.py only
patches the two seams, so it doesn't interfere with a test that replaces
`fipm.network.httpx.Client` directly)."""

from __future__ import annotations

import json

import pytest

from fipm import network
from fipm.config import Settings

# ---------------------------------------------------------------------------
# AC4: SPARQL templates byte-identical to spec 11 §3.1, quoted here verbatim.
# ---------------------------------------------------------------------------

_Q1_SPEC_TEXT = """prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#>
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
} order by desc(?created)"""

_Q2_SPEC_TEXT = """prefix fip:  <https://w3id.org/fair/fip/terms/>
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
} order by ?question"""

_Q3_SPEC_TEXT = """prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#>
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
}"""

_Q4_SPEC_TEXT = """prefix rdfs:   <http://www.w3.org/2000/01/rdf-schema#>
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
} group by ?np ?label order by desc(?s) limit ?LIMIT"""


def test_sparql_templates_are_byte_identical_to_spec():
    assert network.Q1_SPARQL == _Q1_SPEC_TEXT
    assert network.Q2_SPARQL == _Q2_SPEC_TEXT
    assert network.Q3_SPARQL == _Q3_SPEC_TEXT
    assert network.Q4_SPARQL == _Q4_SPEC_TEXT
    # The two invariants §3.1 calls out by name: never hardcode #assertion,
    # and select distinct is mandatory.
    assert "#assertion" not in network.Q2_SPARQL
    assert network.Q1_SPARQL.startswith("prefix") and "select distinct" in network.Q1_SPARQL
    assert "select distinct" in network.Q2_SPARQL


# ---------------------------------------------------------------------------
# Test 37: check_network_safety()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://query.knowledgepixels.com",  # not https
        "https://query.knowledgepixels.com/repo",  # has a path
        "https://user:pass@query.knowledgepixels.com",  # userinfo
        "",  # empty
        "not-a-url",
    ],
)
def test_check_network_safety_rejects_unsafe_urls(url):
    settings = Settings(nanopub_query_url=url)
    with pytest.raises(RuntimeError):
        settings.check_network_safety()


def test_check_network_safety_accepts_the_default():
    Settings(nanopub_query_url="https://query.knowledgepixels.com").check_network_safety()
    Settings(nanopub_query_url="https://query.petapico.org").check_network_safety()


# ---------------------------------------------------------------------------
# Review finding 14: fipm.main's startup lifespan only runs
# check_network_safety() when the network integration is enabled -- an
# unsafe FIPM_NANOPUB_QUERY_URL must not block startup when
# FIPM_NETWORK_ENABLED=false, since no code path ever builds a URL from it
# in that case.
# ---------------------------------------------------------------------------


async def _run_lifespan_once() -> None:
    from fipm.main import app as fastapi_app
    from fipm.main import lifespan

    async with lifespan(fastapi_app):
        pass


def test_lifespan_skips_network_safety_check_when_network_disabled(monkeypatch):
    import asyncio

    from fipm.config import get_settings

    monkeypatch.setenv(
        "FIPM_NANOPUB_QUERY_URL", "http://query.knowledgepixels.com"
    )  # unsafe: not https

    monkeypatch.setenv("FIPM_NETWORK_ENABLED", "true")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError):
            asyncio.run(_run_lifespan_once())
    finally:
        get_settings.cache_clear()

    monkeypatch.setenv("FIPM_NETWORK_ENABLED", "false")
    get_settings.cache_clear()
    try:
        asyncio.run(_run_lifespan_once())  # must not raise
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Tests 38/39: transport-level behaviour, exercised by replacing
# fipm.network.httpx.Client (below the two seams tested elsewhere).
# ---------------------------------------------------------------------------


class _FakeStreamCtx:
    def __init__(self, status_code: int, chunks: list[bytes]) -> None:
        self.status_code = status_code
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def iter_bytes(self):
        yield from self._chunks


class _FakeClient:
    last_kwargs: dict | None = None
    response: _FakeStreamCtx | None = None

    def __init__(self, **kwargs) -> None:
        type(self).last_kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def stream(self, method, url, data=None, headers=None):
        return type(self).response


@pytest.fixture()
def fake_httpx_client(monkeypatch):
    monkeypatch.setattr(network.httpx, "Client", _FakeClient)
    return _FakeClient


def test_client_constructed_with_follow_redirects_false(fake_httpx_client, settings):
    fake_httpx_client.response = _FakeStreamCtx(200, [b'{"results": {"bindings": []}}'])
    network._perform_request(settings, "GET", f"{settings.nanopub_query_url}/api/x/y")
    assert fake_httpx_client.last_kwargs["follow_redirects"] is False


def test_redirect_response_is_network_unavailable(fake_httpx_client, settings):
    fake_httpx_client.response = _FakeStreamCtx(302, [])
    with pytest.raises(network.NetworkError) as exc_info:
        network._perform_request(settings, "GET", f"{settings.nanopub_query_url}/api/x/y")
    assert exc_info.value.code == "network_unavailable"
    assert exc_info.value.status_code == 502


def test_oversized_response_is_network_response_too_large(fake_httpx_client, settings):
    big_settings = Settings(
        nanopub_query_url=settings.nanopub_query_url, network_max_response_bytes=10
    )
    fake_httpx_client.response = _FakeStreamCtx(200, [b"x" * 20])
    with pytest.raises(network.NetworkError) as exc_info:
        network._perform_request(big_settings, "GET", f"{big_settings.nanopub_query_url}/api/x/y")
    assert exc_info.value.code == "network_response_too_large"
    assert exc_info.value.status_code == 502


# ---------------------------------------------------------------------------
# Test 40: search query sanitisation.
# ---------------------------------------------------------------------------


def test_sanitise_fer_query_strips_quotes_and_backslashes_and_caps_length():
    dirty = 'a"b\\c' + "x" * 200
    safe = network._sanitise_fer_query(dirty)
    assert '"' not in safe
    assert "\\" not in safe
    assert len(safe) <= 100


def test_fer_search_query_reaches_q4_already_sanitised(settings, monkeypatch):
    captured: dict[str, str] = {}

    def fake_post_sparql(settings_, repo, query):
        captured["query"] = query
        return {"results": {"bindings": []}}

    monkeypatch.setattr(network, "_post_sparql", fake_post_sparql)

    dirty = 'a"b\\c' + "x" * 200
    network.search_fers(settings, dirty, 20)

    expected_literal = json.dumps(network._sanitise_fer_query(dirty))
    assert f"search:query {expected_literal} ;" in captured["query"]


# ---------------------------------------------------------------------------
# §5: community/resource IRI validation.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "iri",
    [
        "http://purl.org/np/RAoZ>evil",
        'http://purl.org/np/RAoZ"evil',
        "http://purl.org/np/RAoZ evil",
        "http://purl.org/np/RAoZ{evil}",
        "not-an-iri",
        "ftp://example.org/x",
    ],
)
def test_invalid_community_iri_rejected(iri):
    with pytest.raises(network.NetworkError) as exc_info:
        network.validate_community_iri(iri)
    assert exc_info.value.code == "invalid_community_iri"
    assert exc_info.value.status_code == 400


def test_valid_community_iri_accepted():
    network.validate_community_iri(
        "http://purl.org/np/RAoZsfUhNx4sYz-IXfsp1xPBH1-YgTGtHpp3BbMQtWHJg#PARCToxicology"
    )


# ---------------------------------------------------------------------------
# Review finding 4: Q1's own ?index IRI is upstream data, substituted
# verbatim into Q2 -- it must pass the same _is_safe_sparql_iri check as
# ?COMMUNITY/?RESOURCES before that substitution happens.
# ---------------------------------------------------------------------------


def test_unsafe_q1_index_iri_is_rejected_before_q2_is_ever_sent(settings, monkeypatch):
    bad_index = 'https://w3id.org/np/evil"injected'
    q1_response = {
        "results": {
            "bindings": [
                {
                    "fip_np": {"type": "uri", "value": "https://w3id.org/np/fip1"},
                    "label": {"type": "literal", "value": "Bad FIP"},
                    "index": {"type": "uri", "value": bad_index},
                    "created": {"type": "literal", "value": "2026-01-01T00:00:00.000Z"},
                }
            ]
        }
    }

    def fake_post_sparql(settings_, repo, query):
        if repo == f"type/{network.FIP_TYPE_REPO}":
            return q1_response
        raise AssertionError(
            f"Q2 must never be sent when Q1's ?index fails the safety check, got repo={repo!r}"
        )

    monkeypatch.setattr(network, "_post_sparql", fake_post_sparql)

    with pytest.raises(network.NetworkError) as exc_info:
        network.get_community_fip(
            settings,
            "http://purl.org/np/RAoZsfUhNx4sYz-IXfsp1xPBH1-YgTGtHpp3BbMQtWHJg#PARCToxicology",
        )
    assert exc_info.value.code == "network_unavailable"
    assert exc_info.value.status_code == 502


# ---------------------------------------------------------------------------
# Review finding 9: _cached_call never hands out the stored object itself.
# ---------------------------------------------------------------------------


def test_cached_call_returns_deepcopy_mutation_not_visible_on_next_call():
    from fipm.network import _cached_call, reset_network_cache

    reset_network_cache()
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return {"a": [1, 2, 3], "nested": {"b": "x"}}

    value1, _cached_at1, stale1 = _cached_call("ac1105-cache-key", 900, fetch)
    assert stale1 is False
    value1["a"].append(999)
    value1["nested"]["b"] = "mutated"

    value2, _cached_at2, stale2 = _cached_call("ac1105-cache-key", 900, fetch)
    assert value2 == {"a": [1, 2, 3], "nested": {"b": "x"}}
    assert calls["n"] == 1  # served from cache both times -- fetch ran once


# ---------------------------------------------------------------------------
# Review finding 11: the FER search query sanitiser strips control
# characters too, and the query text preserves non-ASCII literally
# (ensure_ascii=False) rather than \uXXXX-escaping it.
# ---------------------------------------------------------------------------


def test_sanitise_fer_query_strips_control_characters():
    dirty = "a\x01b\x1fc\x7f"
    safe = network._sanitise_fer_query(dirty)
    assert safe == "abc"


def test_sanitise_fer_query_preserves_non_ascii_text():
    assert network._sanitise_fer_query("ômicos") == "ômicos"


def test_search_fers_query_carries_non_ascii_literally_not_escaped(settings, monkeypatch):
    captured: dict[str, str] = {}

    def fake_post_sparql(settings_, repo, query):
        captured["query"] = query
        return {"results": {"bindings": []}}

    monkeypatch.setattr(network, "_post_sparql", fake_post_sparql)

    network.search_fers(settings, "ômicos", 20)

    assert '"ômicos"' in captured["query"]
    assert "\\u00f4" not in captured["query"]
