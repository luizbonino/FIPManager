<template>
  <div class="fer-picker">
    <fieldset
      v-if="showSuggested && (suggested.length > 0 || suggestedPhrases.length > 0)"
      class="suggested-fieldset"
    >
      <legend>{{ $t('editor.suggestedOptions') }}</legend>
      <label v-for="opt in suggested" :key="opt.id" class="suggested-option">
        <input
          type="checkbox"
          :checked="checkedFerIds.includes(opt.id)"
          :disabled="disabled"
          @change="onToggleSuggested(opt, ($event.target as HTMLInputElement).checked)"
        />
        <span class="suggested-option-text">
          <span class="suggested-option-label">{{ labelOf(opt) }}</span>
          <span v-if="opt.homepage" class="suggested-option-homepage">{{ opt.homepage }}</span>
        </span>
      </label>

      <label v-for="(phrase, phraseIndex) in suggestedPhrases" :key="`phrase-${phraseIndex}`" class="suggested-option">
        <input
          type="checkbox"
          :checked="checkedPhraseIndexes.includes(phraseIndex)"
          :disabled="disabled"
          @change="onTogglePhrase(phraseIndex, ($event.target as HTMLInputElement).checked)"
        />
        <span class="suggested-option-text">
          <span class="suggested-option-label">{{ phraseLabel(phrase) }}</span>
        </span>
      </label>

      <label class="suggested-option other-option">
        <input v-model="otherChecked" type="checkbox" :disabled="disabled" />
        <span class="suggested-option-text">
          <span class="suggested-option-label">{{ $t('fip.otherOption') }}</span>
        </span>
      </label>
      <div v-if="otherChecked" class="other-input-row">
        <label class="sr-only" :for="otherInputId">{{ $t('fip.otherPlaceholder') }}</label>
        <input
          :id="otherInputId"
          v-model="otherText"
          type="text"
          class="fer-input"
          :placeholder="$t('fip.otherPlaceholder')"
          :disabled="disabled"
          @keydown.enter.prevent="onAddOther"
          @blur="onOtherBlur"
        />
        <button type="button" class="other-add-btn" :disabled="disabled || !otherText.trim()" @click="onAddOther">
          {{ $t('common.add') }}
        </button>
      </div>
    </fieldset>

    <div v-if="mode === 'catalogue'" class="catalogue-mode">
      <label class="sr-only" :for="inputId">{{ $t('editor.chooseFer') }}</label>
      <input
        :id="inputId"
        v-model="query"
        type="text"
        class="fer-input"
        :placeholder="$t('editor.searchFer')"
        :disabled="disabled"
        autocomplete="off"
        @focus="showList = true"
        @input="showList = true"
        @blur="onBlur"
      />
      <ul v-if="showList && filtered.length > 0" class="fer-list">
        <li v-for="opt in filtered" :key="opt.id">
          <button type="button" class="fer-option" @mousedown.prevent="select(opt)">
            <span class="fer-option-label">{{ labelOf(opt) }}</span>
            <span v-if="opt.homepage" class="fer-option-homepage">{{ opt.homepage }}</span>
          </button>
        </li>
      </ul>
      <p v-else-if="showList && query.trim()" class="no-match">
        {{ $t('editor.noFerMatch') }}
      </p>
    </div>

    <div v-else class="free-text-mode">
      <label class="sr-only" :for="inputId">{{ $t('editor.freeTextPlaceholder') }}</label>
      <input
        :id="inputId"
        v-model="freeTextValue"
        type="text"
        class="fer-input"
        :placeholder="$t('editor.freeTextPlaceholder')"
        :disabled="disabled"
        @input="onFreeTextInput"
      />
    </div>

    <button v-if="allowFreeText !== false" type="button" class="toggle-mode" :disabled="disabled" @click="toggleMode">
      {{ mode === 'catalogue' ? $t('editor.useFreeText') : $t('editor.useCatalogue') }}
    </button>
  </div>
</template>

<script lang="ts">
// Module-scope (not inside `<script setup>`, which re-runs per component
// instance): a plain `<script>` block's top level executes once, when the
// module is first imported, so this counter is shared across every
// `FerPicker` instance ever mounted — unlike a `let uid = 0` declared
// inside `<script setup>`, which would reset to 0 on every mount and hand
// out duplicate `#fer-picker-1` / `#fer-picker-other-1` ids whenever two
// pickers are on screen at once (a question with both a FER type and
// suggested phrases, spec 10 §2, renders more than one).
let uid = 0
</script>

<script lang="ts" setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { resolveLang } from '@/lib/lang'
import type { FerOut, SuggestedPhrase } from '@/types/api'

/**
 * Combobox over the catalogue FERs of one `ferType` (spec 02 §2.2): a
 * search box filtering `options` client-side, and a "Use my own wording"
 * toggle writing `ferFreeText` instead. `ferId` xor `ferFreeText`, matching
 * the backend validator — `change` always emits exactly one of the two set.
 *
 * spec 08 §1.5: optionally, a quick-pick `<fieldset>` of `suggested` FERs
 * above the search box (only while `showSuggested`), each a checkbox
 * emitting `toggleSuggested`; `checkedFerIds` tells this component which
 * suggestions already have a declaration elsewhere in the answer (the spec
 * names `suggested`/`allowFreeText`/`showSuggested` as the new props but
 * does not spell out how the checkbox state itself is sourced — the
 * question's whole answer lives in the store, not in one picker instance —
 * so this is the smallest addition that makes "checked reflects reality"
 * true: `QuestionCard.vue` derives it from `store.fip.answers[...].declarations`).
 * `allowFreeText: false` hides the "Use my own wording" toggle and pins `mode`
 * to `'catalogue'`.
 *
 * spec 08 §1.5 extension: `suggestedPhrases` renders one checkbox per
 * generic free-text option after the FER checkboxes (`checkedPhraseIndexes`
 * tells this component which are already declared, same idea as
 * `checkedFerIds`), emitting `togglePhrase`; a built-in "Other" checkbox
 * always sits last, revealing a one-line free-text input + add button that
 * emits `addOther` and then re-hides itself — a plain UI affordance with no
 * state of its own to reconcile against the store.
 */
const props = withDefaults(
  defineProps<{
    options: FerOut[]
    ferId: string | null
    ferFreeText: string | null
    disabled?: boolean
    suggested?: FerOut[]
    suggestedPhrases?: SuggestedPhrase[]
    checkedPhraseIndexes?: number[]
    allowFreeText?: boolean
    showSuggested?: boolean
    checkedFerIds?: string[]
  }>(),
  {
    suggested: () => [],
    suggestedPhrases: () => [],
    checkedPhraseIndexes: () => [],
    allowFreeText: true,
    showSuggested: false,
    checkedFerIds: () => [],
  }
)

const emit = defineEmits<{
  change: [{ ferId: string | null; ferFreeText: string | null }]
  toggleSuggested: [ferId: string, checked: boolean]
  togglePhrase: [index: number, checked: boolean]
  addOther: [text: string]
}>()

const { locale } = useI18n()

const instanceId = ++uid
const inputId = `fer-picker-${instanceId}`
const otherInputId = `fer-picker-other-${instanceId}`

const mode = ref<'catalogue' | 'freeText'>(
  props.allowFreeText === false ? 'catalogue' : props.ferFreeText ? 'freeText' : 'catalogue'
)
const showList = ref(false)

function onToggleSuggested(opt: FerOut, checked: boolean) {
  emit('toggleSuggested', opt.id, checked)
}

function labelOf(opt: FerOut): string {
  return resolveLang(opt.label, locale.value) ?? opt.id
}

function phraseLabel(phrase: SuggestedPhrase): string {
  return resolveLang(phrase.text, locale.value) ?? ''
}

function onTogglePhrase(index: number, checked: boolean) {
  emit('togglePhrase', index, checked)
}

// The "Outros" checkbox (spec 08 §1.5 extension): purely local UI state —
// ticking just reveals the input, adding emits `addOther` and re-hides
// itself, so there is nothing here to reconcile against the store (unlike
// the FER/phrase checkboxes, whose checked state mirrors an existing
// declaration).
const otherChecked = ref(false)
const otherText = ref('')

function onAddOther() {
  const trimmed = otherText.value.trim()
  if (!trimmed) {
    otherChecked.value = false
    return
  }
  emit('addOther', trimmed)
  otherText.value = ''
  otherChecked.value = false
}

function onOtherBlur() {
  if (!otherText.value.trim()) {
    otherChecked.value = false
  }
}

const selectedOption = computed(() => props.options.find((o) => o.id === props.ferId) ?? null)

const query = ref(selectedOption.value ? labelOf(selectedOption.value) : '')
const freeTextValue = ref(props.ferFreeText ?? '')

// Keep the local input in sync when the declaration changes from outside
// (e.g. store hydration after a save round trip) -- and, critically, keep
// `mode` in sync too. Bug: `mode` was only ever set once, from the props
// this instance happened to mount with; the "Other" built-in box (QuestionCard's
// virtual placeholder row, spec 08 §1.5) mounts a FerPicker with
// `ferId: null, ferFreeText: null` (`mode` picks 'catalogue'), and when
// `addOther` turns that placeholder into a real free-text declaration, Vue
// reuses this *same* instance (`DeclarationEditor`'s `:key="row.index"`
// never changes -- the placeholder and the real row are both index 0) --
// so without this, `mode` stayed 'catalogue' forever and the new
// `ferFreeText` never rendered until a full reload remounted the tree.
// Ticking a suggested FER/phrase doesn't hit this: those checkboxes read
// `checkedFerIds`/`checkedPhraseIndexes` directly, entirely independent of
// this component's `mode`.
watch(
  () => props.ferId,
  () => {
    query.value = selectedOption.value ? labelOf(selectedOption.value) : query.value
    if (props.ferId) mode.value = 'catalogue'
  }
)
watch(
  () => props.ferFreeText,
  (v) => {
    freeTextValue.value = v ?? ''
    if (v) mode.value = 'freeText'
  }
)

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  const list = q ? props.options.filter((o) => labelOf(o).toLowerCase().includes(q)) : props.options
  return list.slice(0, 30)
})

function select(opt: FerOut) {
  query.value = labelOf(opt)
  showList.value = false
  emit('change', { ferId: opt.id, ferFreeText: null })
}

function onBlur() {
  // Delay so a `mousedown` on an option still registers before the list unmounts.
  setTimeout(() => {
    showList.value = false
  }, 150)
}

function toggleMode() {
  if (mode.value === 'catalogue') {
    mode.value = 'freeText'
    freeTextValue.value = freeTextValue.value || query.value
    emit('change', { ferId: null, ferFreeText: freeTextValue.value })
  } else {
    mode.value = 'catalogue'
    query.value = selectedOption.value ? labelOf(selectedOption.value) : ''
    emit('change', { ferId: selectedOption.value?.id ?? null, ferFreeText: null })
  }
}

function onFreeTextInput() {
  emit('change', { ferId: null, ferFreeText: freeTextValue.value })
}
</script>

<style scoped>
.fer-picker {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.suggested-fieldset {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin: 0;
  padding: 0.5rem 0.6rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-hover);
}

.suggested-fieldset legend {
  padding: 0 0.3rem;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
}

.suggested-option {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-height: 44px;
  cursor: pointer;
}

.suggested-option input[type='checkbox'] {
  width: 1.25rem;
  height: 1.25rem;
  flex: none;
}

.suggested-option-text {
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  flex-direction: column;
  line-height: 1.3;
}

.suggested-option-label {
  font-size: var(--font-size-sm);
  color: var(--color-text);
  overflow-wrap: anywhere;
}

.suggested-option-homepage {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  overflow-wrap: anywhere;
}

.other-input-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin: -0.15rem 0 0.2rem;
}

.other-input-row .fer-input {
  flex: 1 1 12rem;
  min-width: 0;
}

.other-add-btn {
  flex: none;
  min-height: 44px;
  padding: 0.4rem 0.9rem;
  border: 1px solid var(--color-primary);
  border-radius: var(--border-radius-sm);
  background: none;
  color: var(--color-primary);
  font-size: var(--font-size-sm);
  white-space: nowrap;
}

.other-add-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.catalogue-mode,
.free-text-mode {
  position: relative;
}

.fer-input {
  width: 100%;
  min-height: 44px;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
  font-size: var(--font-size-md);
}

.fer-list {
  position: absolute;
  z-index: 20;
  top: calc(100% + 2px);
  left: 0;
  right: 0;
  max-height: 14rem;
  overflow-y: auto;
  margin: 0;
  padding: 0.25rem;
  list-style: none;
  background-color: var(--color-background);
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  box-shadow: var(--shadow-md);
}

.fer-option {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: 44px;
  padding: 0.4rem 0.6rem;
  border: none;
  background: none;
  text-align: left;
  color: var(--color-text);
  border-radius: var(--border-radius-sm);
}

.fer-option:hover,
.fer-option:focus {
  background-color: var(--color-hover);
}

.fer-option-label {
  font-size: var(--font-size-sm);
}

.fer-option-homepage {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.no-match {
  margin: 0.25rem 0 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.toggle-mode {
  align-self: flex-start;
  min-height: 44px;
  padding: 0.3rem 0.6rem;
  border: none;
  background: none;
  color: var(--color-link);
  font-size: var(--font-size-sm);
  text-decoration: underline;
}
</style>
