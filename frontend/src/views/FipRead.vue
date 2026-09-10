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
          <template v-if="doc.fip.migratedFrom">
            <dt>{{ $t('migration.migratedFromLabel') }}</dt>
            <dd>{{ $t('migration.migratedFromNote', { id: doc.fip.migratedFrom.id, version: doc.fip.migratedFrom.version }) }}</dd>
          </template>
          <template v-if="doc.fip.relatedDMPs.length > 0">
            <dt>{{ $t('dmp.heading') }}</dt>
            <dd>
              <ul class="dmp-list">
                <li v-for="(dmp, i) in doc.fip.relatedDMPs" :key="i">
                  <a v-if="isSafeHttpsUrl(dmp.url)" :href="dmp.url" target="_blank" rel="noopener">{{ dmpDisplayLabel(dmp) }}</a>
                  <span v-else>{{ dmpDisplayLabel(dmp) }}</span>
                  <span v-if="dmp.system === 'FioDMP'" class="dmp-badge">{{ $t('dmp.fiodmp') }}</span>
                  <span v-if="dmp.version" class="dmp-version">v{{ dmp.version }}</span>
                </li>
              </ul>
            </dd>
          </template>
        </dl>
        <p class="print-only fip-url-print">{{ doc.fip.url }}</p>
      </header>

      <MigrationBanner class="no-print" :fip-id="doc.fip.id" :edit-token="editToken" />

      <div class="sections">
        <section v-for="section in sections" :key="section.id" class="section">
          <h2>{{ $t(`sections.${section.id}`) }}</h2>
          <div class="questions">
            <article
              v-for="answer in section.answers"
              :key="answer.questionId"
              class="question"
              :class="{ unanswered: answer.declarations.length === 0 && !answer.notApplicable }"
            >
              <div class="question-head">
                <span class="question-id">{{ answer.questionId }}</span>
                <span v-if="answer.ferType" class="question-fer-chip">{{ answer.ferType }}</span>
              </div>
              <p class="question-text">{{ answer.questionText }}</p>

              <p v-if="answer.notApplicable" class="not-applicable">
                {{ $t('editor.notApplicable') }}
              </p>
              <p v-else-if="answer.declarations.length === 0" class="not-answered">
                {{ $t('editor.notAnswered') }}
              </p>
              <ul v-else class="declarations">
                <li v-for="(decl, i) in answer.declarations" :key="i" class="declaration">
                  <span class="declaration-label">{{ decl.fer?.label || decl.ferFreeText || decl.fer?.id }}</span>
                  <StatusBadge :status="decl.status" />
                  <span v-if="decl.successor || decl.successorFreeText" class="declaration-successor">
                    {{ $t('matrix.successor', { label: decl.successor?.label || decl.successorFreeText }) }}
                  </span>
                  <span v-if="decl.note" class="declaration-note">{{ decl.note }}</span>
                  <span v-if="decl.dmpEvidence" class="declaration-evidence">
                    {{ $t('dmp.evidence') }}:
                    <a
                      v-if="dmpEvidenceHref(decl.dmpEvidence)"
                      :href="dmpEvidenceHref(decl.dmpEvidence) as string"
                      target="_blank"
                      rel="noopener"
                    >
                      {{ dmpEvidenceLabel(decl.dmpEvidence) }}
                    </a>
                    <span v-else-if="dmpEvidenceLabel(decl.dmpEvidence)">{{ dmpEvidenceLabel(decl.dmpEvidence) }}</span>
                    <template v-if="decl.dmpEvidence.section"> · {{ decl.dmpEvidence.section }}</template>
                    <template v-if="decl.dmpEvidence.questionRef"> · {{ decl.dmpEvidence.questionRef }}</template>
                  </span>
                </li>
              </ul>
              <p v-if="answer.comment" class="question-comment">{{ answer.comment }}</p>
            </article>
          </div>
        </section>
      </div>

      <section v-if="doc.orphanedAnswers && doc.orphanedAnswers.length > 0" class="section orphaned-section">
        <h2>{{ $t('migration.orphanedTitle') }}</h2>
        <p class="orphaned-hint">{{ $t('migration.orphanedHint') }}</p>
        <div class="questions">
          <article v-for="orphan in doc.orphanedAnswers" :key="orphan.questionId" class="question">
            <div class="question-head">
              <span class="question-id">{{ orphan.questionId }}</span>
              <span class="orphaned-from">{{ $t('migration.migratedFromNote', { id: doc.questionnaireRef.id, version: orphan.fromVersion }) }}</span>
            </div>
            <p class="question-text">{{ orphan.questionText }}</p>
            <ul class="declarations">
              <li v-for="(decl, i) in orphan.declarations" :key="i" class="declaration">
                <span class="declaration-label">{{ decl.fer?.label || decl.ferFreeText || decl.fer?.id }}</span>
                <StatusBadge :status="decl.status" />
              </li>
            </ul>
            <p v-if="orphan.comment" class="question-comment">{{ orphan.comment }}</p>
          </article>
        </div>
      </section>

      <div class="actions no-print">
        <ExportButtons
          :json-url="fipExportJsonUrl(doc.fip.id)"
          :csv-url="fipExportCsvUrl(doc.fip.id)"
          :ttl-url="fipExportTtlUrl(doc.fip.id)"
          :jsonld-url="fipExportJsonldUrl(doc.fip.id)"
          :nanopub-zip-url="nanopubZipUrl(doc.fip.id)"
        />
        <button type="button" class="btn btn-secondary" @click="printPage">{{ $t('fipRead.print') }}</button>
        <button type="button" class="btn btn-secondary" @click="nanopubDialogOpen = true">
          {{ $t('nanopubExport.buttonLabel') }}
        </button>
      </div>

      <NanopubExportDialog
        :open="nanopubDialogOpen"
        :fip-id="doc.fip.id"
        @close="nanopubDialogOpen = false"
      />

      <AttributionFooter :questionnaire-license="questionnaireLicense" :fip-license="doc.fip.license" />
    </template>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ApiResponseError } from '@/api/client'
import { fipExportCsvUrl, fipExportJsonldUrl, fipExportJsonUrl, fipExportTtlUrl, getFipExport } from '@/api/fips'
import { nanopubZipUrl } from '@/api/network'
import { getKnowledgeModel } from '@/api/knowledgeModels'
import { getToken } from '@/lib/editTokens'
import StatusBadge from '@/components/StatusBadge.vue'
import ExportButtons from '@/components/ExportButtons.vue'
import AttributionFooter from '@/components/AttributionFooter.vue'
import MigrationBanner from '@/components/MigrationBanner.vue'
import NanopubExportDialog from '@/components/NanopubExportDialog.vue'
import '@/assets/print.css'
import type { FipExportDmpEvidence, FipExportDoc, RelatedDmp } from '@/types/api'

// Spec 02 §4.3: replaces FipDetail.vue. Single data source is the export
// document; the knowledge model is fetched only for AttributionFooter's
// CC-BY-SA check (its `license` is not part of the export document).
const route = useRoute()

const loading = ref(true)
const notFound = ref(false)
const doc = ref<FipExportDoc | null>(null)
const questionnaireLicense = ref<string | null>(null)
const nanopubDialogOpen = ref(false)

// spec 07 §5: an edit token in this browser's storage, if any — passed to
// MigrationBanner so a token-holding non-owner still sees it.
const editToken = computed(() => (doc.value ? (getToken(doc.value.fip.id) ?? undefined) : undefined))

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

// Spec 06 §1.3/§2.3: a linked plan shows its `dmpId` (FioDMP) or host+path
// (any other system); a declaration's resolved evidence shows the same for
// its own plan URL, plus section and question ref when stored.
function dmpDisplayLabel(dmp: RelatedDmp): string {
  if (dmp.dmpId) return dmp.dmpId
  try {
    const parsed = new URL(dmp.url)
    return parsed.host + parsed.pathname
  } catch {
    return dmp.url
  }
}

/** Client-side defence in depth (spec 06 §2.4): only ever a same-scheme `https://` URL becomes a clickable `href`. */
function isSafeHttpsUrl(url: string | null | undefined): boolean {
  if (!url) return false
  try {
    return new URL(url).protocol === 'https:'
  } catch {
    return false
  }
}

/** `null` when there's no safe URL to link to — the evidence's plan was removed, or (legacy) its URL isn't a safe https:// one. */
function dmpEvidenceHref(evidence: FipExportDmpEvidence): string | null {
  return isSafeHttpsUrl(evidence.dmpUrl) ? evidence.dmpUrl : null
}

// Text shown either inside the `<a>` (a safe dmpUrl) or, in its place, as
// plain text: the unsafe/unresolvable `rawUrl` the backend kept around, or
// '' (render nothing — the section/question-ref parts, if any, still show).
function dmpEvidenceLabel(evidence: FipExportDmpEvidence): string {
  if (isSafeHttpsUrl(evidence.dmpUrl)) {
    const parsed = new URL(evidence.dmpUrl as string)
    if (evidence.dmpSystem === 'FioDMP') return parsed.pathname.replace(/^\//, '')
    return parsed.host + parsed.pathname
  }
  return evidence.rawUrl ?? evidence.dmpUrl ?? ''
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

.dmp-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.dmp-badge {
  margin-left: 0.4rem;
  font-size: var(--font-size-xs);
  color: var(--color-chip-text);
  background-color: var(--color-chip-bg);
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
}

.dmp-version {
  margin-left: 0.4rem;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
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

.not-applicable {
  margin: 0;
  display: inline-block;
  padding: 0.15rem 0.6rem;
  border-radius: 999px;
  background-color: var(--color-status-not-applicable);
  color: #ffffff;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
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

.declaration-successor {
  color: var(--color-status-planned-replacement);
  font-size: var(--font-size-xs);
}

.declaration-evidence {
  width: 100%;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.question-comment {
  margin: 0.5rem 0 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  font-style: italic;
}

.orphaned-section h2 {
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 0.4rem;
}

.orphaned-hint {
  margin: 0 0 0.75rem;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.orphaned-from {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
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
