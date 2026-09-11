<template>
  <div class="heat-map-scroll">
    <div class="heat-map" :style="gridStyle" role="table" :aria-label="$t('dashboard.coverage.heatMapLabel')">
      <div class="hm-cell hm-corner" role="columnheader" />
      <div v-for="state in states" :key="`h-${state}`" class="hm-cell hm-col-header" role="columnheader">
        {{ $t(`dashboard.cellState.${state}`) }}
      </div>
      <template v-for="row in rows" :key="row.key">
        <div class="hm-cell hm-row-header" role="rowheader">{{ row.key }}</div>
        <div
          v-for="state in states"
          :key="`${row.key}-${state}`"
          class="hm-cell hm-value"
          role="cell"
          :style="{ backgroundColor: fillFor(row, state) }"
          :aria-label="cellAriaLabel(row, state)"
        >
          <span class="hm-number">{{ formatCount(row.counts[state]) }}</span>
          <span class="hm-share">{{ formatShare(row.shares[state]) }}</span>
        </div>
      </template>
    </div>
    <p v-if="rows.length === 0" class="hm-empty">{{ $t('dashboard.coverage.noRows') }}</p>
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { CELL_STATE_ORDER, formatCount, formatShare, type CellStateKey } from '@/lib/dashboard'
import type { CoverageCounts, CoverageRow } from '@/types/dashboard'

/**
 * Spec 13 §6.2: rows are principle codes (or questions/groups), columns
 * are the six `cell_state`s — ≤126 cells whether the population is 40 FIPs
 * or 100 000, never a per-FIP column. Hand-rolled CSS grid (no chart
 * library, spec 13 read-first §6 "hand-rolled SVG or CSS grid"). Colour is
 * never the only signal (spec 02 §4.3): every cell carries its count, its
 * share and an `aria-label` (spec 13 AC-7).
 */
defineProps<{ rows: CoverageRow[] }>()

const { t } = useI18n()

const states = CELL_STATE_ORDER

// `unanswered`/`absent` have no `--color-status-*` variable (matrix.ts's
// hatched/dashed idioms are ink-based, not fills); fixed neutrals here
// match `MatrixCell.vue`'s `.status-unanswered`/`.status-absent` palette.
const STATE_COLOR: Record<CellStateKey, string> = {
  current: 'var(--color-status-current)',
  planned: 'var(--color-status-planned)',
  none: 'var(--color-status-none)',
  notApplicable: 'var(--color-status-not-applicable)',
  unanswered: '#9ca3af',
  absent: '#d1d5db',
}

const gridStyle = computed(() => ({
  gridTemplateColumns: `minmax(6rem, auto) repeat(${states.length}, minmax(5.5rem, 1fr))`,
}))

function fillFor(row: CoverageRow, state: CellStateKey): string {
  const share = row.shares[state] ?? 0
  const color = STATE_COLOR[state]
  // Diverging fill: share drives the mix ratio against a neutral base so an
  // empty cell (share 0) reads as blank, not as a coloured "zero".
  const pct = Math.round(Math.min(1, Math.max(0, share)) * 85) + (share > 0 ? 15 : 0)
  return `color-mix(in srgb, ${color} ${pct}%, var(--color-background) ${100 - pct}%)`
}

function cellAriaLabel(row: CoverageRow, state: CellStateKey): string {
  const count = row.counts[state as keyof CoverageCounts] ?? 0
  const share = row.shares[state as keyof CoverageCounts] ?? 0
  return t('dashboard.coverage.cellAriaLabel', {
    row: row.key,
    state: t(`dashboard.cellState.${state}`),
    count: formatCount(count),
    share: formatShare(share),
  })
}
</script>

<style scoped>
.heat-map-scroll {
  overflow-x: auto;
}

.heat-map {
  display: grid;
  gap: 2px;
  min-width: 40rem;
}

.hm-cell {
  padding: 0.4rem 0.5rem;
  font-size: var(--font-size-xs);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
}

.hm-corner {
  background: transparent;
}

.hm-col-header,
.hm-row-header {
  font-weight: var(--font-weight-bold);
  background-color: var(--color-hover);
}

.hm-row-header {
  position: sticky;
  left: 0;
  z-index: 1;
}

.hm-value {
  border-radius: var(--border-radius-sm);
  align-items: center;
}

.hm-number {
  font-weight: var(--font-weight-bold);
}

.hm-share {
  color: var(--color-text-secondary);
}

.hm-empty {
  padding: 1rem;
  color: var(--color-text-secondary);
}
</style>
