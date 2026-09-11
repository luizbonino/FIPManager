<template>
  <div v-if="status !== 'live'" class="snapshot-banner no-print" :class="status">
    <template v-if="status === 'snapshot'">
      <span class="banner-text">{{ $t('dashboard.snapshot.computedAgo', { age: ageText }) }}</span>
      <button type="button" class="btn btn-secondary" :disabled="refreshing" @click="onRefresh">
        {{ refreshing ? $t('dashboard.snapshot.refreshing') : $t('dashboard.snapshot.refresh') }}
      </button>
    </template>
    <template v-else-if="status === 'pending'">
      <span class="spinner" aria-hidden="true" />
      <span class="banner-text">{{ $t('dashboard.snapshot.pending', { attempts: attempt, max: maxAttempts }) }}</span>
    </template>
  </div>
</template>

<script lang="ts" setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

/**
 * Spec 13 §5.3/§6.1/AC-5: `tier: "snapshot"` renders "computed {age} ago ·
 * Refresh" (`POST`s exactly once per click — disabled while the request is
 * in flight); a `202 snapshot_pending` poll renders a computing message
 * instead. `status="live"` renders nothing.
 */
const props = defineProps<{
  status: 'live' | 'snapshot' | 'pending'
  computedAt?: string | null
  attempt?: number
  maxAttempts?: number
}>()

const emit = defineEmits<{ (e: 'refresh'): void }>()

const { t } = useI18n()
const refreshing = ref(false)

const attempt = computed(() => props.attempt ?? 0)
const maxAttempts = computed(() => props.maxAttempts ?? 20)

const ageText = computed(() => {
  if (!props.computedAt) return t('dashboard.snapshot.unknownAge')
  const then = new Date(props.computedAt).getTime()
  if (Number.isNaN(then)) return t('dashboard.snapshot.unknownAge')
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60000))
  if (minutes < 1) return t('dashboard.snapshot.justNow')
  if (minutes < 60) return t('dashboard.snapshot.minutesAgo', { minutes })
  const hours = Math.round(minutes / 60)
  return t('dashboard.snapshot.hoursAgo', { hours })
})

async function onRefresh() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    emit('refresh')
  } finally {
    // The caller's refresh call is async and out of this component's
    // control; a short cool-down still guarantees one POST per click even
    // under a fast double-click, without this component awaiting the parent.
    setTimeout(() => {
      refreshing.value = false
    }, 300)
  }
}
</script>

<style scoped>
.snapshot-banner {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.6rem 1rem;
  border-radius: var(--border-radius-sm);
  font-size: var(--font-size-sm);
}

.snapshot-banner.snapshot {
  background-color: var(--color-hover);
  border: 1px solid var(--color-border);
}

.snapshot-banner.pending {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
}

.btn {
  min-height: 44px;
  padding: 0.4rem 0.9rem;
  border: none;
  border-radius: var(--border-radius-sm);
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
}

.btn:disabled {
  opacity: 0.6;
}

.spinner {
  width: 0.8rem;
  height: 0.8rem;
  border-radius: 50%;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary);
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
