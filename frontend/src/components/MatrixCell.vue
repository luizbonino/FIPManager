<template>
  <div class="matrix-cell" :class="{ compact }">
    <p v-if="cell.unanswered" class="chip status-unanswered" :aria-label="$t('matrix.unanswered')">–</p>
    <template v-else>
      <span v-for="chip in cell.chips" :key="chip.key" class="chip-wrap">
        <button
          type="button"
          class="chip"
          :class="`status-${chip.status}`"
          :title="chipTitle(chip)"
          :aria-label="chipTitle(chip)"
          @click="chip.note ? toggleNote(chip.key) : undefined"
        >
          <span class="chip-label">{{ chip.label || statusFullText(chip.status) }}</span>
          <span class="chip-status">{{ statusText(chip.status) }}</span>
          <span v-if="chip.note" class="chip-note-marker" aria-hidden="true">&#9679;</span>
        </button>
        <p v-if="chip.note && expanded.has(chip.key)" class="chip-note">
          <span class="sr-only">{{ $t('matrix.note') }}: </span>{{ chip.note }}
        </p>
      </span>
    </template>
    <p v-if="cell.comment" class="cell-comment" :title="cell.comment">{{ cell.comment }}</p>
  </div>
</template>

<script lang="ts" setup>
import { reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import type { MatrixCell, MatrixChip } from '@/lib/matrix'
import type { DeclarationStatus } from '@/types/api'

/**
 * One matrix cell (spec 03 §1.3): one `<button>` chip per stored
 * declaration, class `chip status-<status>`, label **and** status text
 * always shown (colour is never the only signal, spec 02 §4.3); an empty
 * cell renders "–". `compact` abbreviates the status text to three letters,
 * keeping the full text in `title`/`aria-label`.
 */
const props = defineProps<{ cell: MatrixCell; compact?: boolean }>()

const { t } = useI18n()

const STATUS_KEYS: Record<DeclarationStatus, string> = {
  current: 'current',
  planned: 'planned',
  'planned-development': 'plannedDevelopment',
  'planned-replacement': 'plannedReplacement',
  none: 'none',
}

const STATUS_ABBR: Record<DeclarationStatus, string> = {
  current: 'CUR',
  planned: 'PLA',
  'planned-development': 'DEV',
  'planned-replacement': 'REP',
  none: 'NON',
}

// Which chips (by key) currently show their note underneath — tap to toggle.
const expanded = reactive(new Set<string>())

function toggleNote(key: string) {
  if (expanded.has(key)) expanded.delete(key)
  else expanded.add(key)
}

function statusFullText(status: DeclarationStatus): string {
  return t(`declarationStatus.${STATUS_KEYS[status]}`)
}

function statusText(status: DeclarationStatus): string {
  return props.compact ? STATUS_ABBR[status] : statusFullText(status)
}

function chipTitle(chip: MatrixChip): string {
  const label = chip.label || statusFullText(chip.status)
  const base = `${label} — ${statusFullText(chip.status)}`
  return chip.note ? `${base}: ${chip.note}` : base
}
</script>

<style scoped>
.matrix-cell {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  align-items: flex-start;
}

.chip-wrap {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.15rem 0.5rem;
  border: 1px solid transparent;
  border-radius: 999px;
  font-size: var(--font-size-xs);
  color: #fff;
  max-width: 14rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.compact .chip {
  font-size: 0.65rem;
  padding: 0.1rem 0.35rem;
  max-width: 8rem;
}

.chip-label {
  overflow: hidden;
  text-overflow: ellipsis;
}

.chip-status {
  font-weight: var(--font-weight-bold);
  opacity: 0.9;
}

.chip-note-marker {
  font-size: 0.6em;
}

.chip.status-current { background-color: var(--color-status-current); }
.chip.status-planned { background-color: var(--color-status-planned); }
.chip.status-planned-development { background-color: var(--color-status-planned-development); }
.chip.status-planned-replacement { background-color: var(--color-status-planned-replacement); }
.chip.status-none { background-color: var(--color-status-none); }

.chip.status-unanswered {
  display: inline-block;
  padding: 0.15rem 0.6rem;
  border: 1px dashed #9ca3af;
  border-radius: 999px;
  background-color: #f3f4f6;
  color: #6b7280;
  margin: 0;
}

.chip-note {
  margin: 0.15rem 0 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  max-width: 14rem;
}

.cell-comment {
  margin: 0.2rem 0 0;
  font-size: var(--font-size-xs);
  font-style: italic;
  color: var(--color-text-secondary);
  max-width: 14rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
