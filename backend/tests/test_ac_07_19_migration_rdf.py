"""AC19 (spec 07-mail-and-migration.md §8): `export.ttl` contains
`dcterms:conformsTo <.../gofair-fip-mini/1.1.0>`, `fipmx:migrated-from
<.../gofair-fip-mini/1.0.0>`, one `# orphaned answer` comment line and no
`prov:wasRevisionOf`; the JSON-LD carries no orphaned-answer node."""

from __future__ import annotations

from _migration_helpers import build_scenario


def test_export_ttl_after_migration(client):
    scenario = build_scenario(client, "mig19")
    fip_id = scenario["fip_id"]
    km_id = scenario["km_id"]

    migrate = client.post(f"/api/fips/{fip_id}/migrate", json={"to": "1.1.0"})
    assert migrate.status_code == 200, migrate.text

    ttl = client.get(f"/api/fips/{fip_id}/export.ttl")
    assert ttl.status_code == 200
    text = ttl.text

    assert f"knowledge-models/{km_id}/1.1.0" in text
    assert "migrated-from" in text
    assert f"knowledge-models/{km_id}/1.0.0" in text
    orphan_comment_lines = [
        line for line in text.splitlines() if line.startswith("# orphaned answer")
    ]
    assert len(orphan_comment_lines) == 1
    assert "A2" in orphan_comment_lines[0]
    assert "prov:wasRevisionOf" not in text
    assert "wasRevisionOf" not in text


def test_export_jsonld_has_no_orphaned_answer_node(client):
    scenario = build_scenario(client, "mig19b")
    fip_id = scenario["fip_id"]

    migrate = client.post(f"/api/fips/{fip_id}/migrate", json={"to": "1.1.0"})
    assert migrate.status_code == 200, migrate.text

    jsonld = client.get(f"/api/fips/{fip_id}/export.jsonld")
    assert jsonld.status_code == 200
    doc = jsonld.json()
    # The orphaned answer (A2) must not appear as a node anywhere in the
    # graph: no "questionId": "A2" fipmx:Answer-shaped node, no A2 IRI.
    serialized = str(doc)
    assert "orphaned" not in serialized.lower()
    assert "#answer-A2" not in serialized
