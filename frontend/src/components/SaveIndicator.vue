<template>
  <div class="save-indicator" :class="`state-${state}`" role="status">
    <span class="dot" aria-hidden="true" />
    <span class="text">
      <template v-if="state === 'saved'">{{ $t('save.saved', { time: savedTimeLabel }) }}</template>
      <template v-else-if="state === 'saving'">{{ $t('save.saving') }}</template>
      <template v-else-if="state === 'unsaved'">{{ $t('save.unsaved') }}</template>
      <template v-else-if="state === 'conflict'">{{ $t('save.conflict') }}</template>
      <template v-else-if="errorKind === 'invalid'">{{ $t('save.invalid', { code: errorDetail }) }}</template>
      <template v-else>{{ retriesExhausted ? $t('save.failed') : $t('save.error') }}</template>
    </span>
    <button v-if="state === 'error' && retriesExhausted" type="button" class="retry-btn" @click="$emit('retry')">
      {{ $t('save.retry') }}
    </button>
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import type { SaveState } from '@/stores/kmEditor'

/**
 * Always-visible save state (spec 02 §2.3): `saved | unsaved | saving |
 * error`, plus `kmEditor`'s `conflict` (a 409: someone else's edit landed
 * first — Reload, not Retry, is the way out). `kmEditor`'s `SaveState` is
 * a superset of `fipEditor`'s, so either store's `saveState` is assignable
 * here. `retriesExhausted` distinguishes the auto-retrying "Not saved —
 * retrying" message from the terminal "Not saved" + manual Retry button.
 */
const props = defineProps<{
  state: SaveState
  lastSavedAt: Date | null
  retriesExhausted?: boolean
  /** `fipEditor`'s `lastError` (spec 02 §2.3): `'invalid'` picks the "check your entries" message over the generic retry one. */
  errorKind?: string | null
  /** The backend `detail` code behind an `errorKind === 'invalid'`, interpolated into `save.invalid`. */
  errorDetail?: string | null
}>()

defineEmits<{ retry: [] }>()

const savedTimeLabel = computed(() => {
  if (!props.lastSavedAt) return ''
  return props.lastSavedAt.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
})
</script>

<style scoped>
.save-indicator {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: var(--font-size-sm);
  white-space: nowrap;
}

.dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background-color: var(--color-text-secondary);
  flex-shrink: 0;
}

.state-saved .dot {
  background-color: var(--color-success);
}

.state-saving .dot {
  background-color: var(--color-primary);
  animation: pulse 1s ease-in-out infinite;
}

.state-unsaved .dot {
  background-color: var(--color-status-planned);
}

.state-error .dot,
.state-conflict .dot {
  background-color: var(--color-error);
}

.retry-btn {
  padding: 0.2rem 0.6rem;
  min-height: 44px;
  border: 1px solid var(--color-error);
  border-radius: var(--border-radius-sm);
  background: none;
  color: var(--color-error);
  font-size: var(--font-size-sm);
}

@media (prefers-reduced-motion: no-preference) {
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }
}
</style>
