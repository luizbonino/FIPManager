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
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import { useFipEditorStore } from '@/stores/fipEditor'
import { resolveLang } from '@/lib/lang'
import FerPicker from './FerPicker.vue'
import StatusSelect from './StatusSelect.vue'
import type { Declaration, DeclarationStatus, FerOut } from '@/types/api'

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

@media (min-width: 640px) {
  .declaration-editor {
    grid-template-columns: 2fr 1fr 1fr auto;
    align-items: start;
  }
}
</style>
