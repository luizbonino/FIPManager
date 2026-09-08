<template>
  <label class="visibility-select">
    <span>{{ $t('visibility.label') }}</span>
    <select :value="modelValue" :disabled="disabled" @change="onChange">
      <option value="private">{{ $t('visibility.private') }}</option>
      <option value="link">{{ $t('visibility.link') }}</option>
      <option value="public">{{ $t('visibility.public') }}</option>
    </select>
  </label>
</template>

<script lang="ts" setup>
import type { Visibility } from '@/types/api'

/** Owner-only; PATCHes immediately, not debounced (spec 02 §3). */
defineProps<{ modelValue: Visibility; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [Visibility] }>()

function onChange(event: Event) {
  emit('update:modelValue', (event.target as HTMLSelectElement).value as Visibility)
}
</script>

<style scoped>
.visibility-select {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: var(--font-size-sm);
}

.visibility-select select {
  min-height: 44px;
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
}
</style>
