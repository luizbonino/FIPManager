<template>
  <div class="fip-detail-view">
    <div v-if="isLoading" class="loading">
      <p>{{ $t('common.loading') }}</p>
    </div>

    <div v-else-if="error" class="error-message">
      <p>{{ error }}</p>
    </div>

    <div v-else-if="fip" class="fip-detail-content">
      <div class="fip-header">
        <h1>{{ fip.title || $t('fip.title') }}</h1>
        <span class="read-only-badge">{{ $t('fip.readOnly') }}</span>
      </div>

      <div class="fip-meta">
        <p><strong>{{ $t('common.id') }}:</strong> {{ fip.id }}</p>
        <p v-if="fip.description"><strong>{{ $t('common.description') }}:</strong> {{ fip.description }}</p>
        <p v-if="fip.createdAt"><strong>{{ $t('common.created') }}:</strong> {{ formatDate(fip.createdAt) }}</p>
        <p v-if="fip.updatedAt"><strong>{{ $t('common.updated') }}:</strong> {{ formatDate(fip.updatedAt) }}</p>
      </div>

      <div class="fip-sections">
        <section v-if="fip.metadata" class="fip-section">
          <h2>{{ $t('fip.metadata') }}</h2>
          <pre class="json-content">{{ JSON.stringify(fip.metadata, null, 2) }}</pre>
        </section>

        <section v-if="fip.content" class="fip-section">
          <h2>{{ $t('fip.content') }}</h2>
          <div class="content-display">{{ fip.content }}</div>
        </section>

        <section v-if="fip.ontologyMappings && fip.ontologyMappings.length > 0" class="fip-section">
          <h2>{{ $t('fip.ontologyMappings') }}</h2>
          <div class="mappings-list">
            <div v-for="(mapping, index) in fip.ontologyMappings" :key="index" class="mapping-item">
              <p><strong>{{ $t('fip.source') }}:</strong> {{ mapping.source }}</p>
              <p><strong>{{ $t('fip.target') }}:</strong> {{ mapping.target }}</p>
              <p v-if="mapping.type"><strong>{{ $t('fip.type') }}:</strong> {{ mapping.type }}</p>
            </div>
          </div>
        </section>
      </div>

      <div class="fip-actions">
        <button @click="exportJson" class="btn btn-secondary">{{ $t('fip.exportJson') }}</button>
        <button @click="exportCsv" class="btn btn-secondary">{{ $t('fip.exportCsv') }}</button>
      </div>
    </div>

    <div v-else class="not-found">
      <h2>{{ $t('fip.notFound') }}</h2>
      <router-link to="/workspace" class="btn btn-primary">{{ $t('common.back') }}</router-link>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { get } from '@/api/client'
import { useI18n } from 'vue-i18n'

type Fip = {
  id: string
  title: string
  description?: string
  content?: string
  metadata?: Record<string, unknown>
  ontologyMappings?: Array<{
    source: string
    target: string
    type?: string
  }>
  createdAt?: string
  updatedAt?: string
}

const route = useRoute()
const { t } = useI18n()

const fip = ref<Fip | null>(null)
const isLoading = ref(true)
const error = ref<string | null>(null)

const fipId = computed(() => route.params.id as string)

const formatDate = (dateString: string): string => {
  return new Date(dateString).toLocaleString()
}

const fetchFip = async () => {
  isLoading.value = true
  error.value = null

  try {
    const response = await get<Fip>(`/fips/${fipId.value}`)
    fip.value = response
  } catch (err) {
    error.value = t('fip.notFound')
  } finally {
    isLoading.value = false
  }
}

const exportJson = () => {
  if (!fip.value) return
  const data = JSON.stringify(fip.value, null, 2)
  const blob = new Blob([data], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `fip-${fip.value.id}.json`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

const exportCsv = () => {
  if (!fip.value) return
  let csv = 'Field,Value\n'
  csv += `ID,${fip.value.id || ''}\n`
  csv += `Title,${fip.value.title || ''}\n`
  csv += `Description,${fip.value.description || ''}\n`
  csv += `Created,${fip.value.createdAt || ''}\n`
  csv += `Updated,${fip.value.updatedAt || ''}\n`

  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `fip-${fip.value.id}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

onMounted(() => {
  fetchFip()
})
</script>

<style scoped>
.fip-detail-view {
  max-width: 800px;
  margin: 0 auto;
  padding: 1rem;
}

.fip-detail-content {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.fip-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.fip-header h1 {
  font-size: 1.75rem;
  color: var(--color-primary);
  margin: 0;
  flex: 1;
}

.read-only-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 4px;
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
  font-size: 0.875rem;
  font-weight: 500;
}

.fip-meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  padding: 1rem;
  background-color: var(--color-background);
  border: 1px solid var(--color-border);
  border-radius: 8px;
}

.fip-meta p {
  margin: 0.25rem 0;
  color: var(--color-text);
}

.fip-meta strong {
  color: var(--color-primary);
}

.fip-sections {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.fip-section {
  background-color: var(--color-background);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 1.5rem;
}

.fip-section h2 {
  font-size: 1.25rem;
  color: var(--color-primary);
  margin-bottom: 1rem;
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 0.5rem;
}

.json-content {
  background-color: var(--color-hover);
  padding: 1rem;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 0.875rem;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.content-display {
  padding: 1rem;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background-color: var(--color-background);
  min-height: 100px;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.mappings-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.mapping-item {
  padding: 1rem;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background-color: var(--color-hover);
}

.mapping-item p {
  margin: 0.25rem 0;
  color: var(--color-text);
}

.mapping-item strong {
  color: var(--color-primary);
}

.fip-actions {
  display: flex;
  gap: 1rem;
  justify-content: center;
  padding: 1rem;
}

.btn {
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 4px;
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-primary {
  background-color: var(--color-primary);
  color: var(--color-primary-text);
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
}

.btn:hover {
  opacity: 0.9;
}

.loading,
.not-found {
  text-align: center;
  padding: 4rem 2rem;
}

.loading {
  color: var(--color-secondary);
}

.not-found {
  color: var(--color-error);
}

.error-message {
  text-align: center;
  padding: 2rem;
  color: var(--color-error);
  background-color: var(--color-error-bg);
  border-radius: 8px;
}

@media (max-width: 768px) {
  .fip-detail-view {
    padding: 0.5rem;
  }

  .fip-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .fip-header h1 {
    font-size: 1.5rem;
  }

  .fip-meta {
    grid-template-columns: 1fr;
  }

  .fip-actions {
    flex-wrap: wrap;
  }

  .btn {
    flex: 1;
    min-width: 120px;
  }
}
</style>
