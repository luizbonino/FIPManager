<template>
  <div class="move-buttons no-print">
    <button
      type="button"
      class="move-btn"
      :disabled="!canUp"
      :aria-label="$t('km.moveUp')"
      :title="$t('km.moveUp')"
      @click="$emit('up')"
    >
      <span aria-hidden="true">&#9650;</span>
    </button>
    <button
      type="button"
      class="move-btn"
      :disabled="!canDown"
      :aria-label="$t('km.moveDown')"
      :title="$t('km.moveDown')"
      @click="$emit('down')"
    >
      <span aria-hidden="true">&#9660;</span>
    </button>
  </div>
</template>

<script lang="ts" setup>
/**
 * Up/down reorder controls (spec 04 §5 A1): no drag handle anywhere in
 * this feature — phone- and keyboard-friendly, trivially testable, and
 * ends are simply `disabled`. Reused for both sections and questions.
 */
defineProps<{ canUp: boolean; canDown: boolean }>()
defineEmits<{ up: []; down: [] }>()
</script>

<style scoped>
.move-buttons {
  display: flex;
  flex-direction: row;
  gap: 0.35rem;
}

.move-btn {
  min-width: 44px;
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
  cursor: pointer;
  font-size: var(--font-size-sm);
  line-height: 1;
}

.move-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.move-btn:not(:disabled):hover {
  background-color: var(--color-hover);
}
</style>
