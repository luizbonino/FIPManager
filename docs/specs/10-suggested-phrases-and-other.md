# Spec 10 – Suggested phrases and "Outro"

Status: draft, 2026-09-10. Author: builder (backend), following up on spec 08-workshop-picklists.md
§4.2/§4.3. Driver: a co-facilitator reviewing the imported CONFOA 2026 area questionnaires, relayed to
the team as (paraphrased, pt-BR):

> "Quero que apareçam **todas** as opções de resposta do documento em cada pergunta — mesmo as que não
> correspondem a um recurso do catálogo (FER), tipo 'apenas texto não estruturado' ou 'conta do
> repositório'. Não podem simplesmente desaparecer. E o 'Outros' tem de abrir sempre uma caixa de texto,
> em todas as perguntas."

Before this change, `scripts/import-workshop-docx.py` resolved every document option to a catalogue FER
or an `inlineFers` draft, **except** a generic/placeholder option (curated as `"ferId": "skip"` in
`data/workshop/option-map.json`, 74 of them at the 2026-09-10 re-import) — those were counted in the
report and then silently dropped: not a suggestion, not a draft, not visible anywhere in the resulting
model. That is the specific complaint above. This spec adds a place for them: `question.suggestedPhrases`,
free-text options a participant ticks like a checkbox, distinct from a catalogue FER suggestion and from
the built-in "Outro" free-text box (which already exists per spec 08 §1.1 `allowFreeText`, unchanged here).

## 1. Content model

### 1.1 `question.suggestedPhrases`

A knowledge-model question (spec 01 §3, extended by spec 08 §1.1) gains one more optional field, a
sibling of `suggestedFerIds`:

```json
{"id": "F2", "ferType": "metadata-schema",
 "suggestedFerIds": ["https://schema.org/"],
 "suggestedPhrases": [
   {"text": {"pt-BR": "Apenas texto não estruturado"}},
   {"text": {"pt-BR": "Conta do repositório", "en": "Repository account"}}
 ],
 "allowFreeText": true}
```

| Field | Rule |
|---|---|
| `question.suggestedPhrases` | optional list of `{"text": LangMap}`, 0..`MAX_SUGGESTED_PHRASES` (12). Order = display order, after `suggestedFerIds`. |
| `suggestedPhrases[].text` | a LangMap (spec 04 §3.3 rule 3 / `_check_langmap`), same shape as `question.text`, but **`en` is not required** (the source document is pt-BR only — the same relaxation as an `inlineFers` label, spec 08 §7 A7) and each string is capped at 200 characters (not the usual 4000) and must be trimmed (no leading/trailing whitespace). |

Phrases are pure authoring metadata: they never touch `suggestedFerIds`, `inlineFers` or the FER
catalogue, and are allowed on a question that also carries `suggestedFerIds` (FERs and phrases are
independent, additive lists).

### 1.2 Validator (`km_content.validate_content`, new function `_validate_suggested_phrases`)

New codes, same `{path, code, message}` shape as spec 08 §1.2:

| Rule | Code |
|---|---|
| `suggestedPhrases` is a list | `invalid_value` if not |
| ≤ `MAX_SUGGESTED_PHRASES` (12) entries | `too_many` |
| each entry is an object | `missing_key` if not |
| each entry has a valid `text` LangMap (rule 3, `en` not required, 1..200 chars) | `missing_key` / `unknown_language` / `empty_string` / `too_long` (the shared `_check_langmap` codes) |
| each language string has no leading/trailing whitespace | `not_trimmed` |
| no two entries normalise to the same text (whitespace-collapsed, casefolded) in **any** language, checked pairwise across the whole list | `duplicate_phrase` |

Unlike `suggestedFerIds`, phrases need no `known_fer_ids` / catalogue lookup — there is nothing to
resolve. `MAX_SUGGESTED_PHRASES = 12` lives next to `MAX_SUGGESTED_FER_IDS` in `km_content.py`.

### 1.3 `MAX_SUGGESTED_FER_IDS` bump: 12 → 16

Unrelated to phrases directly, but discovered while re-running the importer for this change:
`confoa-2026-dados-omicos`'s `I3-metadata` question resolves **15** real catalogue FERs (not generic
placeholders — real, distinct FAIR Enabling Resources the document lists), one over the old cap of 12.
Removing generic options from `suggestedFerIds` (they were never counted there) does not change this;
the truncation was already happening before this change and is unrelated to `suggestedPhrases`.
`MAX_SUGGESTED_FER_IDS` is raised to **16** in `backend/fipm/km_content.py` and in the importer script's
own copy of the constant. The frontend mirror (`frontend/src/lib/kmContent.ts`, out of scope for this
backend change) needs the same bump to 16 before the picklist UI can show all 15 without truncating.

## 2. UI behaviour contract (frontend, for the frontend builder — no backend code implements this)

This section is a contract, not an implementation (frontend/ is out of scope for this change); it
describes what the picker must do so the backend fields above are actually usable.

- **Order**: within a question, the picker renders `suggestedFerIds` first (as today, spec 08 §1.5),
  then `suggestedPhrases`, then the built-in "Outro" checkbox last.
- **Ticking a phrase** appends an ordinary declaration `{ferFreeText: <phrase text in the FIP's
  language>, status: km.content.defaultDeclarationStatus ?? 'current'}` — exactly the same declaration
  shape a manually-typed free-text answer produces (spec 08 §1.1 `allowFreeText`). Language resolution
  follows the FIP's own language with the usual fallback chain, pt-PT ⇄ pt-BR → en (spec 01 §2): the
  phrase's LangMap is resolved the same way `questionText` is resolved for export (spec 01 §3.1), so a
  pt-PT FIP gets the pt-BR phrase text when no pt-PT variant exists.
- **Unticking a phrase** removes every declaration in that question whose `ferFreeText` equals *any*
  language variant of that phrase (not just the one currently displayed) — a participant who switched the
  UI language mid-session must still be able to untick what they ticked earlier. Confirms first
  (`window.confirm(editor.dropAnnotatedDeclaration)`, spec 08 §1.5) exactly when the matched declaration
  carries a note, `dmpEvidence`, a successor, or a non-default status, same rule as unticking a FER
  suggestion.
- **"Outro"** is unchanged in spirit (spec 08 §4.1 already treats it as a sentinel that sets
  `allowFreeText: true`, never a suggestion) but this spec makes its visibility rule explicit: the
  built-in "Outro" checkbox/text-box appears whenever a question has a non-empty `suggestedFerIds` **or**
  `suggestedPhrases` — i.e. whenever there is a picklist at all, matching the document's "Outros" that
  appears on every checklist question, and matching the co-facilitator's request verbatim. On a question
  with neither list, the ordinary free-text search box already does the same job (`allowFreeText`
  defaults `true`), so no extra "Outro" toggle is needed there.
- Ticking a phrase or "Outro" never creates or reuses a catalogue FER, an `inlineFers` draft, or any
  option-map entry — that pipeline is a build-time (importer) concept only, described in §3 below.

## 3. Decision: phrases are free text, never catalogue entries

A `suggestedPhrases` entry is deliberately **not** a FER, an `inlineFers` draft, or a step toward
becoming one. The document's generic options ("apenas texto não estruturado", "conta do repositório",
"sem política definida", …) describe a *situation*, not a resource — they have no homepage, no type in
the sense `data/fers/fer-types.json` needs, and promoting them would pollute the catalogue with 74 entries
no one could search for meaningfully. Keeping them as free text:

- costs nothing at export/RDF time (§4 confirms this with a regression test — a `ferFreeText` declaration
  is already a first-class, fully-supported shape);
- keeps the FER catalogue meaningful (`suggestedFerIds` stays "real resources only");
- matches how a participant would type the same text manually if the phrase didn't exist as a checkbox —
  ticking is a convenience, not a new data shape.

The corollary: `_validate_suggested_phrases` never touches `known_fer_ids`, `inlineFers`, or
`fer_types`, unlike `_validate_suggested_fer_ids`/`_validate_inline_fers` (spec 08 §1.2 rules 9/10/12).

## 4. Importer — `scripts/import-workshop-docx.py`

### 4.1 "skip" → `suggestedPhrases`

An option whose `data/workshop/option-map.json` entry is `{"ferId": "skip", ...}` (a generic/placeholder
option, curated by hand or via `data/fers/aliases-workshop.md`'s `unmatched: generic` rows) now becomes a
`suggestedPhrases` entry `{"text": {"pt-BR": "<original option text, original casing and accents>"}}` on
that question, appended in document order, **after** `suggestedFerIds` is fully built (FERs and drafts
first, phrases last within the question's own data — display order is a frontend concern, §2). The map's
`"skip"` sentinel **keeps its literal value** for backward compatibility — every existing curated entry in
`option-map.json` (and every row of `data/fers/aliases-workshop.md`) works unchanged; only its *meaning*
in the importer's output changes, from "dropped" to "shown as a free-text option". Within one question,
duplicate normalised texts collapse to one phrase entry (same `norm()` used for FER matching, spec 08
§4.2), and the list truncates at `MAX_SUGGESTED_PHRASES` (12) with a report line — mirroring the existing
`suggestedFerIds` truncation.

### 4.2 Sentinels unchanged

The three built-in sentinels (spec 08 §4.1) are untouched and stay entirely separate from
`suggestedPhrases`:

- `_OTHER_SENTINELS` ("Outro(s)", "especificar", …) — never a suggestion or a phrase; sets
  `allowFreeText: true` (already the default) and is handled entirely by the frontend's built-in "Outro"
  box (§2).
- `_NOT_APPLICABLE_SENTINELS` ("Não se aplica") — dropped, recorded in the report only; the §2 (spec 08)
  per-answer "not applicable" toggle is always available regardless.
- `_UNDEFINED_SENTINELS` ("Ainda não definido") — dropped; leaving the question unanswered *is*
  "undefined" (spec 08 §7 A3).

None of the three becomes a `suggestedPhrases` entry: they are not generic *options*, they are
meta-answers about the question itself, already represented elsewhere (free text, not-applicable,
unanswered).

### 4.3 `--overwrite-draft`

New flag. When the latest on-disk version of an area model (`confoa-2026-<slug>-<version>.json`) has
`"status": "draft"`, `--overwrite-draft` rewrites that file **in place** (same version, e.g. still
`1.0.0`) instead of refusing with the existing "changed on disk, rerun with --bump" behaviour. A latest
version whose on-disk `status` is `"published"` is **refused exactly as today** — `--overwrite-draft`
never touches published content, matching `--bump`'s existing safety property (`import-data` would refuse
a differing content hash on a published row anyway, spec 01 §3.3). `--bump` and `--overwrite-draft` may
both be passed; `--overwrite-draft` takes precedence when the latest version is a draft (in-place rewrite
instead of minting a new version).

This is what makes a re-run of a still-unpublished, unclaimed workshop draft practical: the five existing
CONFOA 2026 area models are all still `status: "draft"` and unclaimed (`owner_id: null`), so a facilitator
iterating on `data/fers/aliases-workshop.md` or `data/workshop/option-map.json` can re-run the importer
repeatedly without accumulating `-1.0.1`, `-1.0.2`, … files before anyone has even reviewed `1.0.0`.

### 4.4 2026-09-10 re-import

Re-run for the five existing areas:

```
uv run --project backend python scripts/import-workshop-docx.py \
    --docx "docs/workshop/PERFIS DE IMPLEMENTAÇÃO FAIR 2.docx" --overwrite-draft
```

(all other flags at their defaults — `--base`, `--seed`, `--map`, `--out`, `--aliases` already point at
the right files; `--report` defaults to `data/workshop/import-report-<today>.md`.) Report:
`data/workshop/import-report-2026-09-10.md`. All five files rewritten in place at `1.0.0` (still draft,
unclaimed), all still valid (`validate_content` against the real `data/fers/seed.json` catalogue: zero
errors on all five). Totals:

| Area | `suggestedPhrases` entries written | Max phrases on one question |
|---|---:|---:|
| Dados Ômicos | 49 | 7 |
| Biodiversidade | 63 | 7 |
| Agricultura | 60 | 7 |
| Saúde Pública | 58 | 6 |
| Enfermagem | 63 | 7 |
| **Total** | **293** | **7** (across all areas) |

74 distinct generic/placeholder texts (293 occurrences across the five areas — the same text can recur
under different questions/areas, each producing its own `suggestedPhrases` entry since phrases, like FER
suggestions, are per-question). `confoa-2026-dados-omicos`'s `I3-metadata` now carries all 15 resolved
FERs (no truncation, §1.3). The "Unresolved options" and "Type mismatches" report sections are
byte-identical to the 2026-09-09 run — nothing in this change affects FER resolution, only what happens
to already-classified "skip" options.

## 5. Exports — deliberately unchanged

Confirmed by `backend/tests/test_ac_10_phrase_free_text_export.py`: a FIP declaration whose `ferFreeText`
equals a `suggestedPhrases` entry's text is an ordinary free-text declaration and already round-trips
through JSON export/import, CSV export (`fer_free_text` column, `fer_id` empty) and Turtle export (the
free-text FER node, spec 03 §2.4) with no code change — the whole point of §3's decision. `SCHEMA_VERSION`
is untouched.

## 6. Acceptance criteria

**Backend (pytest)**

1. `validate_content` accepts a question with valid `suggestedPhrases` (1..12 entries, `en` not required,
   ≤ 200 chars, trimmed) alongside `suggestedFerIds`; rejects > 12 entries (`too_many`), an entry with
   empty/missing `text` (`missing_key`/`empty_string`), a non-object entry (`missing_key`), untrimmed text
   (`not_trimmed`), a duplicate normalised text across entries (`duplicate_phrase`, checked across
   languages too) and a non-list value (`invalid_value`). — `test_ac_10_suggested_phrases_validator.py`.
2. `validate_content` accepts 13..16 `suggestedFerIds` (cap now 16) and still rejects 17. —
   `test_ac_08_01_02_suggested_fer_validator.py` (updated).
3. A FIP declaration with `ferFreeText` matching a `suggestedPhrases` entry exports correctly in JSON,
   CSV and Turtle and round-trips through `POST /api/fips/import`. —
   `test_ac_10_phrase_free_text_export.py`.
4. The importer: a "skip"-mapped option becomes a `suggestedPhrases` entry with the original casing, in
   document order, capped at 12 with a report line; the three sentinels never become phrases;
   `--overwrite-draft` rewrites an on-disk draft in place and refuses (soft-skips, same as today without
   `--bump`) an on-disk published version; a byte-identical option-map "skip" entry still round-trips. —
   `test_import_workshop_docx.py` (`test_ac18_aliases_md_skips_generic_and_resolves_multi_iri`,
   `test_ac18_overwrite_draft_rewrites_in_place`, `test_ac18_overwrite_draft_refuses_published_latest`).
5. `python -m fipm import-data` (the app-startup path, `fipm.main`) updates an unowned, unpublished draft
   knowledge model when its on-disk `content_sha256` changes even though `(id, version)` is unchanged, and
   leaves a facilitator-claimed draft (`owner_id` set) untouched regardless of on-disk changes. —
   `test_ac_10_unowned_draft_startup_reimport.py` (this already worked —
   `import_knowledge_model_doc` compares `content_sha256`, not version alone; the tests are new
   confirmation, not a behaviour change).
6. The five real `data/knowledge-models/confoa-2026-*-1.0.0.json` files, re-imported 2026-09-10, all pass
   `validate_content` against the real FER catalogue and the "imports every model under
   data/knowledge-models" test suite (`test_km_content_validate.py`'s
   `test_import_data_reports_all_skipped_on_warm_db_with_real_data`, run twice for idempotency).

## 7. Out of scope / left for the frontend builder

- `frontend/src/lib/kmContent.ts`: mirror `_validate_suggested_phrases`/`MAX_SUGGESTED_PHRASES` and bump
  its own `MAX_SUGGESTED_FER_IDS` mirror to 16 (§1.3).
- `FerPicker.vue` / `QuestionCard.vue` / `KmQuestionCard.vue`: implement §2's UI contract (phrase
  checkboxes, ordering, untick-by-any-language-variant removal, the "Outro" visibility rule).
- `KmLangTabs.vue`-based phrase editor in the knowledge-model editor UI (add/reorder/remove a
  `suggestedPhrases` entry, mirroring the existing "Suggested options" block for `suggestedFerIds`, spec
  08 §1.4).

## 8. Cross-references

- spec 08-workshop-picklists.md §4.1's "Sentinels" row and §4.2's option-map description do not claim a
  "skip"-mapped option is *dropped* (they describe the FER-matching pipeline only); no correction was
  needed there. This spec is the first place the "skip" sentinel's participant-facing fate is documented.
- `MAX_SUGGESTED_FER_IDS` (§1.3) and `MAX_SUGGESTED_PHRASES` (§1.1) both live in
  `backend/fipm/km_content.py`, next to each other, mirroring spec 08 §1.2's `MAX_INLINE_FERS`.
