<template>
  <div class="km-validation-list">
    <p v-if="errors.length === 0" class="valid-msg">{{ $t('km.valid') }}</p>
    <template v-else>
      <p class="invalid-msg">{{ $t('km.invalid', { count: errors.length }) }}</p>
      <ul class="error-list">
        <li v-for="(error, index) in errors" :key="index" class="error-item">
          <code class="error-path">{{ error.path }}</code>
          <span class="error-code">{{ error.code }}</span>
          <span class="error-message">{{ error.message }}</span>
        </li>
      </ul>
    </template>
  </div>
</template>

<script lang="ts" setup>
import type { ContentError } from '@/lib/kmContent'

/** Renders `validateContent`'s output (spec 04 §3.3/§5) as a flat, scannable list. */
defineProps<{ errors: ContentError[] }>()
</script>

<style scoped>
.km-validation-list {
  font-size: var(--font-size-sm);
}

.valid-msg {
  color: var(--color-success);
  margin: 0;
}

.invalid-msg {
  color: var(--color-error);
  font-weight: var(--font-weight-medium);
  margin: 0 0 0.5rem;
}

.error-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  max-height: 16rem;
  overflow-y: auto;
}

.error-item {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  align-items: baseline;
  padding: 0.35rem 0.5rem;
  border: 1px solid var(--color-error);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-error-bg);
}

.error-path {
  font-family: monospace;
  font-size: var(--font-size-xs);
  color: var(--color-id-chip-text);
  background-color: var(--color-id-chip-bg);
  padding: 0.1rem 0.35rem;
  border-radius: var(--border-radius-sm);
}

.error-code {
  font-weight: var(--font-weight-medium);
  color: var(--color-error);
}

.error-message {
  color: var(--color-text-secondary);
}
</style>
