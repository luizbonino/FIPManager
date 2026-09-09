<template>
  <div class="matrix-scroll">
    <table class="matrix-table">
      <thead>
        <!-- spec 08 §3.3: a second header row grouping columns by
             questionnaire ref, only while a session actually offers more
             than one (a single-ref session looks exactly as before). -->
        <tr v-if="matrix.columnGroups.length > 1" class="column-group-row">
          <th scope="col" class="sticky-col group-header-fill"></th>
          <template v-for="group in matrix.columnGroups" :key="group.refKey">
            <th v-if="group.columnCount > 0" scope="colgroup" :colspan="group.columnCount" class="column-group-head">
              {{ group.label ?? group.refKey }}
            </th>
          </template>
          <th scope="col" class="group-header-fill"></th>
        </tr>
        <tr>
          <th scope="col" class="sticky-col question-head">{{ $t('matrix.question') }}</th>
          <th v-for="column in matrix.columns" :key="column.fipId" scope="col" class="fip-head">
            <router-link :to="column.url" class="fip-name" :title="column.fullLabel">{{ column.label }}</router-link>
            <ProgressBar :answered="column.answeredCount" :total="matrix.questionCount" />
          </th>
          <th scope="col" class="convergence-head">{{ $t('matrix.convergence') }}</th>
        </tr>
      </thead>
      <tbody v-for="group in matrix.groups" :key="group.sectionId">
        <tr class="group-head-row">
          <th scope="rowgroup" class="sticky-col group-title" :colspan="1">{{ group.title ?? $t('matrix.otherGroup') }}</th>
          <td :colspan="matrix.columns.length" class="group-fill"></td>
          <td class="group-convergence">
            <ConvergenceBadge :group="{ agreed: group.rowsAgreed, total: group.rowsWithData }" compact />
          </td>
        </tr>
        <tr v-for="row in group.rows" :key="row.questionId">
          <th scope="row" class="sticky-col row-head" :class="{ compact }">
            <div class="row-head-top">
              <span class="question-id">{{ row.questionId }}</span>
              <span v-if="row.scope" class="scope-badge">{{ $t(`matrix.scope${row.scope === 'metadata' ? 'Metadata' : 'Data'}`) }}</span>
            </div>
            <p class="row-text">{{ row.text }}</p>
            <span v-if="row.ferTypeLabel" class="fer-type-chip">{{ row.ferTypeLabel }}</span>
          </th>
          <td v-for="cell in row.cells" :key="cell.fipId">
            <MatrixCell :cell="cell" :compact="compact" />
          </td>
          <td class="row-convergence">
            <ConvergenceBadge :convergence="row.convergence" :compact="compact" />
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script lang="ts" setup>
import type { Matrix } from '@/lib/matrix'
import MatrixCell from './MatrixCell.vue'
import ConvergenceBadge from './ConvergenceBadge.vue'
import ProgressBar from './ProgressBar.vue'

/**
 * The comparison-matrix table itself (spec 03 §1.3): one horizontally
 * scrolling `<table>`, sticky first column, one `<tbody>` per knowledge-model
 * section with a group-head row, one `<th scope="col">` per FIP and a
 * trailing convergence column. Pure renderer — `matrix` is already filtered
 * by the caller's toggles (`SessionMatrix.vue`).
 */
defineProps<{ matrix: Matrix; compact?: boolean }>()
</script>

<style scoped>
.matrix-scroll {
  overflow-x: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
}

.matrix-table {
  border-collapse: collapse;
  width: 100%;
  min-width: 40rem;
}

.matrix-table th,
.matrix-table td {
  border: 1px solid var(--color-border);
  padding: 0.5rem 0.6rem;
  vertical-align: top;
  text-align: left;
}

thead th {
  background-color: var(--color-hover);
  position: sticky;
  top: 0;
  z-index: 2;
}

.sticky-col {
  position: sticky;
  left: 0;
  background-color: var(--color-background);
  z-index: 1;
  min-width: 14rem;
  max-width: 18rem;
}

thead .sticky-col {
  z-index: 3;
  background-color: var(--color-hover);
}

.fip-head {
  min-width: 8rem;
}

.column-group-row th {
  background-color: var(--color-secondary);
  color: var(--color-primary);
  font-weight: var(--font-weight-bold);
  text-align: center;
}

.group-header-fill {
  background-color: var(--color-hover);
}

.fip-name {
  font-weight: var(--font-weight-medium);
  display: block;
  margin-bottom: 0.3rem;
}

.convergence-head {
  min-width: 8rem;
}

.group-head-row th,
.group-head-row td {
  background-color: var(--color-secondary);
  font-weight: var(--font-weight-bold);
}

.group-title {
  color: var(--color-primary);
}

.group-fill {
  background-color: var(--color-secondary);
}

.row-head.compact .row-text {
  font-size: var(--font-size-sm);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.row-head-top {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.question-id {
  font-family: monospace;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  background-color: var(--color-secondary);
  padding: 0.1rem 0.4rem;
  border-radius: var(--border-radius-sm);
}

.scope-badge {
  font-size: var(--font-size-xs);
  color: var(--color-chip-text);
  background-color: var(--color-chip-bg);
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
}

.row-text {
  margin: 0.3rem 0;
  font-weight: var(--font-weight-medium);
}

.fer-type-chip {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.row-convergence,
.group-convergence {
  min-width: 8rem;
}
</style>
