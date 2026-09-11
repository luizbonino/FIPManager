<template>
  <div class="neighbour-list">
    <p v-if="skippedPopularKeys.length > 0" class="disclosure">
      {{ $t('dashboard.similarity.skippedPopularKeys', { keys: skippedPopularKeys.join(', ') }) }}
    </p>
    <p v-if="candidateBudgetExhausted" class="disclosure">{{ $t('dashboard.similarity.candidateBudgetExhausted') }}</p>
    <p v-if="postingTruncated" class="disclosure">{{ $t('dashboard.similarity.postingTruncated') }}</p>

    <table class="neighbour-table">
      <thead>
        <tr>
          <th scope="col">{{ $t('dashboard.similarity.neighbourFip') }}</th>
          <th scope="col">{{ $t('dashboard.similarity.similarity') }}</th>
          <th scope="col">{{ $t('dashboard.similarity.sharedKeys') }}</th>
          <th scope="col">{{ $t('dashboard.similarity.topShared') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in neighbours" :key="row.fipId">
          <td>
            <router-link :to="`/fips/${row.fipId}`">{{ row.label }}</router-link>
          </td>
          <td>{{ formatShare(row.similarity) }}</td>
          <td>{{ row.sharedKeys }}</td>
          <td>
            <template v-for="(shared, index) in row.topShared" :key="`${shared.questionId}-${shared.ferKey}`">
              <span :class="{ 'free-text-key': formatConvergenceKey(shared.label).isFreeText }">{{ formatConvergenceKey(shared.label).text }}</span>
              <span v-if="formatConvergenceKey(shared.label).isFreeText" class="free-text-tag">({{ $t('dashboard.similarity.freeText') }})</span>
              <span v-if="index < row.topShared.length - 1">, </span>
            </template>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="neighbours.length === 0" class="empty-hint">{{ $t('dashboard.similarity.noNeighbours') }}</p>
  </div>
</template>

<script lang="ts" setup>
import { formatConvergenceKey, formatShare } from '@/lib/dashboard'
import type { NeighbourRow } from '@/types/dashboard'

/**
 * Spec 13 §4.3/§6.2: up to 100 ranked neighbours, plus the disclosure
 * fields a wrong-or-truncated candidate set must surface, not swallow
 * (spec 13 AC-6): `candidateBudgetExhausted`, `postingTruncated`,
 * `skippedPopularKeys`.
 */
defineProps<{
  neighbours: NeighbourRow[]
  candidateBudgetExhausted: boolean
  postingTruncated: boolean
  skippedPopularKeys: string[]
}>()
</script>

<style scoped>
.neighbour-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.disclosure {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  background-color: var(--color-hover);
  padding: 0.35rem 0.6rem;
  border-radius: var(--border-radius-sm);
}

.neighbour-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.neighbour-table th,
.neighbour-table td {
  text-align: left;
  padding: 0.4rem 0.5rem;
  border-bottom: 1px solid var(--color-border);
}

.empty-hint {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}

.free-text-key {
  font-style: italic;
}

.free-text-tag {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
}
</style>
