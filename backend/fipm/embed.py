"""GET /fips/{id}/embed -- server-rendered HTML for a third-party <iframe>
(spec 06-dmp-linkage.md §3). Pure, unit-testable rendering: no DB access,
no JS, no external requests. Every interpolated value passes through
`html.escape(..., quote=True)` -- this page is framed by a third party, so
escaping is the security boundary (AC 7)."""

from __future__ import annotations

import html
from typing import Any

from fipm.config import Settings
from fipm.models import Fip

# spec 02-core-flows.md §4.3 / frontend `assets/styles.css`
# `--color-status-*`: the SPA's CSS variables aren't available on this
# standalone page, so the five status colours are inlined as hex.
STATUS_COLORS: dict[str, str] = {
    "current": "#0a7d33",
    "planned": "#b45f06",
    "planned-development": "#6f42c1",
    "planned-replacement": "#b3261e",
    "none": "#6b7280",
}

# The three languages the embed ships fixed strings for (spec 06 §3);
# narrower than the app's four `Language` values (no `es`).
_SUPPORTED_LANGS: tuple[str, ...] = ("en", "pt-PT", "pt-BR")

EMBED_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "answered": "questions answered",
        "questionnaire": "Questionnaire",
        "language": "Language",
        "description": "Description",
        "domain": "Research domain",
        "relatedDmps": "Related data management plans",
        "noDmps": "No plans linked.",
        "version": "Version",
        "viewFull": "View the full FIP",
        "principle": "Principle",
        "question": "Question",
        "resources": "FAIR-enabling resource(s)",
        "status": "Status",
        "notFoundTitle": "Not found",
        "notFoundBody": "This FIP is private, or does not exist.",
        "attributionQuestionnaire": (
            "Questionnaire content: FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, "
            "Barbara Magagna, Jacintha Schultes / GO FAIR Foundation, CC BY-SA 4.0."
        ),
        "attributionOntology": "FER types and terms: FIP Ontology, CC0 1.0.",
        "attributionAnswers": "This FIP's answers: {license}.",
    },
    "pt-PT": {
        "answered": "perguntas respondidas",
        "questionnaire": "Questionário",
        "language": "Idioma",
        "description": "Descrição",
        "domain": "Domínio de investigação",
        "relatedDmps": "Planos de gestão de dados relacionados",
        "noDmps": "Nenhum plano associado.",
        "version": "Versão",
        "viewFull": "Ver o FIP completo",
        "principle": "Princípio",
        "question": "Pergunta",
        "resources": "Recurso(s) FAIR-enabling",
        "status": "Estado",
        "notFoundTitle": "Não encontrado",
        "notFoundBody": "Este FIP é privado, ou não existe.",
        "attributionQuestionnaire": (
            "Conteúdo do questionário: FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, "
            "Barbara Magagna, Jacintha Schultes / GO FAIR Foundation, CC BY-SA 4.0."
        ),
        "attributionOntology": (
            "Tipos e termos de FER (FAIR Enabling Resource): FIP Ontology, CC0 1.0."
        ),
        "attributionAnswers": "Respostas deste FIP: {license}.",
    },
    "pt-BR": {
        "answered": "perguntas respondidas",
        "questionnaire": "Questionário",
        "language": "Idioma",
        "description": "Descrição",
        "domain": "Domínio de pesquisa",
        "relatedDmps": "Planos de gestão de dados relacionados",
        "noDmps": "Nenhum plano vinculado.",
        "version": "Versão",
        "viewFull": "Ver o FIP completo",
        "principle": "Princípio",
        "question": "Pergunta",
        "resources": "Recurso(s) FAIR-enabling",
        "status": "Status",
        "notFoundTitle": "Não encontrado",
        "notFoundBody": "Este FIP é privado, ou não existe.",
        "attributionQuestionnaire": (
            "Conteúdo do questionário: FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, "
            "Barbara Magagna, Jacintha Schultes / GO FAIR Foundation, CC BY-SA 4.0."
        ),
        "attributionOntology": (
            "Tipos e termos de FER (FAIR Enabling Resource): FIP Ontology, CC0 1.0."
        ),
        "attributionAnswers": "Respostas deste FIP: {license}.",
    },
}


def resolve_embed_lang(lang_param: str | None, fip_language: str) -> str:
    """`?lang=` when it is one of the three supported languages, else the
    FIP's own language, else `en` (spec 06 §3)."""
    if lang_param in _SUPPORTED_LANGS:
        return lang_param
    if fip_language in _SUPPORTED_LANGS:
        return fip_language
    return "en"


def _e(value: Any) -> str:
    """html.escape a value for a text/attribute context; None -> ""."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def frame_ancestors(settings: Settings) -> tuple[list[str], bool]:
    """The CSP `frame-ancestors` token list for `FIPM_EMBED_ALLOWED_ORIGINS`,
    plus whether the result is `'self'`-only (in which case `X-Frame-Options:
    SAMEORIGIN` is also sent -- the header can't express an allow-list)."""
    origins = settings.embed_allowed_origins_list
    if origins == ["*"]:
        return ["*"], False
    if not origins:
        return ["'self'"], True
    return ["'self'", *origins], False


def embed_headers(settings: Settings, visibility: str | None) -> dict[str, str]:
    ancestors, self_only = frame_ancestors(settings)
    headers = {
        "Content-Type": "text/html; charset=utf-8",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": (
            "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
            f"form-action 'none'; frame-ancestors {' '.join(ancestors)}"
        ),
        "Cache-Control": (
            "public, max-age=300" if visibility in ("public", "link") else "private, no-store"
        ),
    }
    if self_only:
        headers["X-Frame-Options"] = "SAMEORIGIN"
    return headers


_STYLE = """
:root{color-scheme:light}
body{margin:0;padding:1rem 1.25rem 2rem;max-width:46rem;color:#1a1a1a;background:#fff;
  line-height:1.4;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
h1{font-size:1.3rem;margin:0 0 .25rem}
h2{font-size:1rem;margin:1.5rem 0 .5rem}
.meta{color:#555;font-size:.85rem;margin:0 0 .75rem}
.count{font-weight:600;margin:0 0 .75rem}
table{width:100%;border-collapse:collapse;font-size:.82rem}
th,td{text-align:left;padding:.3rem .4rem;border-bottom:1px solid #ddd;vertical-align:top}
th{font-size:.75rem;text-transform:uppercase;letter-spacing:.02em;color:#555}
.qid{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;white-space:nowrap}
.status{display:inline-block;color:#fff;border-radius:.75rem;padding:.05rem .55rem;
  font-size:.72rem;margin:.1rem .25rem .1rem 0;white-space:nowrap}
.dmp-list{padding-left:1.1rem;margin:.25rem 0}
.dmp-list li{margin:.15rem 0}
.v{color:#555;font-size:.85rem}
footer{margin-top:1.75rem;padding-top:.6rem;border-top:1px solid #ddd;font-size:.72rem;color:#666}
footer p{margin:.2rem 0}
a{color:#0a5dab}
@media (max-width:420px){.principle{display:none}}
""".strip()


def render_not_found(settings: Settings, lang: str = "en") -> str:
    resolved = lang if lang in _SUPPORTED_LANGS else "en"
    strings = EMBED_STRINGS[resolved]
    return (
        f'<!doctype html><html lang="{_e(resolved)}"><head><meta charset="utf-8">'
        f"<title>{_e(strings['notFoundTitle'])}</title></head>"
        f"<body><p>{_e(strings['notFoundBody'])}</p></body></html>"
    )


def render_embed(
    doc: dict[str, Any],
    fip: Fip,
    settings: Settings,
    lang: str | None,
    km_license: str | None = None,
) -> str:
    """`doc` is `exporters.build_export_json`'s output for `fip` -- already
    resolved (question texts, FER labels, notes, questionnaire ref) with
    the pt-PT <-> pt-BR -> en fallback, and padded to every questionnaire
    question. The embed adds no resolution logic of its own. `km_license`
    is the questionnaire's own `license` (not `doc`'s, which only carries
    the FIP's own license) -- it decides whether the CC BY-SA questionnaire
    credit is shown, mirroring `AttributionFooter.vue`."""
    resolved_lang = resolve_embed_lang(lang, fip.language)
    strings = EMBED_STRINGS[resolved_lang]

    community = doc["fip"].get("community") or {}
    name = community.get("name") or ""
    description = community.get("description")
    domain = community.get("domain")

    answers = doc["answers"]
    total = len(answers)
    answered = sum(1 for a in answers if a["declarations"])

    q_ref = doc["questionnaireRef"]
    km_title = q_ref.get("title") or q_ref["id"]
    meta_line = (
        f"{_e(km_title)} (id {_e(q_ref['id'])} v{_e(q_ref['version'])}, {_e(resolved_lang)})"
    )

    row_html: list[str] = []
    for a in answers:
        declarations = a["declarations"]
        if declarations:
            resource_bits = []
            status_bits = []
            for d in declarations:
                fer = d.get("fer")
                label = fer.get("label") if fer else d.get("ferFreeText")
                resource_bits.append(_e(label) if label else "—")
                status = d.get("status") or ""
                color = STATUS_COLORS.get(status, "#6b7280")
                status_bits.append(
                    f'<span class="status" style="background:{color}">{_e(status)}</span>'
                )
            resources_html = ", ".join(resource_bits)
            status_html = "".join(status_bits)
        else:
            resources_html = "—"
            status_html = ""
        row_html.append(
            "<tr>"
            f'<td class="qid">{_e(a["questionId"])}</td>'
            f'<td class="principle">{_e(a.get("principle") or "")}</td>'
            f"<td>{resources_html}</td>"
            f"<td>{status_html}</td>"
            "</tr>"
        )

    dmp_entries = fip.related_dmps or []
    if dmp_entries:
        dmp_items = []
        for dmp in dmp_entries:
            label = dmp.get("dmpId") or dmp.get("url") or ""
            version = dmp.get("version")
            version_html = f' <span class="v">v{_e(version)}</span>' if version else ""
            dmp_items.append(
                f'<li><a href="{_e(dmp.get("url"))}" target="_blank" rel="noopener">'
                f"{_e(label)}</a>{version_html}</li>"
            )
        dmp_html = f'<ul class="dmp-list">{"".join(dmp_items)}</ul>'
    else:
        dmp_html = f"<p>{_e(strings['noDmps'])}</p>"

    desc_html = f"<p>{_e(description)}</p>" if description else ""
    domain_html = f"<p><strong>{_e(strings['domain'])}:</strong> {_e(domain)}</p>" if domain else ""

    full_url = f"{settings.base_url}/fips/{fip.id}"

    footer_lines = []
    if (km_license or "").startswith("CC-BY-SA"):
        footer_lines.append(f"<p>{_e(strings['attributionQuestionnaire'])}</p>")
        footer_lines.append(f"<p>{_e(strings['attributionOntology'])}</p>")
    footer_lines.append(f"<p>{strings['attributionAnswers'].format(license=_e(fip.license))}</p>")

    return (
        "<!doctype html>"
        f'<html lang="{_e(resolved_lang)}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(name)}</title>"
        f"<style>{_STYLE}</style>"
        "</head><body>"
        f"<h1>{_e(name)}</h1>"
        f"{desc_html}{domain_html}"
        f'<p class="meta">{strings["questionnaire"]}: {meta_line}</p>'
        f'<p class="count">{answered} / {total} {_e(strings["answered"])}</p>'
        "<table><thead><tr>"
        f"<th>{_e(strings['question'])}</th>"
        f'<th class="principle">{_e(strings["principle"])}</th>'
        f"<th>{_e(strings['resources'])}</th>"
        f"<th>{_e(strings['status'])}</th>"
        "</tr></thead><tbody>"
        f"{''.join(row_html)}"
        "</tbody></table>"
        f"<h2>{_e(strings['relatedDmps'])}</h2>"
        f"{dmp_html}"
        f'<p><a href="{_e(full_url)}">{_e(strings["viewFull"])}</a></p>'
        f"<footer>{''.join(footer_lines)}</footer>"
        "</body></html>"
    )
