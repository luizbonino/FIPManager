<template>
  <div class="export-buttons no-print">
    <a class="export-link" :href="jsonUrl">{{ $t('fip.exportJson') }}</a>
    <a class="export-link" :href="csvUrl">{{ $t('fip.exportCsv') }}</a>
    <a class="export-link" :href="ttlUrl" :title="$t('export.rdfHint')">{{ $t('export.ttl') }}</a>
    <a class="export-link" :href="jsonldUrl" :title="$t('export.rdfHint')">{{ $t('export.jsonld') }}</a>
    <a v-if="nanopubZipUrl" class="export-link" :href="nanopubZipUrl">{{ $t('nanopubExport.exportLinkLabel') }}</a>
  </div>
</template>

<script lang="ts" setup>
/**
 * Plain `<a>` links to the export endpoints (spec 02 §2.4, spec 03 §3) —
 * `Content-Disposition: attachment` is already set server-side.
 * `nanopubZipUrl` (spec 11 §3.5) is optional so existing callers keep
 * working unchanged until they pass it.
 */
defineProps<{ jsonUrl: string; csvUrl: string; ttlUrl: string; jsonldUrl: string; nanopubZipUrl?: string }>()
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
