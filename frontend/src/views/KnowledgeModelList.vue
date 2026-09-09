<template>
  <div class="km-list-view">
    <div class="header-row">
      <h1>{{ $t('km.title') }}</h1>
      <div class="header-actions">
        <button type="button" class="btn btn-secondary" @click="showImport = !showImport">
          {{ $t('km.import') }}
        </button>
        <router-link to="/knowledge-models/new" class="btn btn-primary">{{ $t('km.new') }}</router-link>
      </div>
    </div>

    <div v-if="showImport" class="import-panel">
      <KmImportDialog :errors="importErrors" @import="onImport" />
    </div>

    <div v-if="loading" class="loading">
      <p>{{ $t('common.loading') }}</p>
    </div>

    <div v-else class="km-blocks">
      <section v-for="block in blocks" :key="block.key" class="km-block">
        <h2>{{ $t(block.labelKey) }}</h2>
        <p v-if="block.key === 'unownedDrafts'" class="block-hint">{{ $t('km.unownedDraftHint') }}</p>
        <div v-if="block.items.length > 0" class="km-rows">
          <div v-for="model in block.items" :key="`${model.id}@${model.version}`" class="km-row">
            <div class="km-row-main">
              <span class="km-name">{{ resolveLang(model.title, locale) ?? model.id }}</span>
              <span class="ref-chip">{{ model.id }}@{{ model.version }}</span>
              <span class="status-chip" :class="`status-${model.status}`">{{ $t(`km.${model.status}`) }}</span>
            </div>
            <span class="meta">{{ $t('km.questions', { count: model.questionCount }) }}</span>
            <p v-if="model.forkedFrom" class="fork-note">
              {{ $t('km.forkOf', { id: model.forkedFrom.id, version: model.forkedFrom.version }) }}
            </p>
            <div class="km-row-actions">
              <router-link :to="`/knowledge-models/${model.id}/${model.version}`">{{ $t('common.view') }}</router-link>
              <button type="button" class="link-btn" @click="onFork(model)">{{ $t('km.fork') }}</button>
              <router-link
                v-if="(model.status === 'draft' && model.ownerId === userId) || (model.isUnownedDraft === true && isAdmin)"
                :to="`/knowledge-models/${model.id}/${model.version}/edit`"
              >
                {{ $t('km.edit') }}
              </router-link>
            </div>
          </div>
        </div>
        <p v-else class="empty-state">{{ $t('km.noModels') }}</p>
      </section>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { forkKnowledgeModel, importKnowledgeModel, listKnowledgeModels } from '@/api/knowledgeModels'
import { ApiResponseError } from '@/api/client'
import { resolveLang } from '@/lib/lang'
import { useAuthStore } from '@/stores/auth'
import KmImportDialog from '@/components/KmImportDialog.vue'
import type { ContentError } from '@/lib/kmContent'
import type { KnowledgeModelSummary } from '@/types/api'

// Spec 04 §5: three blocks (Mine, System, Public); anonymous visitors see
// System + Public only (the API already filters to published+public+own).
const { locale } = useI18n()
const router = useRouter()
const authStore = useAuthStore()

const models = ref<KnowledgeModelSummary[]>([])
const loading = ref(true)
const showImport = ref(false)
const importErrors = ref<ContentError[]>([])

const userId = computed(() => authStore.user?.id ?? null)
const isAdmin = computed(() => authStore.user?.role === 'admin')

// spec 04 §5 addition: shipped drafts imported from data/ (ownerId NULL,
// isSystem false) surface to admins only, in their own group above "Mine",
// since an admin can edit and claim one on first write; a normal user
// never sees this group even if the API happens to send such rows.
const blocks = computed(() => {
  const mine = models.value.filter((m) => userId.value !== null && m.ownerId === userId.value)
  const system = models.value.filter((m) => m.isSystem)
  const publicOnes = models.value.filter(
    (m) => !m.isSystem && !m.isUnownedDraft && (userId.value === null || m.ownerId !== userId.value)
  )
  const result = []
  if (isAdmin.value) {
    const unownedDrafts = models.value.filter((m) => m.isUnownedDraft)
    result.push({ key: 'unownedDrafts', labelKey: 'km.unownedDrafts', items: unownedDrafts })
  }
  result.push(
    { key: 'mine', labelKey: 'km.mine', items: mine },
    { key: 'system', labelKey: 'km.system', items: system },
    { key: 'public', labelKey: 'km.public', items: publicOnes }
  )
  return result
})

async function load() {
  loading.value = true
  try {
    const result = await listKnowledgeModels()
    models.value = result.items
  } finally {
    loading.value = false
  }
}

async function onFork(model: KnowledgeModelSummary) {
  const created = await forkKnowledgeModel(model.id, model.version)
  await router.push(`/knowledge-models/${created.id}/${created.version}/edit`)
}

async function onImport(document: unknown) {
  importErrors.value = []
  try {
    const created = await importKnowledgeModel({ document })
    await router.push(`/knowledge-models/${created.id}/${created.version}/edit`)
  } catch (err) {
    if (err instanceof ApiResponseError && Array.isArray((err.data as { errors?: unknown }).errors)) {
      importErrors.value = (err.data as unknown as { errors: ContentError[] }).errors
    }
  }
}

onMounted(load)
</script>

<style scoped>
.km-list-view {
  max-width: 1000px;
  margin: 0 auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.header-row h1 {
  margin: 0;
  color: var(--color-primary);
}

.header-actions {
  display: flex;
  gap: 0.75rem;
}

.import-panel {
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  padding: 1rem;
}

.loading {
  text-align: center;
  padding: 2rem;
}

.km-blocks {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.km-block h2 {
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 0.4rem;
  margin: 0 0 0.75rem;
}

.block-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin: -0.5rem 0 0.75rem;
}

.km-rows {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.km-row {
  display: grid;
  gap: 0.35rem;
  padding: 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
}

.km-row-main {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.km-name {
  font-weight: var(--font-weight-medium);
}

.ref-chip {
  font-family: monospace;
  font-size: var(--font-size-xs);
  color: var(--color-id-chip-text);
  background-color: var(--color-id-chip-bg);
  padding: 0.1rem 0.4rem;
  border-radius: var(--border-radius-sm);
}

.status-chip {
  font-size: var(--font-size-xs);
  color: var(--color-chip-text);
  background-color: var(--color-chip-bg);
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
}

.status-published {
  background-color: var(--status-current-bg);
  color: var(--status-current-fg);
}

.meta,
.fork-note {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin: 0;
}

.km-row-actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  font-size: var(--font-size-sm);
}

.km-row-actions a,
.link-btn {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
}

.link-btn {
  background: none;
  border: none;
  color: var(--color-link);
  cursor: pointer;
  padding: 0;
  font-size: var(--font-size-sm);
}

.empty-state {
  color: var(--color-text-secondary);
  padding: 1rem 0;
}

.btn {
  min-height: 44px;
  padding: 0.5rem 1.2rem;
  border: none;
  border-radius: var(--border-radius-sm);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  font-size: var(--font-size-sm);
  cursor: pointer;
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
