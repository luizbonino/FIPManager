"""AC8 (spec 07-mail-and-migration.md §7): `render_mail` renders both
templates (`verify-email`, `password-reset`) in all four languages with no
`KeyError` and a non-empty subject each; a `pt-PT` user with only `pt-BR`
present gets the `pt-BR` file; a missing language file fails the suite (all
four directories exist -- exercised here by asserting the fixture tree
itself, since the shipped `data/i18n/mail/` tree is out of scope for this
backend change per the builder brief)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fipm.config import get_settings
from fipm.mail import MailTemplateMissing, _load_template, render_mail

TEMPLATES = ("verify-email", "password-reset", "password-changed")
LANGUAGES = ("en", "pt-PT", "pt-BR", "es")

CTX = {
    "appName": "FIP Manager",
    "displayName": "Test User",
    "link": "http://testserver/verify?token=abc",
    "baseUrl": "http://testserver",
    "expiresHours": "24",
    "contactEmail": "contact@example.org",
}


@pytest.mark.parametrize("template", TEMPLATES)
@pytest.mark.parametrize("lang", LANGUAGES)
def test_render_mail_all_templates_all_languages(template, lang):
    subject, text = render_mail(template, lang, CTX)
    assert subject.strip() != ""
    assert text.strip() != ""
    # str.format placeholders are all filled -- no stray "{" left over.
    assert "{" not in subject
    assert "{" not in text


def test_all_four_language_directories_exist_for_every_template(settings):
    """spec §1: "an untranslated file may copy en, never be missing --
    absence is a test failure, not a runtime surprise"."""
    for lang in LANGUAGES:
        for template in TEMPLATES:
            path = Path(settings.data_dir) / "i18n" / "mail" / lang / f"{template}.txt"
            assert path.is_file(), f"missing {path}"


def test_pt_pt_falls_back_to_pt_br_when_pt_pt_absent(tmp_path, monkeypatch):
    """A synthetic data_dir with only pt-BR present for one template: a
    pt-PT request falls back to it rather than jumping straight to en."""
    base = tmp_path / "i18n" / "mail"
    (base / "en").mkdir(parents=True)
    (base / "pt-BR").mkdir(parents=True)
    (base / "en" / "only-pt-br.txt").write_text("Subject: EN subject\n\nEN body\n")
    (base / "pt-BR" / "only-pt-br.txt").write_text("Subject: PT-BR subject\n\nPT-BR body\n")

    _load_template.cache_clear()
    monkeypatch.setenv("FIPM_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        subject, text = render_mail("only-pt-br", "pt-PT", {})
        assert subject == "PT-BR subject"
        assert "PT-BR body" in text
    finally:
        get_settings.cache_clear()
        _load_template.cache_clear()


def test_missing_template_raises_mail_template_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("FIPM_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    _load_template.cache_clear()
    try:
        with pytest.raises(MailTemplateMissing):
            render_mail("does-not-exist", "en", {})
    finally:
        get_settings.cache_clear()
        _load_template.cache_clear()
