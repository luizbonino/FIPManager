<template>
  <div class="workspace-view">
    <h1>{{ $t('workspace.title') }}</h1>

    <div v-if="isLoading" class="loading">
      <p>{{ $t('workspace.loading') }}</p>
    </div>

    <div v-else-if="error" class="error-message">
      <p>{{ $t('workspace.error') }}: {{ error }}</p>
    </div>

    <div v-else class="workspace-content">
      <section class="workspace-section">
        <h2>{{ $t('workspace.myFips') }}</h2>
        <div v-if="myFips.length > 0" class="items-grid">
          <div v-for="fip in myFips" :key="fip.id" class="item-card" @click="navigateToFip(fip.id)">
            <h3>{{ fip.title || $t('fip.title') }}</h3>
            <p class="item-meta">{{ fip.id }}</p>
            <span class="item-badge">{{ $t('fip.readOnly') }}</span>
          </div>
        </div>
        <div v-else class="empty-state">
          <p>{{ $t('workspace.noFips') }}</p>
        </div>
      </section>

      <section class="workspace-section">
        <h2>{{ $t('workspace.mySessions') }}</h2>
        <div v-if="mySessions.length > 0" class="items-grid">
          <div v-for="session in mySessions" :key="session.id" class="item-card">
            <h3>{{ session.name || $t('session.joinTitle') }}</h3>
            <p class="item-meta">{{ session.id }}</p>
            <span v-if="session.joinCode" class="item-badge">{{ session.joinCode }}</span>
          </div>
        </div>
        <div v-else class="empty-state">
          <p>{{ $t('workspace.noSessions') }}</p>
        </div>
      </section>

      <section class="workspace-section">
        <h2>{{ $t('workspace.myKnowledgeModels') }}</h2>
        <div v-if="myKnowledgeModels.length > 0" class="items-grid">
          <div v-for="km in myKnowledgeModels" :key="km.id" class="item-card">
            <h3>{{ km.name || $t('workspace.myKnowledgeModels') }}</h3>
            <p class="item-meta">{{ km.id }}</p>
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
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { get } from '@/api/client'
import { useI18n } from 'vue-i18n'

type Fip = {
  id: string
  title: string
  description?: string
  createdAt: string
  updatedAt: string
}

type Session = {
  id: string
  name: string
  joinCode: string
  isActive: boolean
  createdAt: string
}

type KnowledgeModel = {
  id: string
  name: string
  description?: string
  createdAt: string
}

const myFips = ref<Fip[]>([])
const mySessions = ref<Session[]>([])
const myKnowledgeModels = ref<KnowledgeModel[]>([])
const isLoading = ref(true)
const error = ref<string | null>(null)

const router = useRouter()
const { t } = useI18n()

const navigateToFip = (fipId: string) => {
  router.push(`/fips/${fipId}`)
}

const fetchData = async () => {
  isLoading.value = true
  error.value = null

  try {
    const [fipsResponse, sessionsResponse, kmResponse] = await Promise.all([
      get<Fip[]>('/me/fips'),
      get<Session[]>('/me/sessions'),
      get<KnowledgeModel[]>('/me/knowledge-models'),
    ])

    myFips.value = fipsResponse || []
    mySessions.value = sessionsResponse || []
    myKnowledgeModels.value = kmResponse || []
  } catch (err) {
    error.value = err instanceof Error ? err.message : t('errors.serverError')
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.workspace-view {
  max-width: 1200px;
  margin: 0 auto;
  padding: 1rem;
}

.workspace-view h1 {
  font-size: 2rem;
  margin-bottom: 2rem;
  color: var(--color-primary);
  text-align: center;
}

.workspace-content {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.workspace-section {
  background-color: var(--color-background);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 1.5rem;
}

.workspace-section h2 {
  font-size: 1.25rem;
  margin-bottom: 1rem;
  color: var(--color-text);
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 0.5rem;
}

.items-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}

.item-card {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 1rem;
  cursor: pointer;
  transition: all 0.2s ease;
  background-color: var(--color-background);
}

.item-card:hover {
  border-color: var(--color-primary);
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.1);
  transform: translateY(-2px);
}

.item-card h3 {
  font-size: 1rem;
  margin-bottom: 0.5rem;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-meta {
  font-size: 0.875rem;
  color: var(--color-secondary);
  margin-bottom: 0.5rem;
}

.item-badge {
  display: inline-block;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  background-color: var(--color-primary);
  color: var(--color-primary-text);
  font-size: 0.75rem;
  font-weight: 500;
}

.empty-state {
  text-align: center;
  padding: 2rem;
  color: var(--color-secondary);
}

.loading {
  text-align: center;
  padding: 4rem 2rem;
  color: var(--color-secondary);
}

.error-message {
  text-align: center;
  padding: 2rem;
  color: var(--color-error);
  background-color: var(--color-error-bg);
  border-radius: 8px;
}

@media (max-width: 768px) {
  .workspace-view {
    padding: 0.5rem;
  }

  .workspace-view h1 {
    font-size: 1.5rem;
    margin-bottom: 1rem;
  }

  .workspace-section {
    padding: 1rem;
  }

  .items-grid {
    grid-template-columns: 1fr;
  }

  .loading,
  .error-message {
    padding: 2rem 1rem;
  }
}
</style>
