<template>
  <div class="session-fip-list">
    <p v-if="reconnecting" class="reconnecting no-print">
      <span class="dot" aria-hidden="true" />
      {{ $t('sessionAdmin.reconnecting') }}
    </p>
    <p v-if="sorted.length === 0" class="empty-state">{{ $t('sessionAdmin.noFips') }}</p>
    <ul v-else class="fip-rows">
      <li v-for="fip in sorted" :key="fip.id" class="fip-row">
        <div class="fip-row-main">
          <span class="fip-name">{{ displayName(fip) }}</span>
          <span class="visibility-chip">{{ $t(`visibility.${fip.visibility}`) }}</span>
        </div>
        <ProgressBar :answered="answeredCount(fip.answers)" :total="21" />
        <span class="updated">{{ $t('sessionAdmin.lastUpdate') }}: {{ relativeTime(fip.updatedAt) }}</span>
        <router-link :to="`/fips/${fip.id}`" class="view-link">{{ $t('common.view') }}</router-link>
      </li>
    </ul>
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { answeredCount } from '@/lib/progress'
import ProgressBar from './ProgressBar.vue'
import type { FipOut } from '@/types/api'

const { locale } = useI18n()

/**
 * `GET /api/sessions/{id}/fips` rendering (spec 02 §4.2): display name,
 * `answered / 21` bar, `updatedAt` as relative time, visibility, View link;
 * sorted by `createdAt`.
 */
const props = defineProps<{ fips: FipOut[]; reconnecting?: boolean }>()

const sorted = computed(() => [...props.fips].sort((a, b) => a.createdAt.localeCompare(b.createdAt)))

function displayName(fip: FipOut): string {
  return fip.community?.name || fip.id
}

// `Intl.RelativeTimeFormat` covers localisation natively for en/pt-PT/pt-BR
// (spec 02 §4.2's "relative time"), so no extra i18n strings are needed.
function relativeTime(iso: string): string {
  const diffMs = new Date(iso).getTime() - Date.now()
  const rtf = new Intl.RelativeTimeFormat(locale.value, { numeric: 'auto' })
  const diffMin = Math.round(diffMs / 60000)
  if (Math.abs(diffMin) < 60) return rtf.format(diffMin, 'minute')
  const diffH = Math.round(diffMin / 60)
  if (Math.abs(diffH) < 24) return rtf.format(diffH, 'hour')
  const diffD = Math.round(diffH / 24)
  return rtf.format(diffD, 'day')
}
</script>

<style scoped>
.reconnecting {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.reconnecting .dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background-color: var(--color-status-planned);
}

.empty-state {
  color: var(--color-text-secondary);
  padding: 1rem 0;
}

.fip-rows {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.fip-row {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.4rem;
  padding: 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  align-items: center;
}

.fip-row-main {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.fip-name {
  font-weight: var(--font-weight-medium);
}

.visibility-chip {
  font-size: var(--font-size-xs);
  color: var(--color-chip-text);
  background-color: var(--color-chip-bg);
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
}

.updated {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.view-link {
  align-self: start;
  min-height: 44px;
  display: inline-flex;
  align-items: center;
}

@media (min-width: 640px) {
  .fip-row {
    grid-template-columns: 2fr 1fr auto auto;
  }
}
</style>
