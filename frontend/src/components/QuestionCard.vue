<template>
  <div class="question-card" :id="question.id">
    <div class="question-head">
      <span class="question-id">{{ question.id }}</span>
      <span v-if="ferTypeLabel" class="question-fer-chip">{{ ferTypeLabel }}</span>
      <label class="na-toggle">
        <input type="checkbox" :checked="notApplicable" :disabled="readOnly" @change="onToggleNotApplicable" />
        <span>{{ $t('editor.notApplicable') }}</span>
      </label>
    </div>
    <p class="question-text">{{ resolvedText }}</p>

    <details v-if="resolvedHelp" class="question-help">
      <summary>{{ $t('editor.help') }}</summary>
      <p>{{ resolvedHelp }}</p>
    </details>

    <div v-if="!notApplicable" class="declarations">
      <DeclarationEditor
        v-for="row in displayRows"
        :key="row.index"
        :question-id="question.id"
        :index="row.index"
        :declaration="row.declaration"
        :options="ferOptions"
        :suggested="row.index === 0 ? suggestedFers : []"
        :suggested-phrases="row.index === 0 ? suggestedPhrases : []"
        :checked-phrase-indexes="row.index === 0 ? checkedPhraseIndexes : []"
        :allow-free-text="allowFreeText"
        :show-suggested="row.index === 0 && hasSuggestions"
        :checked-fer-ids="checkedFerIds"
        :compact="compactDeclarations"
        @remove="onRemove(row.index)"
        @toggle-suggested="onToggleSuggested"
        @toggle-phrase="onTogglePhrase"
        @add-other="onAddOther"
      />
    </div>

    <button
      v-if="!readOnly && canAddMore && !notApplicable"
      type="button"
      class="add-declaration-btn"
      @click="onAdd"
    >
      {{ $t('editor.addDeclaration') }}
    </button>

    <label class="comment-field">
      <span>{{ notApplicable ? $t('editor.notApplicableWhy') : $t('editor.comment') }}</span>
      <textarea
        :value="answer?.comment ?? ''"
        rows="2"
        :disabled="readOnly"
        @change="onCommentChange"
      />
    </label>
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFipEditorStore } from '@/stores/fipEditor'
import { phraseMatchesFreeText, suggestedFersFor } from '@/lib/kmContent'
import { resolveLang } from '@/lib/lang'
import DeclarationEditor from './DeclarationEditor.vue'
import type { Declaration, FerOut, KnowledgeModelQuestion, SuggestedPhrase } from '@/types/api'

/**
 * One question of a section panel (spec 02 §2.2, extended by spec 08 §1.5/
 * §2.2): id badge, resolved text, FER-type chip, a "Not applicable" toggle,
 * collapsible Help, 0..n `DeclarationEditor` rows (the first carrying the
 * model's suggested-FER quick-pick, when it has one), an "Add declaration"
 * button (hidden once `allowMultiple` is false and one declaration exists,
 * or the question is marked N/A), and an optional comment.
 */
const props = defineProps<{
  question: KnowledgeModelQuestion
  ferTypeLabel: string | null
}>()

const store = useFipEditorStore()
const { locale, t } = useI18n()

const readOnly = computed(() => store.readOnly)

const answer = computed(() => store.fip?.answers.find((a) => a.questionId === props.question.id))
const declarations = computed(() => answer.value?.declarations ?? [])
const notApplicable = computed(() => answer.value?.notApplicable === true)

const canAddMore = computed(() => props.question.allowMultiple || declarations.value.length === 0)

const resolvedText = computed(() => resolveLang(props.question.text, locale.value) ?? props.question.id)
const resolvedHelp = computed(() => resolveLang(props.question.help, locale.value))

const ferOptions = computed<FerOut[]>(() => {
  const type = props.question.ferType
  if (!type) return []
  return Object.values(store.fers).filter((f) => f.type === type)
})

// spec 08 §1.1/§1.5: default true; a model authored before this feature has
// neither field, so both fall back to the spec defaults.
const allowFreeText = computed(() => props.question.allowFreeText ?? true)
const compactDeclarations = computed(() => store.km?.content.compactDeclarations === true)
const defaultDeclarationStatus = computed(() => store.km?.content.defaultDeclarationStatus ?? 'current')

/**
 * The question's suggested FERs, resolved against `km.content.inlineFers`
 * then the catalogue (spec §1.3) — `[]` once the question has none, which
 * also hides the quick-pick fieldset entirely (`FerPicker`'s `showSuggested`).
 */
const suggestedFers = computed<FerOut[]>(() => {
  if (!store.km) return []
  return suggestedFersFor(store.km.content, props.question.id, store.fers)
})

/** spec 08 §1.5 extension: generic free-text quick-pick options, a sibling of `suggestedFers`. */
const suggestedPhrases = computed<SuggestedPhrase[]>(() => props.question.suggestedPhrases ?? [])

const hasSuggestions = computed(() => suggestedFers.value.length > 0 || suggestedPhrases.value.length > 0)

const checkedFerIds = computed(() => declarations.value.map((d) => d.ferId).filter((id): id is string => !!id))

/** Indexes of `suggestedPhrases` that already have a matching declaration (spec 08 §1.5 extension). */
const checkedPhraseIndexes = computed(() =>
  suggestedPhrases.value.reduce<number[]>((acc, phrase, index) => {
    if (declarations.value.some((d) => phraseMatchesFreeText(phrase, d.ferFreeText))) acc.push(index)
    return acc
  }, [])
)

/**
 * `DeclarationEditor` rows to render: the real declarations, or — when
 * there are none yet and the question has suggestions — one *virtual* empty
 * row at index 0 so the quick-pick and search box have somewhere to live
 * (spec §1.5). Interacting with it (search, free text or a quick-pick tick)
 * creates the real declaration through the usual store calls; left
 * untouched, nothing is ever written.
 */
const displayRows = computed<{ declaration: Declaration; index: number }[]>(() => {
  if (declarations.value.length > 0) {
    return declarations.value.map((declaration, index) => ({ declaration, index }))
  }
  if (hasSuggestions.value) {
    return [{ declaration: { status: defaultDeclarationStatus.value }, index: 0 }]
  }
  return []
})

function onAdd() {
  store.addDeclaration(props.question.id, { status: defaultDeclarationStatus.value })
}

function onRemove(index: number) {
  store.removeDeclaration(props.question.id, index)
}

/**
 * spec §1.5: a declaration the checkbox alone can't fully represent (a
 * note, DMP evidence, a successor or a non-default status) needs a confirm
 * before an untick silently drops that context — shared by the FER
 * quick-pick and the suggested-phrase quick-pick (spec 10 §2).
 */
function isAnnotatedDeclaration(declaration: Declaration): boolean {
  return (
    !!(declaration.note && Object.keys(declaration.note).length > 0) ||
    !!declaration.dmpEvidence ||
    !!declaration.successorFerId ||
    !!declaration.successorFreeText ||
    declaration.status !== defaultDeclarationStatus.value
  )
}

/**
 * spec §1.5: a tick appends an ordinary declaration with the model's
 * default status; an untick removes the declaration whose `ferId` matches,
 * confirming first when it's annotated — silently dropping that context
 * would lose information the participant can't easily reconstruct.
 */
function onToggleSuggested(ferId: string, checked: boolean) {
  if (checked) {
    if (checkedFerIds.value.includes(ferId)) return
    store.addDeclaration(props.question.id, { ferId, status: defaultDeclarationStatus.value })
    return
  }
  const index = declarations.value.findIndex((d) => d.ferId === ferId)
  if (index === -1) return
  if (isAnnotatedDeclaration(declarations.value[index]) && !confirm(t('editor.dropAnnotatedDeclaration'))) return
  store.removeDeclaration(props.question.id, index)
}

/**
 * spec 10 §2: a tick resolves the phrase's text in the FIP's own language
 * (the same fallback chain export uses, spec 01 §2 — not the editor's UI
 * display language, which a participant may have switched mid-session) and
 * appends a free-text declaration with the model's default status. An
 * untick removes every declaration whose `ferFreeText` matches *any*
 * language variant of the phrase — a participant who switched UI language
 * must still be able to untick what they ticked earlier — confirming first
 * exactly when any matched declaration is annotated, same rule as the FER
 * quick-pick; removed highest index first so earlier indices don't shift
 * under a still-pending removal.
 */
function onTogglePhrase(index: number, checked: boolean) {
  const phrase = suggestedPhrases.value[index]
  if (!phrase) return
  if (checked) {
    const alreadyChecked = declarations.value.some((d) => phraseMatchesFreeText(phrase, d.ferFreeText))
    if (alreadyChecked) return
    const fipLanguage = store.fip?.language ?? 'en'
    const resolvedText = resolveLang(phrase.text, fipLanguage)
    if (!resolvedText) return
    store.addDeclaration(props.question.id, {
      ferId: null,
      ferFreeText: resolvedText,
      status: defaultDeclarationStatus.value,
      note: null,
    })
    return
  }
  const matching = declarations.value
    .map((d, i) => (phraseMatchesFreeText(phrase, d.ferFreeText) ? i : -1))
    .filter((i) => i !== -1)
  if (matching.length === 0) return
  const anyAnnotated = matching.some((i) => isAnnotatedDeclaration(declarations.value[i]))
  if (anyAnnotated && !confirm(t('editor.dropAnnotatedDeclaration'))) return
  for (const i of [...matching].reverse()) {
    store.removeDeclaration(props.question.id, i)
  }
}

/**
 * The built-in "Other" checkbox (spec 08 §1.5 extension): adds a plain
 * free-text declaration with the model's default status. It is not matched
 * against `suggestedPhrases`, so it renders afterwards like any other
 * free-text declaration rather than through a quick-pick checkbox.
 */
function onAddOther(text: string) {
  const trimmed = text.trim()
  if (!trimmed) return
  store.addDeclaration(props.question.id, {
    ferId: null,
    ferFreeText: trimmed,
    status: defaultDeclarationStatus.value,
    note: null,
  })
}

/**
 * spec §2.2: turning N/A on with declarations present confirms, then clears
 * them (the store enforces the two are mutually exclusive); turning it off
 * simply drops the flag. `notApplicable: false` is never stored (the
 * checked branch below only ever sets `true`).
 */
function onToggleNotApplicable(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  if (checked) {
    if (declarations.value.length > 0 && !confirm(t('editor.notApplicableConfirm'))) {
      // Leave the store untouched; the checkbox re-renders from `notApplicable` (still false).
      ;(event.target as HTMLInputElement).checked = false
      return
    }
    store.setNotApplicable(props.question.id, true)
  } else {
    store.setNotApplicable(props.question.id, false)
  }
}

function onCommentChange(event: Event) {
  const value = (event.target as HTMLTextAreaElement).value
  store.setComment(props.question.id, value || null)
}
</script>

<style scoped>
.question-card {
  padding: 1rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  background-color: var(--color-background);
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  scroll-margin-top: 5rem;
}

.question-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.question-id {
  font-family: monospace;
  font-size: var(--font-size-xs);
  /* Explicit chip fg/bg pair (not --color-secondary/--color-text-secondary):
     --color-secondary is overridden to a mid-tone slate by index.html's
     inline :root block, which paired with the muted gray text made this
     chip unreadable. --color-id-chip-* is dedicated to this chip only. */
  color: var(--color-id-chip-text);
  background-color: var(--color-id-chip-bg);
  padding: 0.15rem 0.4rem;
  border-radius: var(--border-radius-sm);
}

.question-fer-chip {
  font-size: var(--font-size-xs);
  color: var(--color-chip-text);
  background-color: var(--color-chip-bg);
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
}

.na-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin-left: auto;
  min-height: 44px;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
}

.na-toggle input {
  width: 1.25rem;
  height: 1.25rem;
}

.question-text {
  margin: 0;
  font-weight: var(--font-weight-medium);
}

.question-help summary {
  cursor: pointer;
  color: var(--color-link);
  font-size: var(--font-size-sm);
  min-height: 44px;
  display: flex;
  align-items: center;
}

.question-help p {
  margin: 0.25rem 0 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.declarations {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.add-declaration-btn {
  align-self: flex-start;
  min-height: 44px;
  padding: 0.4rem 0.9rem;
  border: 1px solid var(--color-primary);
  border-radius: var(--border-radius-sm);
  background: none;
  color: var(--color-primary);
  font-size: var(--font-size-sm);
}

.comment-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.comment-field textarea {
  padding: 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
  font-family: inherit;
  font-size: var(--font-size-sm);
  resize: vertical;
}
</style>
