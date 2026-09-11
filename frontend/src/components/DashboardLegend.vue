<template>
  <div class="dashboard-legend">
    <h2 class="legend-title">{{ $t('dashboard.legend.title') }}</h2>
    <ul class="legend-states">
      <li v-for="state in states" :key="state" class="legend-item">
        <span class="swatch" :class="`state-${state}`" aria-hidden="true" />
        {{ $t(`dashboard.cellState.${state}`) }}
      </li>
    </ul>
    <p class="legend-hint">{{ $t('dashboard.legend.colourHint') }}</p>
  </div>
</template>

<script lang="ts" setup>
import { CELL_STATE_ORDER } from '@/lib/dashboard'

/**
 * The six `cell_state` values with colour and label (spec 13 §1.3), reusing
 * `matrix.ts`'s `--color-status-*` vocabulary (builder brief C's read-first
 * list: do not fork `MatrixLegend.vue`, reuse its colour variables). Always
 * printed — never carries `.no-print` (spec 13 AC-7/AC-8).
 */
const states = CELL_STATE_ORDER
</script>

<style scoped>
.dashboard-legend {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  padding: 0.75rem 1rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  background-color: var(--color-hover);
  font-size: var(--font-size-xs);
}

.legend-title {
  margin: 0;
  font-size: var(--font-size-sm);
}

.legend-states {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem 1rem;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}

.swatch {
  display: inline-block;
  width: 0.9rem;
  height: 0.9rem;
  border-radius: 50%;
}

.swatch.state-current { background-color: var(--color-status-current); }
.swatch.state-planned { background-color: var(--color-status-planned); }
.swatch.state-none { background-color: var(--color-status-none); }
.swatch.state-notApplicable { background-color: var(--color-status-not-applicable); }
.swatch.state-unanswered {
  background-color: #f3f4f6;
  border: 1px dashed #9ca3af;
}
.swatch.state-absent {
  background-image: repeating-linear-gradient(45deg, #e5e7eb, #e5e7eb 3px, #f3f4f6 3px, #f3f4f6 6px);
  border: 1px solid #9ca3af;
}

.legend-hint {
  margin: 0;
  color: var(--color-text-secondary);
}
</style>
