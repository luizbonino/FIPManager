<template>
  <div class="convergence-list">
    <table class="convergence-table">
      <thead>
        <tr>
          <th scope="col">{{ $t('dashboard.similarity.colQuestion') }}</th>
          <th scope="col">{{ $t('dashboard.similarity.colDeclaring') }}</th>
          <th scope="col">{{ $t('dashboard.similarity.colDistinct') }}</th>
          <th scope="col">{{ $t('dashboard.similarity.colNotApplicable') }}</th>
          <th scope="col">{{ $t('dashboard.similarity.colTop') }}</th>
          <th scope="col">{{ $t('dashboard.similarity.colAgreed') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.questionId">
          <td>{{ row.questionId }}</td>
          <td>{{ row.declaringFips }}</td>
          <td>{{ row.distinctCurrent }}</td>
          <td>{{ row.notApplicableFips }}</td>
          <td>
            <template v-if="row.topLabel">
              <span :class="{ 'free-text-key': formatConvergenceKey(row.topLabel).isFreeText }">{{ formatConvergenceKey(row.topLabel).text }}</span>
              <span v-if="formatConvergenceKey(row.topLabel).isFreeText" class="free-text-tag">({{ $t('dashboard.similarity.freeText') }})</span>
              <span class="cv-top-count">&times;{{ row.topCount }}</span>
            </template>
          </td>
          <td>
            <span v-if="row.agreed" class="cv-agreed" :title="$t('dashboard.similarity.agreed')">
              &#10003;
              <span class="sr-only">{{ $t('dashboard.similarity.agreed') }}</span>
            </span>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="rows.length === 0" class="empty-hint">{{ $t('dashboard.similarity.noConvergence') }}</p>
  </div>
</template>

<script lang="ts" setup>
import { formatConvergenceKey } from '@/lib/dashboard'
import type { ConvergenceRow } from '@/types/dashboard'

/**
 * Spec 13 §3.3.1/§11.3 amendment: `MapData.convergence`, one row per
 * question — declaring/distinct/not-applicable counts and the most common
 * key, agreement flagged. `topLabel`/`topKey` are raw convergence keys, not
 * resolved names (§11.3 amendment) — rendered through `formatConvergenceKey`,
 * same as `NeighbourList.vue`'s `topShared`.
 */
defineProps<{ rows: ConvergenceRow[] }>()
</script>

<style scoped>
.convergence-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.convergence-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.convergence-table th,
.convergence-table td {
  text-align: left;
  padding: 0.4rem 0.5rem;
  border-bottom: 1px solid var(--color-border);
}

.cv-top-count {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  margin-left: 0.3rem;
}

.cv-agreed {
  color: var(--color-status-current);
  font-weight: var(--font-weight-bold);
}

.free-text-key {
  font-style: italic;
}

.free-text-tag {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
}

.empty-hint {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
