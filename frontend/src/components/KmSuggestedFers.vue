<template>
  <div class="km-suggested-fers">
    <div class="field-label-row">
      <span class="field-label">{{ $t('km.suggestedOptions') }}</span>
      <span class="suggested-count">{{ suggestedFerIds.length }}/{{ MAX_SUGGESTED_FERS }}</span>
    </div>

    <ul v-if="suggestedFerIds.length > 0" class="suggested-chip-list">
      <li v-for="(ferId, index) in suggestedFerIds" :key="ferId" class="suggested-chip">
        <span class="chip-label">{{ labelOf(ferId) }}</span>
        <span class="chip-type">{{ typeOf(ferId) }}</span>
        <MoveButtons
          :can-up="!readOnly && index > 0"
          :can-down="!readOnly && index < suggestedFerIds.length - 1"
          @up="$emit('move', ferId, 'up')"
          @down="$emit('move', ferId, 'down')"
        />
        <button type="button" class="chip-remove" :disabled="readOnly" @click="$emit('remove', ferId)">
          <span aria-hidden="true">&times;</span>
          <span class="sr-only">{{ $t('km.removeSuggested') }}</span>
        </button>
      </li>
    </ul>

    <div class="add-from-catalogue">
      <label class="search-field">
        <span class="sr-only">{{ $t('editor.searchFer') }}</span>
        <input v-model="query" type="text" :placeholder="$t('editor.searchFer')" :disabled="readOnly" />
      </label>
      <label class="show-all-types">
        <input v-model="showAllTypes" type="checkbox" :disabled="readOnly || !ferType" />
        <span>{{ $t('km.showAllTypes') }}</span>
      </label>
      <ul v-if="query.trim() && searchResults.length > 0" class="search-results">
        <li v-for="opt in searchResults" :key="opt.id">
          <button
            type="button"
            class="search-result-btn"
            :disabled="readOnly || suggestedFerIds.includes(opt.id) || suggestedFerIds.length >= MAX_SUGGESTED_FERS"
            @click="onAddFromCatalogue(opt.id)"
          >
            {{ labelOf(opt.id) }} <span class="chip-type">{{ opt.type }}</span>
          </button>
        </li>
      </ul>
      <p v-else-if="query.trim()" class="no-match">{{ $t('editor.noFerMatch') }}</p>
    </div>

    <details class="add-inline-fer">
      <summary>{{ $t('km.addInlineFer') }}</summary>
      <div class="inline-fer-form">
        <label class="inline-field">
          <span>{{ $t('km.inlineFerId') }}</span>
          <input v-model="newFerId" type="text" placeholder="https://fipm.example.org/fers/draft/…" :disabled="readOnly" />
        </label>
        <div class="inline-field">
          <span>{{ $t('km.inlineFerLabel') }}</span>
          <KmLangTabs :model-value="newFerLabel" :default-lang="locale" :disabled="readOnly" @change="onLabelChange" />
        </div>
        <label class="inline-field">
          <span>{{ $t('km.ferType') }}</span>
          <select v-model="newFerType" :disabled="readOnly">
            <option v-for="type in ferTypeOptions" :key="type.key" :value="type.key">{{ ferTypeLabelOf(type) }}</option>
          </select>
        </label>
        <label class="inline-field">
          <span>{{ $t('km.inlineFerHomepage') }}</span>
          <input v-model="newFerHomepage" type="text" placeholder="https://…" :disabled="readOnly" />
        </label>
        <button type="button" class="btn btn-secondary" :disabled="readOnly || !canAddInline" @click="onAddInline">
          {{ $t('km.addInlineFer') }}
        </button>
      </div>
    </details>

    <label class="allow-free-text">
      <input
        type="checkbox"
        :checked="allowFreeText"
        :disabled="readOnly"
        @change="$emit('updateAllowFreeText', ($event.target as HTMLInputElement).checked)"
      />
      <span>{{ $t('km.allowFreeText') }}</span>
    </label>
  </div>
</template>

<script lang="ts" setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { resolveLang } from '@/lib/lang'
import { MAX_SUGGESTED_FERS, resolveSuggestedFer, type MoveDirection } from '@/lib/kmContent'
import MoveButtons from './MoveButtons.vue'
import KmLangTabs from './KmLangTabs.vue'
import type { FerOut, FerType, InlineFer, KnowledgeModelContent, LangMap } from '@/types/api'

/**
 * The "Suggested options" block under a question's FER-type row (spec 08
 * §1.4): current suggestions as reorderable chips with a counter, a
 * client-filtered search over the cached catalogue (`fers`, the same
 * whole-catalogue prefetch `fipEditor`'s `FerPicker` already relies on —
 * simpler than a live per-keystroke endpoint call and consistent with the
 * rest of the app) with a "show all types" escape hatch, an "Add inline
 * FER" sub-form, and the `allowFreeText` checkbox.
 */
const props = defineProps<{
  content: KnowledgeModelContent
  questionId: string
  ferType: string | null
  suggestedFerIds: string[]
  fers: Record<string, FerOut>
  ferTypeOptions: FerType[]
  allowFreeText: boolean
  readOnly?: boolean
}>()

const emit = defineEmits<{
  add: [ferId: string]
  remove: [ferId: string]
  move: [ferId: string, direction: MoveDirection]
  addInline: [fer: InlineFer]
  updateAllowFreeText: [value: boolean]
}>()

const { locale } = useI18n()

function labelOf(ferId: string): string {
  const resolved = resolveSuggestedFer(ferId, props.content, props.fers)
  return (resolved && resolveLang(resolved.label, locale.value)) || ferId
}

function typeOf(ferId: string): string {
  const resolved = resolveSuggestedFer(ferId, props.content, props.fers)
  return resolved?.type ?? ''
}

function ferTypeLabelOf(type: FerType): string {
  return resolveLang(type.label, locale.value) ?? type.key
}

const query = ref('')
const showAllTypes = ref(false)

const searchResults = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return []
  const pool = Object.values(props.fers).filter((f) => showAllTypes.value || !props.ferType || f.type === props.ferType)
  return pool.filter((f) => (resolveLang(f.label, locale.value) ?? f.id).toLowerCase().includes(q)).slice(0, 20)
})

function onAddFromCatalogue(ferId: string) {
  emit('add', ferId)
  query.value = ''
}

const newFerId = ref('')
const newFerLabel = ref<LangMap>({})
const newFerType = ref(props.ferType ?? props.ferTypeOptions[0]?.key ?? '')
const newFerHomepage = ref('')

function onLabelChange(lang: string, value: string) {
  const next = { ...newFerLabel.value }
  if (value === '') delete next[lang]
  else next[lang] = value
  newFerLabel.value = next
}

const canAddInline = computed(
  () => newFerId.value.trim() !== '' && Object.values(newFerLabel.value).some((v) => v.trim() !== '') && newFerType.value !== ''
)

function onAddInline() {
  if (!canAddInline.value) return
  emit('addInline', {
    id: newFerId.value.trim(),
    label: { ...newFerLabel.value },
    type: newFerType.value,
    homepage: newFerHomepage.value.trim() || null,
  })
  newFerId.value = ''
  newFerLabel.value = {}
  newFerHomepage.value = ''
}

</script>

<style scoped>
.km-suggested-fers {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-hover);
}

.field-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.field-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
}

.suggested-count {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.suggested-chip-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.suggested-chip {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  flex-wrap: wrap;
}

.chip-label {
  font-size: var(--font-size-sm);
  flex: 1;
  min-width: 8rem;
}

.chip-type {
  font-size: var(--font-size-xs);
  color: var(--color-chip-text);
  background-color: var(--color-chip-bg);
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
}

.chip-remove {
  min-width: 44px;
  min-height: 44px;
  border: 1px solid var(--color-error);
  border-radius: var(--border-radius-sm);
  background: none;
  color: var(--color-error);
  font-size: 1.1rem;
}

.add-from-catalogue {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.search-field input {
  width: 100%;
  min-height: 44px;
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
  font-size: var(--font-size-sm);
}

.show-all-types {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  min-height: 44px;
}

.search-results {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  max-height: 12rem;
  overflow-y: auto;
}

.search-result-btn {
  width: 100%;
  min-height: 44px;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.3rem 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  text-align: left;
  font-size: var(--font-size-sm);
}

.search-result-btn:disabled {
  opacity: 0.5;
}

.no-match {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.add-inline-fer summary {
  cursor: pointer;
  min-height: 44px;
  display: flex;
  align-items: center;
  font-size: var(--font-size-sm);
  color: var(--color-link);
}

.inline-fer-form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding-top: 0.5rem;
}

.inline-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: var(--font-size-sm);
}

.inline-field input,
.inline-field select {
  min-height: 44px;
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
}

.allow-free-text {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-size: var(--font-size-sm);
  min-height: 44px;
}

.btn {
  min-height: 44px;
  padding: 0.4rem 1rem;
  border: none;
  border-radius: var(--border-radius-sm);
  font-size: var(--font-size-sm);
  cursor: pointer;
  align-self: flex-start;
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
