<template>
  <span class="status-badge" :class="`status-${status}`">{{ $t(`declarationStatus.${statusKey}`) }}</span>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import type { DeclarationStatus } from '@/types/api'

/**
 * Five distinct colours **and** always the text label (spec 02 §4.3) —
 * status is never conveyed by colour alone.
 */
const props = defineProps<{ status: DeclarationStatus }>()

const STATUS_KEYS: Record<DeclarationStatus, string> = {
  current: 'current',
  planned: 'planned',
  'planned-development': 'plannedDevelopment',
  'planned-replacement': 'plannedReplacement',
  none: 'none',
}

const statusKey = computed(() => STATUS_KEYS[props.status])
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
</style>
