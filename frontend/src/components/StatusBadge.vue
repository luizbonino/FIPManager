<template>
  <span class="status-badge" :class="`status-${status}`">{{ $t(i18nKey) }}</span>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import type { DeclarationStatus, MigrationItemStatus } from '@/types/api'

/**
 * Five distinct colours **and** always the text label (spec 02 §4.3) —
 * status is never conveyed by colour alone. Also reused, unchanged, for
 * `FipMigrate.vue`'s diff status column (spec 07 §5): `MigrationItemStatus`
 * shares no string values with `DeclarationStatus`, so one lookup table and
 * one `status-*` CSS class scheme cover both without a variant prop.
 */
const props = defineProps<{ status: DeclarationStatus | MigrationItemStatus }>()

const STATUS_KEYS: Record<DeclarationStatus | MigrationItemStatus, string> = {
  current: 'current',
  planned: 'planned',
  'planned-development': 'plannedDevelopment',
  'planned-replacement': 'plannedReplacement',
  none: 'none',
  unchanged: 'unchanged',
  added: 'added',
  removed: 'removed',
  hidden: 'hidden',
  split: 'split',
}

/** `declarationStatus.*` for the five `DeclarationStatus` values, `migration.status*` for the five migration ones. */
const I18N_NAMESPACE: Record<DeclarationStatus | MigrationItemStatus, string> = {
  current: 'declarationStatus',
  planned: 'declarationStatus',
  'planned-development': 'declarationStatus',
  'planned-replacement': 'declarationStatus',
  none: 'declarationStatus',
  unchanged: 'migration',
  added: 'migration',
  removed: 'migration',
  hidden: 'migration',
  split: 'migration',
}

const statusKey = computed(() => STATUS_KEYS[props.status])
const i18nKey = computed(() => {
  const ns = I18N_NAMESPACE[props.status]
  if (ns === 'migration') {
    const key = `status${statusKey.value.charAt(0).toUpperCase()}${statusKey.value.slice(1)}`
    return `migration.${key}`
  }
  return `declarationStatus.${statusKey.value}`
})
</script>

<style scoped>
.status-badge {
  display: inline-block;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  white-space: nowrap;
}

/* Each status pairs an explicit bg + fg (not a shared white text default)
   so contrast stays correct even if a status's hue changes independently. */
.status-current { background-color: var(--status-current-bg); color: var(--status-current-fg); }
.status-planned { background-color: var(--status-planned-bg); color: var(--status-planned-fg); }
.status-planned-development { background-color: var(--status-planned-development-bg); color: var(--status-planned-development-fg); }
.status-planned-replacement { background-color: var(--status-planned-replacement-bg); color: var(--status-planned-replacement-fg); }
.status-none { background-color: var(--status-none-bg); color: var(--status-none-fg); }

/* Migration diff statuses (spec 07 §5) — same component, disjoint values. */
.status-unchanged { background-color: var(--status-unchanged-bg); color: var(--status-unchanged-fg); }
.status-added { background-color: var(--status-added-bg); color: var(--status-added-fg); }
.status-removed { background-color: var(--status-removed-bg); color: var(--status-removed-fg); }
.status-hidden { background-color: var(--status-hidden-bg); color: var(--status-hidden-fg); }
.status-split { background-color: var(--status-split-bg); color: var(--status-split-fg); }
</style>
