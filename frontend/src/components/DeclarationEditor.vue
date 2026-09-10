<template>
  <div class="declaration-editor">
    <FerPicker
      :options="options"
      :fer-id="declaration.ferId ?? null"
      :fer-free-text="declaration.ferFreeText ?? null"
      :disabled="readOnly"
      :suggested="suggested"
      :suggested-phrases="suggestedPhrases"
      :checked-phrase-indexes="checkedPhraseIndexes"
      :allow-free-text="allowFreeText"
      :show-suggested="showSuggested"
      :checked-fer-ids="checkedFerIds"
      @change="onFerChange"
      @toggle-suggested="(ferId, checked) => $emit('toggleSuggested', ferId, checked)"
      @toggle-phrase="(index, checked) => $emit('togglePhrase', index, checked)"
      @add-other="(text) => $emit('addOther', text)"
    />

    <template v-if="!compact">
      <StatusSelect
        :model-value="declaration.status"
        :disabled="readOnly"
        @update:model-value="onStatusChange"
      />
      <label class="note-field">
        <span class="sr-only">{{ $t('editor.note') }}</span>
        <input
          :value="noteValue"
          type="text"
          :placeholder="$t('editor.note')"
          :disabled="readOnly"
          @change="onNoteChange"
        />
      </label>
    </template>

    <button v-if="!readOnly" type="button" class="remove-btn" @click="$emit('remove')">
      {{ $t('editor.removeDeclaration') }}
    </button>

    <div v-if="showSuccessor && !compact" class="successor-row">
      <label class="successor-label">{{ $t('editor.successor') }}</label>
      <FerPicker
        :options="options"
        :fer-id="declaration.successorFerId ?? null"
        :fer-free-text="declaration.successorFreeText ?? null"
        :disabled="readOnly"
        @change="onSuccessorChange"
      />
      <p class="successor-hint">{{ $t('editor.successorHint') }}</p>
    </div>

    <!-- spec 08 §1.5: compactDeclarations collapses the status control (and
         note/successor) behind "more", closed by default, with the status
         still visible as a badge on the summary line (spec 02 §4.3: colour
         is never the only signal). -->
    <details v-if="compact" class="more-details">
      <summary class="more-summary">
        <StatusBadge :status="declaration.status" />
        <span class="more-label">{{ $t('editor.more') }}</span>
      </summary>
      <div class="more-body">
        <StatusSelect
          :model-value="declaration.status"
          :disabled="readOnly"
          @update:model-value="onStatusChange"
        />
        <label class="note-field">
          <span class="sr-only">{{ $t('editor.note') }}</span>
          <input
            :value="noteValue"
            type="text"
            :placeholder="$t('editor.note')"
            :disabled="readOnly"
            @change="onNoteChange"
          />
        </label>
        <div v-if="showSuccessor" class="successor-row">
          <label class="successor-label">{{ $t('editor.successor') }}</label>
          <FerPicker
            :options="options"
            :fer-id="declaration.successorFerId ?? null"
            :fer-free-text="declaration.successorFreeText ?? null"
            :disabled="readOnly"
            @change="onSuccessorChange"
          />
          <p class="successor-hint">{{ $t('editor.successorHint') }}</p>
        </div>
      </div>
    </details>

    <details v-if="hasRelatedDmps" class="evidence">
      <summary>{{ $t('dmp.evidence') }}</summary>
      <div class="evidence-body">
        <label class="evidence-field">
          <span class="sr-only">{{ $t('dmp.evidencePlan') }}</span>
          <select :value="dmpIndexValue" :disabled="readOnly" @change="onPlanChange">
            <option value="">{{ $t('dmp.evidencePlan') }}</option>
            <option v-for="(dmp, idx) in relatedDmps" :key="idx" :value="idx">
              {{ dmpLabel(dmp) }}
            </option>
          </select>
        </label>

        <template v-if="hasPlanSelected">
          <label class="evidence-field">
            <span class="sr-only">{{ $t('dmp.evidenceSection') }}</span>
            <select :value="sectionSelectValue" :disabled="readOnly" @change="onSectionSelectChange">
              <option value="">{{ $t('dmp.evidenceSection') }}</option>
              <option v-for="letter in SECTION_LETTERS" :key="letter" :value="letter">{{ letter }}</option>
              <option value="__other">{{ $t('dmp.sectionOther') }}</option>
            </select>
          </label>
          <input
            v-if="sectionIsOther"
            type="text"
            class="evidence-section-other"
            :value="declaration.dmpEvidence?.section ?? ''"
            maxlength="40"
            :placeholder="$t('dmp.sectionOther')"
            :disabled="readOnly"
            @change="onSectionOtherChange"
          />
          <label class="evidence-field">
            <span class="sr-only">{{ $t('dmp.evidenceQuestion') }}</span>
            <input
              type="text"
              maxlength="120"
              :value="declaration.dmpEvidence?.questionRef ?? ''"
              placeholder="C.3"
              :disabled="readOnly"
              @change="onQuestionRefChange"
            />
          </label>
          <p class="evidence-hint">{{ $t('dmp.evidenceHint') }}</p>
        </template>
      </div>
    </details>
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import { useFipEditorStore } from '@/stores/fipEditor'
import { resolveLang } from '@/lib/lang'
import FerPicker from './FerPicker.vue'
import StatusSelect from './StatusSelect.vue'
import StatusBadge from './StatusBadge.vue'
import type { Declaration, DeclarationStatus, FerOut, RelatedDmp, SuggestedPhrase } from '@/types/api'

/**
 * `FerPicker` + `StatusSelect` + optional note + remove button (spec 02 §2.2).
 * Reads/writes the shared editor store directly rather than round-tripping
 * events through `QuestionCard`, since the store is the single source of
 * truth for the whole editor.
 *
 * spec 08 §1.5: `suggested`/`allowFreeText`/`showSuggested`/`checkedFerIds`
 * forward straight through to the (first, non-successor) `FerPicker`, and
 * `toggleSuggested` bubbles up unchanged for `QuestionCard.vue` to apply
 * against the store. `compact` (the model's `compactDeclarations`) hides
 * the status control, note and successor picker behind a "more" `<details>`,
 * closed by default, with the status still visible as a `StatusBadge`.
 *
 * spec 08 §1.5 extension: `suggestedPhrases`/`checkedPhraseIndexes` forward
 * the same way, and `togglePhrase`/`addOther` bubble up unchanged.
 */
const props = withDefaults(
  defineProps<{
    questionId: string
    index: number
    declaration: Declaration
    options: FerOut[]
    suggested?: FerOut[]
    suggestedPhrases?: SuggestedPhrase[]
    checkedPhraseIndexes?: number[]
    allowFreeText?: boolean
    showSuggested?: boolean
    checkedFerIds?: string[]
    compact?: boolean
  }>(),
  {
    suggested: () => [],
    suggestedPhrases: () => [],
    checkedPhraseIndexes: () => [],
    allowFreeText: true,
    showSuggested: false,
    checkedFerIds: () => [],
    compact: false,
  }
)

defineEmits<{
  remove: []
  toggleSuggested: [ferId: string, checked: boolean]
  togglePhrase: [index: number, checked: boolean]
  addOther: [text: string]
}>()

const store = useFipEditorStore()
const readOnly = computed(() => store.readOnly)

const noteValue = computed(() => {
  const language = store.fip?.language ?? 'en'
  return resolveLang(props.declaration.note ?? null, language) ?? ''
})

function onFerChange(payload: { ferId: string | null; ferFreeText: string | null }) {
  store.setDeclaration(props.questionId, props.index, payload)
}

function onStatusChange(status: DeclarationStatus) {
  store.setDeclaration(props.questionId, props.index, { status })
}

// spec 05 §5: the second picker exists only for a planned-replacement
// declaration; `store.setDeclaration` itself clears both successor fields
// the moment the merged status stops being 'planned-replacement', so no
// 422 can ever be saved regardless of ordering between this and the status change.
const showSuccessor = computed(() => props.declaration.status === 'planned-replacement')

function onSuccessorChange(payload: { ferId: string | null; ferFreeText: string | null }) {
  store.setDeclaration(props.questionId, props.index, {
    successorFerId: payload.ferId,
    successorFreeText: payload.ferFreeText,
  })
}

function onNoteChange(event: Event) {
  const value = (event.target as HTMLInputElement).value
  const language = store.fip?.language ?? 'en'
  store.setDeclaration(props.questionId, props.index, {
    note: value ? { [language]: value } : null,
  })
}

// "Evidence in DMP" (spec 06 §2.3): rendered only while >= 1 DMP is linked
// to this FIP. Section is one of the FioDMP letters A-G, or free text via
// `dmp.sectionOther`. Writes go through `store.setDmpEvidence`, itself a
// thin wrapper over `store.setDeclaration`.
const SECTION_LETTERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G']

const relatedDmps = computed<RelatedDmp[]>(() => store.fip?.relatedDmps ?? [])
const hasRelatedDmps = computed(() => relatedDmps.value.length > 0)

const dmpIndexValue = computed(() => props.declaration.dmpEvidence?.dmpIndex ?? '')
const hasPlanSelected = computed(() => props.declaration.dmpEvidence != null)

const sectionSelectValue = computed(() => {
  const section = props.declaration.dmpEvidence?.section
  if (!section) return ''
  return SECTION_LETTERS.includes(section) ? section : '__other'
})
const sectionIsOther = computed(() => sectionSelectValue.value === '__other')

function dmpLabel(dmp: RelatedDmp): string {
  let base = dmp.dmpId ?? ''
  if (!base) {
    try {
      base = new URL(dmp.url).host
    } catch {
      base = dmp.url
    }
  }
  return dmp.version ? `${base} v${dmp.version}` : base
}

function onPlanChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  if (value === '') {
    store.setDmpEvidence(props.questionId, props.index, null)
    return
  }
  store.setDmpEvidence(props.questionId, props.index, {
    dmpIndex: Number(value),
    section: props.declaration.dmpEvidence?.section ?? null,
    questionRef: props.declaration.dmpEvidence?.questionRef ?? null,
  })
}

function onSectionSelectChange(event: Event) {
  const dmpIndex = props.declaration.dmpEvidence?.dmpIndex
  if (dmpIndex === undefined) return
  const value = (event.target as HTMLSelectElement).value
  const section = value === '' ? null : value === '__other' ? '' : value
  store.setDmpEvidence(props.questionId, props.index, {
    dmpIndex,
    section,
    questionRef: props.declaration.dmpEvidence?.questionRef ?? null,
  })
}

function onSectionOtherChange(event: Event) {
  const dmpIndex = props.declaration.dmpEvidence?.dmpIndex
  if (dmpIndex === undefined) return
  const value = (event.target as HTMLInputElement).value
  store.setDmpEvidence(props.questionId, props.index, {
    dmpIndex,
    section: value || null,
    questionRef: props.declaration.dmpEvidence?.questionRef ?? null,
  })
}

function onQuestionRefChange(event: Event) {
  const dmpIndex = props.declaration.dmpEvidence?.dmpIndex
  if (dmpIndex === undefined) return
  const value = (event.target as HTMLInputElement).value
  store.setDmpEvidence(props.questionId, props.index, {
    dmpIndex,
    section: props.declaration.dmpEvidence?.section ?? null,
    questionRef: value || null,
  })
}
</script>

<style scoped>
.declaration-editor {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.5rem;
  padding: 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-hover);
}

.note-field input {
  width: 100%;
  min-height: 44px;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
  font-size: var(--font-size-sm);
}

.remove-btn {
  justify-self: start;
  min-height: 44px;
  padding: 0.3rem 0.75rem;
  border: 1px solid var(--color-error);
  border-radius: var(--border-radius-sm);
  background: none;
  color: var(--color-error);
  font-size: var(--font-size-sm);
}

.more-details {
  grid-column: 1 / -1;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
}

.more-summary {
  cursor: pointer;
  min-height: 44px;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
}

.more-label {
  font-size: var(--font-size-sm);
  color: var(--color-link);
}

.more-body {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0 0.75rem 0.75rem;
}

.successor-row {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  padding: 0.6rem;
  border: 1px solid var(--color-status-planned-replacement);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
}

.successor-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-status-planned-replacement);
}

.successor-hint {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.evidence {
  grid-column: 1 / -1;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
}

.evidence summary {
  cursor: pointer;
  min-height: 44px;
  display: flex;
  align-items: center;
  padding: 0.5rem 0.75rem;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.evidence-body {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0 0.75rem 0.75rem;
}

.evidence-field {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.evidence select,
.evidence input {
  min-height: 44px;
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
  font-size: var(--font-size-sm);
}

.evidence-hint {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

@media (min-width: 640px) {
  .declaration-editor {
    grid-template-columns: 2fr 1fr 1fr auto;
    align-items: start;
  }
}
</style>
