<template>
  <div class="translation-meter" role="status">
    <div class="meter-track">
      <div class="meter-fill" :style="{ width: pct + '%' }" />
    </div>
    <span class="meter-text">
      {{ $t('km.translationMeter', { done, total, language: $t(`languages.${language}`) }) }}
    </span>
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'

/**
 * Translation-completeness indicator (spec 04 §5): "{done} of {total}
 * texts in {language}" — the editor's sticky header shows one of these for
 * the currently-selected language tab.
 */
const props = defineProps<{ done: number; total: number; language: string }>()

const pct = computed(() => (props.total > 0 ? Math.round((props.done / props.total) * 100) : 0))
</script>

<style scoped>
.translation-meter {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}

.meter-track {
  flex: 1;
  min-width: 3rem;
  height: 0.5rem;
  border-radius: 999px;
  background-color: var(--color-secondary);
  overflow: hidden;
}

.meter-fill {
  height: 100%;
  background-color: var(--color-status-current);
  transition: width 0.2s ease;
}

.meter-text {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  white-space: nowrap;
}
</style>
