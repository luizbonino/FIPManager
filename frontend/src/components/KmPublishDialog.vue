<template>
  <div v-if="open" class="km-publish-overlay" role="presentation" @click.self="$emit('close')">
    <div class="km-publish-dialog" role="dialog" aria-modal="true" :aria-label="$t('km.publishTitle', { version })">
      <h2>{{ $t('km.publishTitle', { version }) }}</h2>

      <KmValidationList :errors="errors" />

      <label class="field">
        <span>{{ $t('km.changelog') }} *</span>
        <textarea v-model="notes" rows="3" :placeholder="$t('km.changelogRequired')" />
      </label>

      <p class="hint">{{ $t('km.publishHint') }}</p>

      <div class="actions">
        <button type="button" class="btn btn-secondary" @click="$emit('close')">{{ $t('common.cancel') }}</button>
        <button
          type="button"
          class="btn btn-primary"
          :disabled="notes.trim() === '' || publishing"
          @click="$emit('publish', notes.trim())"
        >
          {{ $t('km.publish') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, watch } from 'vue'
import KmValidationList from './KmValidationList.vue'
import type { ContentError } from '@/lib/kmContent'

/**
 * Publish confirmation (spec 04 §5): read-only target version, a required
 * changelog `notes` textarea (Publish disabled while empty), the current
 * validation summary and the "publishing freezes this version" reminder.
 */
const props = defineProps<{
  open: boolean
  version: string
  errors: ContentError[]
  publishing?: boolean
}>()

defineEmits<{ publish: [notes: string]; close: [] }>()

const notes = ref('')

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) notes.value = ''
  }
)
</script>

<style scoped>
.km-publish-overlay {
  position: fixed;
  inset: 0;
  background-color: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 1rem;
}

.km-publish-dialog {
  background-color: var(--color-background);
  border-radius: var(--border-radius-md);
  padding: 1.5rem;
  max-width: 32rem;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-height: 90vh;
  overflow-y: auto;
}

.km-publish-dialog h2 {
  margin: 0;
  font-size: 1.2rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.field textarea {
  padding: 0.6rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  font-family: inherit;
  font-size: 1rem;
  resize: vertical;
}

.hint {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.btn {
  min-height: 44px;
  padding: 0.6rem 1.2rem;
  border: none;
  border-radius: var(--border-radius-sm);
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
}

.btn-primary {
  background-color: var(--color-primary);
  color: var(--color-primary-text);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
}
</style>
