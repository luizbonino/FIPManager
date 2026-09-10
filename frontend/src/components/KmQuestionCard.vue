<template>
  <div class="km-question-card" :class="{ hidden: question.hidden }">
    <div class="question-head">
      <span class="question-id">{{ question.id }}</span>
      <span v-if="question.hidden" class="hidden-chip">{{ $t('km.hidden') }}</span>
      <div class="head-actions no-print">
        <MoveButtons :can-up="canMoveUp" :can-down="canMoveDown" @up="$emit('moveUp')" @down="$emit('moveDown')" />
        <button
          v-if="!question.hidden"
          type="button"
          class="ghost-btn"
          :disabled="readOnly"
          @click="$emit('hide')"
        >
          {{ $t('km.hide') }}
        </button>
        <button v-else type="button" class="ghost-btn" :disabled="readOnly" @click="$emit('unhide')">
          {{ $t('km.unhide') }}
        </button>
        <button type="button" class="ghost-btn" :disabled="readOnly || alreadySplit" @click="$emit('split')">
          {{ $t('km.split') }}
        </button>
        <button type="button" class="ghost-btn danger" :disabled="readOnly" @click="onDelete">
          {{ $t('km.deleteQuestion') }}
        </button>
      </div>
    </div>

    <p v-if="question.hidden" class="hidden-hint">{{ $t('km.hiddenHint') }}</p>

    <div class="field-group">
      <span class="field-label">{{ $t('km.questionText') }}</span>
      <KmLangTabs
        :model-value="question.text"
        :default-lang="locale"
        :disabled="readOnly"
        @change="(lang, value) => $emit('updateText', lang, value)"
      />
    </div>

    <div class="field-group">
      <span class="field-label">{{ $t('km.help') }}</span>
      <KmLangTabs
        :model-value="question.help"
        multiline
        :default-lang="locale"
        :disabled="readOnly"
        @change="(lang, value) => $emit('updateHelp', lang, value)"
      />
    </div>

    <div class="controls-grid">
      <label class="control">
        <span>{{ $t('km.principle') }}</span>
        <select :value="question.principle ?? ''" :disabled="readOnly" @change="onPrincipleChange">
          <option value="">{{ $t('km.scopeNone') }}</option>
          <option v-for="p in PRINCIPLES" :key="p" :value="p">{{ p }}</option>
        </select>
      </label>

      <label class="control">
        <span>{{ $t('km.scope') }}</span>
        <select :value="question.scope ?? ''" :disabled="readOnly" @change="onScopeChange">
          <option value="">{{ $t('km.scopeNone') }}</option>
          <option value="metadata">{{ $t('matrix.scopeMetadata') }}</option>
          <option value="data">{{ $t('matrix.scopeData') }}</option>
        </select>
      </label>

      <label class="control">
        <span>{{ $t('km.ferType') }}</span>
        <select :value="question.ferType ?? ''" :disabled="readOnly" @change="onFerTypeChange">
          <option value="">{{ $t('km.ferTypeNone') }}</option>
          <option v-for="type in ferTypeOptions" :key="type.key" :value="type.key">{{ ferTypeLabel(type) }}</option>
        </select>
      </label>

      <label class="control checkbox">
        <input type="checkbox" :checked="question.required" :disabled="readOnly" @change="onRequiredChange" />
        <span>{{ $t('km.required') }}</span>
      </label>

      <label class="control checkbox">
        <input type="checkbox" :checked="question.allowMultiple" :disabled="readOnly" @change="onAllowMultipleChange" />
        <span>{{ $t('km.allowMultiple') }}</span>
      </label>
    </div>

    <KmSuggestedFers
      v-if="content"
      :content="content"
      :question-id="question.id"
      :fer-type="question.ferType"
      :suggested-fer-ids="question.suggestedFerIds ?? []"
      :fers="fers"
      :fer-type-options="ferTypeOptions"
      :allow-free-text="question.allowFreeText ?? true"
      :read-only="readOnly"
      @add="(ferId) => $emit('addSuggested', ferId)"
      @remove="(ferId) => $emit('removeSuggested', ferId)"
      @move="(ferId, direction) => $emit('moveSuggested', ferId, direction)"
      @add-inline="(fer) => $emit('addInlineFer', fer)"
      @update-allow-free-text="(value) => $emit('updateAllowFreeText', value)"
    />

    <KmSuggestedPhrases
      :phrases="question.suggestedPhrases ?? []"
      :read-only="readOnly"
      @add="$emit('addPhrase')"
      @remove="(index) => $emit('removePhrase', index)"
      @move="(index, direction) => $emit('movePhrase', index, direction)"
      @update-text="(index, lang, value) => $emit('updatePhraseText', index, lang, value)"
    />
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { resolveLang } from '@/lib/lang'
import { PRINCIPLES, type MoveDirection } from '@/lib/kmContent'
import { useKmEditorStore } from '@/stores/kmEditor'
import MoveButtons from './MoveButtons.vue'
import KmLangTabs from './KmLangTabs.vue'
import KmSuggestedFers from './KmSuggestedFers.vue'
import KmSuggestedPhrases from './KmSuggestedPhrases.vue'
import type { FerType, InlineFer, KnowledgeModelQuestion } from '@/types/api'

/**
 * One question of the editor's sections accordion (spec 04 §5, extended by
 * spec 08 §1.4): id badge, up/down, hide/unhide, split, delete, `KmLangTabs`
 * over `text` and `help`, controls for principle/scope/FER
 * type/required/allowMultiple, and the "Suggested options" block
 * (`KmSuggestedFers`). A hidden question stays editable but dims and
 * carries a "Hidden" chip.
 */
const props = defineProps<{
  question: KnowledgeModelQuestion
  canMoveUp: boolean
  canMoveDown: boolean
  ferTypeOptions: FerType[]
  readOnly?: boolean
}>()

const emit = defineEmits<{
  moveUp: []
  moveDown: []
  hide: []
  unhide: []
  split: []
  delete: []
  updateText: [lang: string, value: string]
  updateHelp: [lang: string, value: string]
  updatePrinciple: [value: string | null]
  updateScope: [value: 'metadata' | 'data' | null]
  updateFerType: [value: string | null]
  updateRequired: [value: boolean]
  updateAllowMultiple: [value: boolean]
  addSuggested: [ferId: string]
  removeSuggested: [ferId: string]
  moveSuggested: [ferId: string, direction: MoveDirection]
  addInlineFer: [fer: InlineFer]
  updateAllowFreeText: [value: boolean]
  addPhrase: []
  removePhrase: [index: number]
  movePhrase: [index: number, direction: MoveDirection]
  updatePhraseText: [index: number, lang: string, value: string]
}>()

const { locale, t } = useI18n()
// Read-only lookups this card needs to *resolve* (inlineFers labels, the
// cached catalogue) — mutations still flow up through the emits above and
// KmSectionList.vue's `applyOp`, matching every other field on this card.
const store = useKmEditorStore()
const content = computed(() => store.content)
const fers = computed(() => store.fers)

const alreadySplit = computed(
  () => props.question.id.endsWith('-metadata') || props.question.id.endsWith('-data')
)

function ferTypeLabel(type: FerType): string {
  return resolveLang(type.label, locale.value) ?? type.key
}

function onPrincipleChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  emit('updatePrinciple', value === '' ? null : value)
}

function onScopeChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  emit('updateScope', value === '' ? null : (value as 'metadata' | 'data'))
}

function onFerTypeChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  emit('updateFerType', value === '' ? null : value)
}

function onRequiredChange(event: Event) {
  emit('updateRequired', (event.target as HTMLInputElement).checked)
}

function onAllowMultipleChange(event: Event) {
  emit('updateAllowMultiple', (event.target as HTMLInputElement).checked)
}

function onDelete() {
  if (!confirm(t('km.deleteQuestionConfirm'))) return
  emit('delete')
}
</script>

<style scoped>
.km-question-card {
  padding: 1rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  background-color: var(--color-background);
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.km-question-card.hidden {
  opacity: 0.65;
  background-color: var(--color-hover);
}

.question-head {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  flex-wrap: wrap;
  justify-content: space-between;
}

.question-id {
  font-family: monospace;
  font-size: var(--font-size-xs);
  color: var(--color-id-chip-text);
  background-color: var(--color-id-chip-bg);
  padding: 0.15rem 0.4rem;
  border-radius: var(--border-radius-sm);
  align-self: flex-start;
}

.hidden-chip {
  font-size: var(--font-size-xs);
  color: #ffffff;
  background-color: var(--color-status-planned);
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  align-self: flex-start;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
  margin-left: auto;
}

.ghost-btn {
  min-height: 44px;
  padding: 0.3rem 0.7rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.ghost-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.ghost-btn.danger {
  color: var(--color-error);
  border-color: var(--color-error);
}

.hidden-hint {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.field-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
}

.controls-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: 0.75rem;
  align-items: end;
}

.control {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: var(--font-size-sm);
}

.control select {
  min-height: 44px;
  padding: 0.4rem 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
}

.control.checkbox {
  flex-direction: row;
  align-items: center;
  gap: 0.5rem;
}

.control.checkbox input {
  width: 1.25rem;
  height: 1.25rem;
}

@media (max-width: 480px) {
  .controls-grid {
    grid-template-columns: 1fr;
  }
}
</style>
