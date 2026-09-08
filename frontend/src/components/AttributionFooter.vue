<template>
  <footer class="attribution-footer">
    <p v-if="questionnaireLicenseIsCcBySa">{{ $t('attribution.questionnaire') }}</p>
    <p v-if="questionnaireLicenseIsCcBySa">{{ $t('attribution.ontology') }}</p>
    <p>{{ $t('attribution.answers', { license: fipLicense }) }}</p>
  </footer>
</template>

<script lang="ts" setup>
import { computed } from 'vue'

/**
 * Mandatory on `FipRead` and `FipEditor` (spec 02 §4.3): when the
 * knowledge model's `license` starts with `CC-BY-SA` it shows the GO FAIR
 * FIP mini-questionnaire and FIP-Ontology credits; the FIP's own `license`
 * is always shown.
 */
const props = defineProps<{ questionnaireLicense: string | null; fipLicense: string }>()

const questionnaireLicenseIsCcBySa = computed(() => (props.questionnaireLicense ?? '').startsWith('CC-BY-SA'))
</script>

<style scoped>
.attribution-footer {
  margin-top: 2rem;
  padding-top: 1rem;
  border-top: 1px solid var(--color-border);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.attribution-footer p {
  margin: 0.25rem 0;
}
</style>
