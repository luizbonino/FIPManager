<template>
  <div class="km-new-view">
    <h1>{{ $t('km.new') }}</h1>

    <section class="card">
      <h2>{{ $t('km.fromScratch') }}</h2>
      <form class="card-form" @submit.prevent="onCreateFromScratch">
        <label class="field">
          <span>{{ $t('common.name') }} *</span>
          <input v-model="scratchTitle" type="text" required />
        </label>
        <label class="field">
          <span>{{ $t('common.id') }}</span>
          <input v-model="scratchId" type="text" :placeholder="$t('km.new')" />
        </label>
        <p v-if="scratchError" class="form-error">{{ scratchError }}</p>
        <button type="submit" class="btn btn-primary" :disabled="submittingScratch">{{ $t('km.new') }}</button>
      </form>
    </section>

    <section class="card">
      <h2>{{ $t('km.fork') }}</h2>
      <p v-if="loadingModels">{{ $t('common.loading') }}</p>
      <form v-else class="card-form" @submit.prevent="onForkSubmit">
        <label class="field">
          <span>{{ $t('km.title') }}</span>
          <select v-model="forkKey" required>
            <option value="" disabled>{{ $t('km.fork') }}</option>
            <option v-for="model in models" :key="`${model.id}@${model.version}`" :value="`${model.id}@${model.version}`">
              {{ resolveLang(model.title, locale) ?? model.id }} ({{ model.id }}@{{ model.version }})
            </option>
          </select>
        </label>
        <p v-if="forkError" class="form-error">{{ forkError }}</p>
        <button type="submit" class="btn btn-primary" :disabled="!forkKey || submittingFork">{{ $t('km.fork') }}</button>
      </form>
    </section>

    <section class="card">
      <h2>{{ $t('km.import') }}</h2>
      <KmImportDialog :errors="importErrors" @import="onImport" />
    </section>
  </div>
</template>

<script lang="ts" setup>
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ApiResponseError } from '@/api/client'
import { createKnowledgeModel, forkKnowledgeModel, importKnowledgeModel, listKnowledgeModels } from '@/api/knowledgeModels'
import { resolveLang } from '@/lib/lang'
import KmImportDialog from '@/components/KmImportDialog.vue'
import type { ContentError } from '@/lib/kmContent'
import type { KnowledgeModelSummary } from '@/types/api'

// Spec 04 §5: three cards — from scratch, fork, import.
const { locale, t } = useI18n()
const router = useRouter()

const scratchTitle = ref('')
const scratchId = ref('')
const scratchError = ref<string | null>(null)
const submittingScratch = ref(false)

const models = ref<KnowledgeModelSummary[]>([])
const loadingModels = ref(true)
const forkKey = ref('')
const forkError = ref<string | null>(null)
const submittingFork = ref(false)

const importErrors = ref<ContentError[]>([])

async function onCreateFromScratch() {
  submittingScratch.value = true
  scratchError.value = null
  try {
    const created = await createKnowledgeModel({
      id: scratchId.value.trim() || undefined,
      title: { en: scratchTitle.value.trim() },
    })
    await router.push(`/knowledge-models/${created.id}/${created.version}/edit`)
  } catch (err) {
    scratchError.value =
      err instanceof ApiResponseError && err.data.detail === 'model_id_taken' ? t('km.idTaken') : t('errors.serverError')
  } finally {
    submittingScratch.value = false
  }
}

async function onForkSubmit() {
  if (!forkKey.value) return
  const [id, version] = forkKey.value.split('@')
  submittingFork.value = true
  forkError.value = null
  try {
    const created = await forkKnowledgeModel(id, version)
    await router.push(`/knowledge-models/${created.id}/${created.version}/edit`)
  } catch {
    forkError.value = t('errors.serverError')
  } finally {
    submittingFork.value = false
  }
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

onMounted(async () => {
  loadingModels.value = true
  try {
    const result = await listKnowledgeModels()
    models.value = result.items
  } finally {
    loadingModels.value = false
  }
})
</script>

<style scoped>
.km-new-view {
  max-width: 600px;
  margin: 0 auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.card {
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  padding: 1.25rem;
}

.card h2 {
  margin: 0 0 0.75rem;
  font-size: 1.1rem;
}

.card-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.field input,
.field select {
  min-height: 44px;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  font-size: 1rem;
  font-family: inherit;
}

.form-error {
  color: var(--color-error);
  font-size: var(--font-size-sm);
  margin: 0;
}

.btn {
  align-self: flex-start;
  min-height: 44px;
  padding: 0.6rem 1.4rem;
  border: none;
  border-radius: var(--border-radius-sm);
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
}

.btn-primary {
  background-color: var(--color-primary);
  color: var(--color-primary-text);
}

.btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}
</style>
