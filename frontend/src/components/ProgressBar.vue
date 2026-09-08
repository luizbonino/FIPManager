<template>
  <div class="progress-bar" role="progressbar" :aria-valuenow="answered" aria-valuemin="0" :aria-valuemax="total">
    <div class="progress-track">
      <div class="progress-fill" :style="{ width: pct + '%' }" />
    </div>
    <span class="progress-text">{{ $t('editor.progress', { answered, total }) }}</span>
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'

/** `answered / 21` bar (spec 02 §2.2, §4.2's `SessionFipList` reuse). */
const props = defineProps<{ answered: number; total: number }>()

const pct = computed(() => (props.total > 0 ? Math.round((props.answered / props.total) * 100) : 0))
</script>

<style scoped>
.progress-bar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}

.progress-track {
  flex: 1;
  min-width: 3rem;
  height: 0.5rem;
  border-radius: 999px;
  background-color: var(--color-secondary);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background-color: var(--color-primary);
  transition: width 0.2s ease;
}

.progress-text {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  white-space: nowrap;
}
</style>
