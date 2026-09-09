"""Audit finding 1: `fipm.rdf.orphaned_answer_comment_lines` interpolates
`fip.orphaned_answers` fields (all user-controlled JSON -- round-tripped
through `POST /fips/import`, or copied verbatim by a migration) into a
Turtle `#` comment line with no serialiser escaping in between. A Turtle
`#` comment ends at the first line break, so an unescaped `\\n`/`\\r` in
one of those fields used to let the rest of the value be parsed as real
Turtle instead of staying inert comment text. `_sanitize_comment_field`
collapses any run of `\\r`/`\\n` to a single space (and drops other control
characters) before interpolation, so a value can never introduce a line
break into the header block."""

from __future__ import annotations

from types import SimpleNamespace

from rdflib import Graph

from fipm.rdf import orphaned_answer_comment_lines, to_turtle


def test_newline_in_question_id_is_collapsed_not_a_line_break():
    fip = SimpleNamespace(
        orphaned_answers=[
            {
                "questionId": "A2\n<http://evil.example/> a <http://evil.example/Injected> .",
                "declarations": [],
            }
        ]
    )
    lines = orphaned_answer_comment_lines(fip)
    assert len(lines) == 1
    assert "\n" not in lines[0]
    assert "\r" not in lines[0]
    assert lines[0].startswith("# orphaned answer A2")


def test_newline_in_declaration_fields_is_collapsed():
    fip = SimpleNamespace(
        orphaned_answers=[
            {
                "questionId": "A2",
                "declarations": [
                    {
                        "ferFreeText": (
                            "In-house\n<http://evil.example/> a <http://evil.example/Injected> ."
                        ),
                        "status": "current\n# nested comment",
                    }
                ],
            }
        ]
    )
    lines = orphaned_answer_comment_lines(fip)
    assert len(lines) == 1
    assert "\n" not in lines[0]
    assert "\r" not in lines[0]


def test_crlf_is_also_collapsed():
    fip = SimpleNamespace(orphaned_answers=[{"questionId": "A2\r\ninjected", "declarations": []}])
    lines = orphaned_answer_comment_lines(fip)
    assert len(lines) == 1
    assert "\r" not in lines[0]
    assert "\n" not in lines[0]


def test_injected_triple_stays_inert_in_the_serialised_turtle():
    """Regression for the actual attack: before the fix, this questionId
    would produce a `# orphaned answer ...` line followed by two real,
    uncommented Turtle lines (`@prefix evil: ...` and `evil:s evil:p
    evil:o .`), which `Graph.parse` would happily accept as an injected
    triple. After the fix, everything the caller supplied stays on the one
    `#`-prefixed line, so no `evil:` triple is ever parsed."""
    fip = SimpleNamespace(
        orphaned_answers=[
            {
                "questionId": (
                    "A2\n@prefix evil: <http://evil.example/> .\nevil:s evil:p evil:o ."
                ),
                "declarations": [],
            }
        ]
    )
    lines = orphaned_answer_comment_lines(fip)
    assert len(lines) == 1

    ttl = to_turtle(Graph(), extra_comment_lines=lines)

    injected_lines = [line for line in ttl.splitlines() if "evil:" in line]
    assert len(injected_lines) == 1
    assert injected_lines[0].startswith("#")

    parsed = Graph()
    parsed.parse(data=ttl, format="turtle")
    assert len(parsed) == 0
