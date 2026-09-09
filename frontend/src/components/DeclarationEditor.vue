<template>
  <div class="declaration-editor">
    <FerPicker
      :options="options"
      :fer-id="declaration.ferId ?? null"
      :fer-free-text="declaration.ferFreeText ?? null"
      :disabled="readOnly"
      @change="onFerChange"
    />
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
    <button v-if="!readOnly" type="button" class="remove-btn" @click="$emit('remove')">
      {{ $t('editor.removeDeclaration') }}
    </button>

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
import type { Declaration, DeclarationStatus, FerOut, RelatedDmp } from '@/types/api'

/**
 * `FerPicker` + `StatusSelect` + optional note + remove button (spec 02 §2.2).
 * Reads/writes the shared editor store directly rather than round-tripping
 * events through `QuestionCard`, since the store is the single source of
 * truth for the whole editor.
 */
const props = defineProps<{
  questionId: string
  index: number
  declaration: Declaration
  options: FerOut[]
}>()

defineEmits<{ remove: [] }>()

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
