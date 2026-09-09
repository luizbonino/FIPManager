<template>
  <div class="matrix-legend">
    <h2 class="legend-title">{{ $t('matrix.legend') }}</h2>
    <ul class="legend-states">
      <li v-for="status in statuses" :key="status" class="legend-item">
        <span class="swatch" :class="`status-${status}`" aria-hidden="true" />
        {{ $t(`declarationStatus.${statusKey(status)}`) }}
      </li>
      <li class="legend-item">
        <span class="swatch status-unanswered" aria-hidden="true" />
        {{ $t('matrix.unanswered') }}
      </li>
      <li class="legend-item">
        <span class="swatch status-not-applicable" aria-hidden="true" />
        {{ $t('matrix.notApplicableFull') }}
      </li>
      <li class="legend-item">
        <span class="swatch status-absent" aria-hidden="true" />
        {{ $t('matrix.absent') }}
      </li>
    </ul>
    <ul class="legend-scopes">
      <li class="legend-item"><span class="scope-badge">{{ $t('matrix.scopeMetadata') }}</span></li>
      <li class="legend-item"><span class="scope-badge">{{ $t('matrix.scopeData') }}</span></li>
    </ul>
    <p class="legend-convergence">{{ $t('matrix.convergence') }}: {{ $t('matrix.convergenceHint') }}</p>
  </div>
</template>

<script lang="ts" setup>
import type { DeclarationStatus } from '@/types/api'

/**
 * The six cell states with colours and labels, the two scope badges and
 * the convergence-number explanation (spec 03 §1.3). Always printed —
 * never carries `.no-print`.
 */
const statuses: DeclarationStatus[] = ['current', 'planned', 'planned-development', 'planned-replacement', 'none']

const STATUS_KEYS: Record<DeclarationStatus, string> = {
  current: 'current',
  planned: 'planned',
  'planned-development': 'plannedDevelopment',
  'planned-replacement': 'plannedReplacement',
  none: 'none',
}

function statusKey(status: DeclarationStatus): string {
  return STATUS_KEYS[status]
}
</script>

<style scoped>
.matrix-legend {
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

.legend-states,
.legend-scopes {
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

.swatch.status-current { background-color: var(--color-status-current); }
.swatch.status-planned { background-color: var(--color-status-planned); }
.swatch.status-planned-development { background-color: var(--color-status-planned-development); }
.swatch.status-planned-replacement { background-color: var(--color-status-planned-replacement); }
.swatch.status-none { background-color: var(--color-status-none); }
.swatch.status-unanswered {
  background-color: #f3f4f6;
  border: 1px dashed #9ca3af;
}
.swatch.status-not-applicable { background-color: var(--color-status-not-applicable); }
.swatch.status-absent {
  background-image: repeating-linear-gradient(45deg, #e5e7eb, #e5e7eb 3px, #f3f4f6 3px, #f3f4f6 6px);
  border: 1px solid #9ca3af;
}

.scope-badge {
  font-size: var(--font-size-xs);
  color: var(--color-chip-text);
  background-color: var(--color-chip-bg);
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
}

.legend-convergence {
  margin: 0;
  color: var(--color-text-secondary);
}
</style>
