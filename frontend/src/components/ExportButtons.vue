<template>
  <div class="export-buttons no-print">
    <a class="export-link" :href="jsonUrl">{{ $t('fip.exportJson') }}</a>
    <a class="export-link" :href="csvUrl">{{ $t('fip.exportCsv') }}</a>
  </div>
</template>

<script lang="ts" setup>
/**
 * Plain `<a>` links to the export endpoints (spec 02 §2.4) —
 * `Content-Disposition: attachment` is already set server-side.
 */
defineProps<{ jsonUrl: string; csvUrl: string }>()
</script>

<style scoped>
.export-buttons {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.export-link {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  padding: 0.5rem 1rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
  text-decoration: none;
}

.export-link:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  text-decoration: none;
}
</style>
