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
  color: #fff;
  white-space: nowrap;
}

.status-current { background-color: var(--color-status-current); }
.status-planned { background-color: var(--color-status-planned); }
.status-planned-development { background-color: var(--color-status-planned-development); }
.status-planned-replacement { background-color: var(--color-status-planned-replacement); }
.status-none { background-color: var(--color-status-none); }
</style>
