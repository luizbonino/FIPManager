<template>
  <div class="workspace-view">
    <h1>{{ $t('workspace.title') }}</h1>

    <div v-if="isLoading" class="loading">
      <p>{{ $t('workspace.loading') }}</p>
    </div>

    <div v-else-if="error" class="error-message">
      <p>{{ $t('workspace.error') }}</p>
    </div>

    <div v-else class="workspace-content">
      <section class="workspace-section">
        <div class="section-head">
          <h2>{{ $t('workspace.myFips') }}</h2>
          <router-link to="/fips/new" class="btn btn-primary">{{ $t('workspace.createNewFip') }}</router-link>
        </div>
        <div v-if="myFips.length > 0" class="fip-rows">
          <div v-for="fip in myFips" :key="fip.id" class="fip-row">
            <div class="fip-row-main">
              <span class="fip-name">{{ fip.community?.name || fip.id }}</span>
              <span class="visibility-chip">{{ $t(`visibility.${fip.visibility}`) }}</span>
            </div>
            <span class="questionnaire-ref">{{ fip.questionnaireId }} v{{ fip.questionnaireVersion }}</span>
            <ProgressBar :answered="answeredCount(fip.answers)" :total="21" />
            <span class="updated">{{ $t('common.updated') }}: {{ formatDate(fip.updatedAt) }}</span>
            <div class="fip-row-actions">
              <router-link :to="`/fips/${fip.id}/edit`">{{ $t('fip.edit') }}</router-link>
              <router-link :to="`/fips/${fip.id}`">{{ $t('common.view') }}</router-link>
              <a :href="fipExportJsonUrl(fip.id)">{{ $t('fip.exportJson') }}</a>
              <a :href="fipExportCsvUrl(fip.id)">{{ $t('fip.exportCsv') }}</a>
              <button type="button" class="delete-link" @click="onDeleteFip(fip.id)">{{ $t('common.delete') }}</button>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">
          <p>{{ $t('workspace.noFips') }}</p>
        </div>
      </section>

      <section class="workspace-section">
        <div class="section-head">
          <h2>{{ $t('workspace.mySessions') }}</h2>
          <router-link to="/sessions/new" class="btn btn-primary">{{ $t('workspace.createNewSession') }}</router-link>
        </div>
        <div v-if="mySessions.length > 0" class="items-grid">
          <router-link v-for="session in mySessions" :key="session.id" :to="`/sessions/${session.id}`" class="item-card">
            <h3>{{ session.title }}</h3>
            <p class="item-meta">{{ session.joinCode }}</p>
            <span v-if="session.status === 'closed'" class="item-badge">{{ $t('sessionAdmin.closed') }}</span>
          </router-link>
        </div>
        <div v-else class="empty-state">
          <p>{{ $t('workspace.noSessions') }}</p>
        </div>
      </section>

      <section class="workspace-section">
        <h2>{{ $t('workspace.myKnowledgeModels') }}</h2>
        <div v-if="myKnowledgeModels.length > 0" class="items-grid">
          <div v-for="km in myKnowledgeModels" :key="`${km.id}@${km.version}`" class="item-card">
            <h3>{{ resolveLang(km.title, locale) ?? km.id }}</h3>
            <p class="item-meta">v{{ km.version }} · {{ km.status }}</p>
          </div>
        </div>
        <div v-else class="empty-state">
          <p>{{ $t('workspace.noKnowledgeModels') }}</p>
        </div>
      </section>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { myFips as apiMyFips, myKnowledgeModels as apiMyKms, mySessions as apiMySessions } from '@/api/me'
import { deleteFip, fipExportCsvUrl, fipExportJsonUrl } from '@/api/fips'
import { answeredCount } from '@/lib/progress'
import { resolveLang } from '@/lib/lang'
import ProgressBar from '@/components/ProgressBar.vue'
import type { FipOut, KnowledgeModelSummary, SessionOut } from '@/types/api'

// Spec 02 §3: three lists from GET /api/me/{fips,sessions,knowledge-models}.
const { locale, t } = useI18n()

const myFips = ref<FipOut[]>([])
const mySessions = ref<SessionOut[]>([])
const myKnowledgeModels = ref<KnowledgeModelSummary[]>([])
const isLoading = ref(true)
const error = ref<string | null>(null)

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString()
}

async function onDeleteFip(id: string) {
  if (!confirm(t('common.deleteFipConfirm'))) return
  await deleteFip(id)
  myFips.value = myFips.value.filter((f) => f.id !== id)
}

async function fetchData() {
  isLoading.value = true
  error.value = null
  try {
    const [fipsResponse, sessionsResponse, kmResponse] = await Promise.all([
      apiMyFips(),
      apiMySessions(),
      apiMyKms(),
    ])
    myFips.value = fipsResponse.items
    mySessions.value = sessionsResponse.items
    myKnowledgeModels.value = kmResponse.items
  } catch {
    error.value = 'error'
  } finally {
    isLoading.value = false
  }
}

onMounted(fetchData)
</script>

<style scoped>
.workspace-view {
  max-width: 1000px;
  margin: 0 auto;
  padding: 1rem;
}

.workspace-view h1 {
  font-size: 1.75rem;
  margin-bottom: 1.5rem;
  color: var(--color-primary);
}

.workspace-content {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.workspace-section {
  background-color: var(--color-background);
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  padding: 1.25rem;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 0.5rem;
}

.section-head h2 {
  margin: 0;
}

.fip-rows {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.fip-row {
  display: grid;
  gap: 0.4rem;
  padding: 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
}

.fip-row-main {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.fip-name {
  font-weight: var(--font-weight-medium);
}

.visibility-chip {
  font-size: var(--font-size-xs);
  color: var(--color-chip-text);
  background-color: var(--color-chip-bg);
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
}

.questionnaire-ref,
.updated {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.fip-row-actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  font-size: var(--font-size-sm);
}

.fip-row-actions a,
.delete-link {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
}

.delete-link {
  background: none;
  border: none;
  color: var(--color-error);
  cursor: pointer;
  padding: 0;
  font-size: var(--font-size-sm);
}

.items-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 1rem;
}

.item-card {
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  padding: 1rem;
  color: var(--color-text);
  text-decoration: none;
  display: block;
}

.item-card h3 {
  font-size: 1rem;
  margin: 0 0 0.35rem;
}

.item-meta {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin: 0;
}

.item-badge {
  display: inline-block;
  margin-top: 0.5rem;
  padding: 0.2rem 0.5rem;
  border-radius: var(--border-radius-sm);
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
  font-size: var(--font-size-xs);
}

.empty-state {
  text-align: center;
  padding: 1.5rem;
  color: var(--color-text-secondary);
}

.loading,
.error-message {
  text-align: center;
  padding: 3rem 1rem;
}

.btn {
  min-height: 44px;
  padding: 0.5rem 1rem;
  border-radius: var(--border-radius-sm);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
}

.btn-primary {
  background-color: var(--color-primary);
  color: var(--color-primary-text);
}

@media (max-width: 768px) {
  .items-grid {
    grid-template-columns: 1fr;
  }
}
</style>
