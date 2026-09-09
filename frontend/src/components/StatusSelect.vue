<template>
  <div class="status-select">
    <select
      :id="id"
      :value="modelValue"
      :disabled="disabled"
      class="status-select-input"
      @change="onChange"
    >
      <option v-for="s in STATUSES" :key="s" :value="s">{{ $t(`declarationStatus.${STATUS_KEYS[s]}`) }}</option>
    </select>
  </div>
</template>

<script lang="ts" setup>
import type { DeclarationStatus } from '@/types/api'

/** Native `<select>`, the five statuses (spec 02 §2.2), default `current`. */
defineProps<{ modelValue: DeclarationStatus; disabled?: boolean; id?: string }>()
const emit = defineEmits<{ 'update:modelValue': [DeclarationStatus] }>()

const STATUSES: DeclarationStatus[] = ['current', 'planned', 'planned-development', 'planned-replacement', 'none']

const STATUS_KEYS: Record<DeclarationStatus, string> = {
  current: 'current',
  planned: 'planned',
  'planned-development': 'plannedDevelopment',
  'planned-replacement': 'plannedReplacement',
  none: 'none',
}

function onChange(event: Event) {
  emit('update:modelValue', (event.target as HTMLSelectElement).value as DeclarationStatus)
}
</script>

<style scoped>
.status-select-input {
  min-height: 44px;
  padding: 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
  font-size: var(--font-size-md);
  width: 100%;
}
</style>
