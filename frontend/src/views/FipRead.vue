<template>
  <div class="fip-read-view">
    <div v-if="loading" class="loading">
      <p>{{ $t('common.loading') }}</p>
    </div>

    <div v-else-if="notFound" class="message-box">
      <p>{{ $t('fipRead.notShared') }}</p>
      <router-link to="/" class="btn btn-secondary no-print">{{ $t('nav.home') }}</router-link>
    </div>

    <template v-else-if="doc">
      <header class="community-header">
        <h1>{{ doc.fip.community?.name || doc.fip.id }}</h1>
        <p v-if="doc.fip.community?.description" class="community-description">
          {{ doc.fip.community.description }}
        </p>
        <dl class="community-meta">
          <template v-if="doc.fip.community?.domain">
            <dt>{{ $t('community.domain') }}</dt>
            <dd>{{ doc.fip.community.domain }}</dd>
          </template>
          <template v-if="doc.fip.community?.dataSteward?.orcid">
            <dt>{{ $t('community.dataSteward') }}</dt>
            <dd>
              <a :href="`https://orcid.org/${doc.fip.community.dataSteward.orcid}`" target="_blank" rel="noopener">
                {{ doc.fip.community.dataSteward.orcid }}
              </a>
            </dd>
          </template>
          <dt>{{ $t('fipRead.questionnaire') }}</dt>
          <dd>{{ doc.questionnaireRef.title }} ({{ doc.questionnaireRef.id }} v{{ doc.questionnaireRef.version }}, {{ doc.fip.language }})</dd>
          <dt>{{ $t('common.created') }}</dt>
          <dd>{{ formatDate(doc.fip.createdAt) }}</dd>
          <dt>{{ $t('common.updated') }}</dt>
          <dd>{{ formatDate(doc.fip.updatedAt) }}</dd>
        </dl>
        <p class="print-only fip-url-print">{{ doc.fip.url }}</p>
      </header>

      <div class="sections">
        <section v-for="section in sections" :key="section.id" class="section">
          <h2>{{ $t(`sections.${section.id}`) }}</h2>
          <div class="questions">
            <article
              v-for="answer in section.answers"
              :key="answer.questionId"
              class="question"
              :class="{ unanswered: answer.declarations.length === 0 }"
            >
              <div class="question-head">
                <span class="question-id">{{ answer.questionId }}</span>
                <span v-if="answer.ferType" class="question-fer-chip">{{ answer.ferType }}</span>
              </div>
              <p class="question-text">{{ answer.questionText }}</p>

              <p v-if="answer.declarations.length === 0" class="not-answered">
                {{ $t('editor.notAnswered') }}
              </p>
              <ul v-else class="declarations">
                <li v-for="(decl, i) in answer.declarations" :key="i" class="declaration">
                  <span class="declaration-label">{{ decl.fer?.label || decl.ferFreeText || decl.fer?.id }}</span>
                  <StatusBadge :status="decl.status" />
                  <span v-if="decl.note" class="declaration-note">{{ decl.note }}</span>
                </li>
              </ul>
              <p v-if="answer.comment" class="question-comment">{{ answer.comment }}</p>
            </article>
          </div>
        </section>
      </div>

      <div class="actions no-print">
        <ExportButtons :json-url="fipExportJsonUrl(doc.fip.id)" :csv-url="fipExportCsvUrl(doc.fip.id)" />
        <button type="button" class="btn btn-secondary" @click="printPage">{{ $t('fipRead.print') }}</button>
      </div>

      <AttributionFooter :questionnaire-license="questionnaireLicense" :fip-license="doc.fip.license" />
    </template>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ApiResponseError } from '@/api/client'
import { fipExportCsvUrl, fipExportJsonUrl, getFipExport } from '@/api/fips'
import { getKnowledgeModel } from '@/api/knowledgeModels'
import StatusBadge from '@/components/StatusBadge.vue'
import ExportButtons from '@/components/ExportButtons.vue'
import AttributionFooter from '@/components/AttributionFooter.vue'
import '@/assets/print.css'
import type { FipExportDoc } from '@/types/api'

// Spec 02 §4.3: replaces FipDetail.vue. Single data source is the export
// document; the knowledge model is fetched only for AttributionFooter's
// CC-BY-SA check (its `license` is not part of the export document).
const route = useRoute()

const loading = ref(true)
const notFound = ref(false)
const doc = ref<FipExportDoc | null>(null)
const questionnaireLicense = ref<string | null>(null)

const sections = computed(() => {
  if (!doc.value) return []
  const order: string[] = []
  const bySection = new Map<string, { id: string; answers: typeof doc.value.answers }>()
  for (const answer of doc.value.answers) {
    if (!bySection.has(answer.sectionId)) {
      bySection.set(answer.sectionId, { id: answer.sectionId, answers: [] })
      order.push(answer.sectionId)
    }
    bySection.get(answer.sectionId)!.answers.push(answer)
  }
  return order.map((id) => bySection.get(id)!)
})

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

function printPage() {
  window.print()
}

async function load() {
  loading.value = true
  notFound.value = false
  const id = String(route.params.id)
  try {
    doc.value = await getFipExport(id)
    getKnowledgeModel(doc.value.questionnaireRef.id, doc.value.questionnaireRef.version)
      .then((km) => {
        questionnaireLicense.value = km.license
      })
      .catch(() => {
        questionnaireLicense.value = null
      })
  } catch (err) {
    if (err instanceof ApiResponseError && err.status === 404) {
      notFound.value = true
    } else {
      notFound.value = true
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.fip-read-view {
  max-width: 800px;
  margin: 0 auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.loading,
.message-box {
  text-align: center;
  padding: 3rem 1rem;
}

.community-header h1 {
  margin: 0 0 0.5rem;
  color: var(--color-primary);
}

.community-description {
  margin: 0 0 0.75rem;
  color: var(--color-text-secondary);
}

.community-meta {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.25rem 0.75rem;
  margin: 0;
  font-size: var(--font-size-sm);
}

.community-meta dt {
  color: var(--color-text-secondary);
}

.community-meta dd {
  margin: 0;
}

.print-only {
  display: none;
}

.sections {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.section h2 {
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 0.4rem;
}

.questions {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.question {
  padding: 0.75rem 1rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
}

.question.unanswered {
  opacity: 0.65;
  background-color: var(--color-hover);
}

.question-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.question-id {
  font-family: monospace;
  font-size: var(--font-size-xs);
  color: var(--color-id-chip-text);
  background-color: var(--color-id-chip-bg);
  padding: 0.15rem 0.4rem;
  border-radius: var(--border-radius-sm);
}

.question-fer-chip {
  font-size: var(--font-size-xs);
  color: var(--color-chip-text);
  background-color: var(--color-chip-bg);
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
}

.question-text {
  margin: 0.35rem 0;
  font-weight: var(--font-weight-medium);
}

.not-answered {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  font-style: italic;
}

.declarations {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.declaration {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  font-size: var(--font-size-sm);
}

.declaration-note {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
}

.question-comment {
  margin: 0.5rem 0 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  font-style: italic;
}

.actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.btn {
  min-height: 44px;
  padding: 0.6rem 1.2rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
  border: none;
}
</style>
