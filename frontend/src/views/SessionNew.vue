<template>
  <div class="session-new-view">
    <h1>{{ $t('sessionAdmin.newTitle') }}</h1>

    <form class="session-form" @submit.prevent="onSubmit">
      <label class="field">
        <span>{{ $t('sessionAdmin.titleLabel') }} *</span>
        <input v-model="title" type="text" required />
      </label>

      <label class="field">
        <span>{{ $t('sessionAdmin.knowledgeModel') }} *</span>
        <select v-model="kmKey" required>
          <option value="" disabled>{{ $t('fipNew.chooseQuestionnaire') }}</option>
          <optgroup v-for="group in groupedKms" :key="group.key" :label="$t(group.labelKey)">
            <option v-for="km in group.items" :key="`${km.id}@${km.version}`" :value="`${km.id}@${km.version}`">
              {{ resolveLang(km.title, locale) ?? km.id }} (v{{ km.version }})
            </option>
          </optgroup>
        </select>
      </label>

      <label class="field">
        <span>{{ $t('sessionAdmin.defaultLanguage') }}</span>
        <select v-model="defaultLanguage">
          <option v-for="l in SUPPORTED_LOCALES" :key="l" :value="l">{{ $t(`languages.${l}`) }}</option>
        </select>
      </label>

      <div v-if="isSelectedKmPrivate" class="private-model-notice">
        <p>{{ $t('sessionAdmin.privateModelNotice') }}</p>
        <label class="checkbox-field">
          <input v-model="makeModelLinkVisible" type="checkbox" />
          <span>{{ $t('sessionAdmin.makeModelLinkVisible') }}</span>
        </label>
      </div>

      <p v-if="submitError" class="form-error">{{ submitError }}</p>

      <button type="submit" class="btn btn-primary" :disabled="submitting || !kmKey">
        {{ $t('sessionAdmin.create') }}
      </button>
    </form>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { listKnowledgeModels, patchKnowledgeModel } from '@/api/knowledgeModels'
import { createSession } from '@/api/sessions'
import { resolveLang } from '@/lib/lang'
import { SUPPORTED_LOCALES } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import type { KnowledgeModelSummary } from '@/types/api'

// Spec 02 §4.1 / spec 04 §4: options grouped System/Mine/Public via `isSystem`/`ownerId`.
const router = useRouter()
const { locale, t } = useI18n()
const authStore = useAuthStore()

const title = ref('')
const kmKey = ref('')
const defaultLanguage = ref(locale.value)
const knowledgeModels = ref<KnowledgeModelSummary[]>([])
const submitting = ref(false)
const submitError = ref<string | null>(null)
// Defaults to checked (spec 02 §4.1): a private model picked here would
// otherwise 404 for every participant (`questionnaire_not_found`), since
// `GET /fips/{joinCode}` reads it as them, not as the session's owner.
const makeModelLinkVisible = ref(true)

const selectedKm = computed(() =>
  knowledgeModels.value.find((km) => `${km.id}@${km.version}` === kmKey.value) ?? null
)
const isSelectedKmPrivate = computed(() => selectedKm.value?.visibility === 'private')

const groupedKms = computed(() => {
  const userId = authStore.user?.id ?? null
  const system = knowledgeModels.value.filter((km) => km.isSystem)
  const mine = knowledgeModels.value.filter((km) => !km.isSystem && userId !== null && km.ownerId === userId)
  const publicOnes = knowledgeModels.value.filter(
    (km) => !km.isSystem && (userId === null || km.ownerId !== userId)
  )
  return [
    { key: 'system', labelKey: 'km.system', items: system },
    { key: 'mine', labelKey: 'km.mine', items: mine },
    { key: 'public', labelKey: 'km.public', items: publicOnes },
  ]
})

async function onSubmit() {
  if (!kmKey.value) return
  const [id, version] = kmKey.value.split('@')
  submitting.value = true
  submitError.value = null
  try {
    if (isSelectedKmPrivate.value && makeModelLinkVisible.value) {
      await patchKnowledgeModel(id, version, { visibility: 'link' })
      if (selectedKm.value) selectedKm.value.visibility = 'link'
    }
    const created = await createSession({
      title: title.value,
      questionnaireRef: { id, version },
      defaultLanguage: defaultLanguage.value,
    })
    await router.push(`/sessions/${created.id}`)
  } catch {
    submitError.value = t('errors.serverError')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  const result = await listKnowledgeModels({ status: 'published' })
  knowledgeModels.value = result.items
})
</script>

<style scoped>
.session-new-view {
  max-width: 500px;
  margin: 0 auto;
  padding: 1rem;
}

.session-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
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
}

.private-model-notice {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem;
  border-radius: var(--border-radius-sm);
  background-color: var(--color-hover);
  font-size: var(--font-size-sm);
}

.private-model-notice p {
  margin: 0;
  color: var(--color-text-secondary);
}

.checkbox-field {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.btn {
  min-height: 44px;
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: var(--border-radius-sm);
  background-color: var(--color-primary);
  color: var(--color-primary-text);
  font-size: 1rem;
  font-weight: 500;
}

.btn:disabled {
  opacity: 0.7;
}
</style>
