"""spec 02-core-flows.md §8/§9 item 9 (backend half): the same six cases the
frontend's `lib/lang.ts` `resolveLang` is tested against, run here against
`fipm.exporters.resolve_lang` -- the fallback resolver `resolveLang` mirrors
-- so the two implementations cannot drift. `resolveLang(map, locale)` has
the frontend's default fallback baked in as `"en"`, matching
`resolve_lang`'s `default_language="en"` default."""

from __future__ import annotations

import pytest

from fipm.exporters import resolve_lang


@pytest.mark.parametrize(
    ("langmap", "language", "expected"),
    [
        # 1. Exact locale wins over any fallback.
        ({"en": "E", "pt-PT": "P", "pt-BR": "B"}, "pt-PT", "P"),
        # 2. pt-PT missing falls back to its pt-BR sibling.
        ({"en": "E", "pt-BR": "B"}, "pt-PT", "B"),
        # 3. pt-BR missing falls back to its pt-PT sibling.
        ({"en": "E", "pt-PT": "P"}, "pt-BR", "P"),
        # 4. pt-PT missing, no pt-BR sibling either, falls back to "en".
        ({"en": "E"}, "pt-PT", "E"),
        # 5. A map with only an unrelated language ("de") returns that value
        #    (first-available fallback; no exact match, no sibling, no "en").
        ({"de": "D"}, "en", "D"),
    ],
)
def test_resolve_lang_table(langmap, language, expected):
    assert resolve_lang(langmap, language) == expected


def test_resolve_lang_null_or_empty_map_returns_null():
    # 6. null / {} both return null.
    assert resolve_lang(None, "en") is None
    assert resolve_lang({}, "en") is None
