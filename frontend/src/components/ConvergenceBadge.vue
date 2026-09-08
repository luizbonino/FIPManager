<template>
  <span class="convergence-badge" :class="{ compact, agreed: isAgreed }">
    <template v-if="group">
      <span class="cb-ratio">{{ $t('matrix.groupAgreement', { agreed: group.agreed, total: group.total }) }}</span>
      <span v-if="isAgreed" class="cb-check" aria-hidden="true">&#10003;</span>
    </template>
    <template v-else-if="convergence">
      <span class="cb-count" :title="$t('matrix.convergenceHint')">{{ convergence.distinctCurrent }}</span>
      <span v-if="convergence.topLabel" class="cb-top">
        {{ $t('matrix.mostCommon', { label: convergence.topLabel, count: convergence.topCount }) }}
      </span>
      <span v-if="isAgreed" class="cb-check" :title="$t('matrix.agreed')" aria-hidden="true">&#10003;</span>
      <span v-if="isAgreed" class="sr-only">{{ $t('matrix.agreed') }}</span>
    </template>
  </span>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import type { Convergence } from '@/lib/matrix'

/**
 * Row usage: `{ convergence }` — distinct-current count big, most-common
 * label × count beneath, a green check when `agreed`. Group-head usage
 * (spec 03 §1.3): `{ group: { agreed: rowsAgreed, total: rowsWithData } }`,
 * reusing the same visual language for "{agreed} of {total} rows agree".
 */
const props = defineProps<{
  convergence?: Convergence
  group?: { agreed: number; total: number }
  compact?: boolean
}>()

const isAgreed = computed(() => {
  if (props.group) return props.group.total > 0 && props.group.agreed === props.group.total
  return !!props.convergence?.agreed
})
</script>

<style scoped>
.convergence-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.cb-count {
  font-weight: var(--font-weight-bold);
  font-size: var(--font-size-lg);
}

.compact .cb-count {
  font-size: var(--font-size-md);
}

.cb-top,
.cb-ratio {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.cb-check {
  color: var(--color-status-current);
  font-weight: var(--font-weight-bold);
}
</style>
