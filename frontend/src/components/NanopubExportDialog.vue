<template>
  <div v-if="open" class="nanopub-export-overlay" role="presentation" @click.self="$emit('close')">
    <div class="nanopub-export-dialog" role="dialog" aria-modal="true" :aria-label="$t('nanopubExport.dialogTitle')">
      <h2>{{ $t('nanopubExport.dialogTitle') }}</h2>
      <p class="unsigned-notice">{{ $t('nanopubExport.unsignedNotice') }}</p>

      <div v-if="loading" class="loading">
        <p>{{ $t('common.loading') }}</p>
      </div>
      <p v-else-if="loadError" class="form-error">{{ $t('nanopubExport.loadError') }}</p>

      <template v-else-if="index">
        <section class="counts-section">
          <h3>{{ $t('nanopubExport.countsTitle') }}</h3>
          <ul>
            <li>{{ $t('nanopubExport.countsNanopubs') }}: {{ index.counts.nanopubs }}</li>
            <li>{{ $t('nanopubExport.countsDeclarations') }}: {{ index.counts.declarations }}</li>
            <li>{{ $t('nanopubExport.countsSkipped') }}: {{ index.counts.skipped }}</li>
          </ul>
        </section>

        <section v-if="index.skipped.length > 0" class="skipped-section">
          <h3>{{ $t('nanopubExport.skippedTitle') }}</h3>
          <ul>
            <li v-for="(s, i) in index.skipped" :key="i">
              {{
                $t('nanopubExport.skippedReason', {
                  questionId: s.questionId,
                  index: s.declarationIndex,
                  reason: s.reason,
                })
              }}
            </li>
          </ul>
        </section>

        <section
          v-if="hasNotRepresented"
          class="not-represented-section"
        >
          <h3>{{ $t('nanopubExport.notRepresentedTitle') }}</h3>
          <ul>
            <li v-if="index.notRepresented.notApplicable.length > 0">
              {{
                $t('nanopubExport.notRepresentedNotApplicable', {
                  questions: index.notRepresented.notApplicable.join(', '),
                })
              }}
            </li>
            <li v-if="index.notRepresented.answerComments.length > 0">
              {{
                $t('nanopubExport.notRepresentedAnswerComments', {
                  questions: index.notRepresented.answerComments.join(', '),
                })
              }}
            </li>
            <li v-if="index.notRepresented.dmpEvidence.length > 0">
              {{ $t('nanopubExport.notRepresentedDmpEvidence', { count: index.notRepresented.dmpEvidence.length }) }}
            </li>
            <li v-if="index.notRepresented.relatedDmps > 0">
              {{ $t('nanopubExport.notRepresentedRelatedDmps', { count: index.notRepresented.relatedDmps }) }}
            </li>
          </ul>
        </section>

        <section class="prerequisites-section">
          <h3>{{ $t('nanopubExport.prerequisitesTitle') }}</h3>
          <ul>
            <li v-for="p in index.publishPrerequisites.missing" :key="p.what">
              <strong>{{ p.what }}</strong> — {{ p.detail }}
            </li>
          </ul>
        </section>

        <section class="preview-section">
          <h3>{{ $t('nanopubExport.previewTitle') }}</h3>
          <pre class="preview-trig">{{ previewText }}</pre>
        </section>
      </template>

      <div class="actions">
        <button type="button" class="btn btn-secondary" @click="$emit('close')">{{ $t('common.close') }}</button>
        <a v-if="index" class="btn btn-primary" :href="zipUrl">{{ $t('nanopubExport.downloadButton') }}</a>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
/**
 * spec 11 §3.5/§2.6: the "Prepare nanopublications" dialog, opened from
 * `FipRead.vue`. Fetches `index.json` (the manifest) and the FIP
 * nanopub's `preview.trig` on open; the download itself is a plain `<a
 * href>` to `nanopubZipUrl` — no `fetch`-then-blob — so the browser
 * handles the download and honours the server's `Content-Disposition`
 * filename (acceptance criterion #6).
 */
import { computed, ref, watch } from 'vue'
import { getNanopubIndex, getNanopubPreview, nanopubZipUrl } from '@/api/network'
import type { NanopubBundleIndex } from '@/types/network'

const props = defineProps<{ open: boolean; fipId: string }>()
defineEmits<{ close: [] }>()

const loading = ref(false)
const loadError = ref(false)
const index = ref<NanopubBundleIndex | null>(null)
const previewText = ref('')

const zipUrl = computed(() => nanopubZipUrl(props.fipId))

const hasNotRepresented = computed(() => {
  const nr = index.value?.notRepresented
  if (!nr) return false
  return (
    nr.notApplicable.length > 0 || nr.answerComments.length > 0 || nr.dmpEvidence.length > 0 || nr.relatedDmps > 0
  )
})

async function load() {
  loading.value = true
  loadError.value = false
  index.value = null
  previewText.value = ''
  try {
    const [idx, preview] = await Promise.all([getNanopubIndex(props.fipId), getNanopubPreview(props.fipId)])
    index.value = idx
    previewText.value = preview
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) load()
  },
  { immediate: true }
)
</script>

<style scoped>
.nanopub-export-overlay {
  position: fixed;
  inset: 0;
  background-color: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 1rem;
}

.nanopub-export-dialog {
  background-color: var(--color-background);
  border-radius: var(--border-radius-md);
  padding: 1.5rem;
  max-width: 36rem;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-height: 90vh;
  overflow-y: auto;
}

.nanopub-export-dialog h2 {
  margin: 0;
  font-size: 1.2rem;
}

.nanopub-export-dialog h3 {
  margin: 0 0 0.4rem;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.unsigned-notice {
  margin: 0;
  padding: 0.6rem 0.8rem;
  border-radius: var(--border-radius-sm);
  background-color: var(--color-user-info);
  color: var(--color-user-info-text);
  font-weight: var(--font-weight-medium);
}

.loading {
  text-align: center;
  padding: 1rem;
}

.form-error {
  color: var(--color-error);
}

section ul {
  margin: 0;
  padding-left: 1.25rem;
  font-size: var(--font-size-sm);
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.preview-trig {
  max-height: 12rem;
  overflow: auto;
  background-color: var(--color-hover);
  border-radius: var(--border-radius-sm);
  padding: 0.6rem;
  font-size: var(--font-size-xs);
  white-space: pre-wrap;
  word-break: break-word;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.btn {
  min-height: 44px;
  padding: 0.6rem 1.2rem;
  border: none;
  border-radius: var(--border-radius-sm);
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
}

.btn-primary {
  background-color: var(--color-primary);
  color: var(--color-primary-text);
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
}
</style>
