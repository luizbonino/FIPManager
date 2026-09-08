<template>
  <div class="fip-new-view">
    <h1>{{ $t('fipNew.title') }}</h1>

    <section v-if="!selectedKm" class="km-choice">
      <h2>{{ $t('fipNew.chooseQuestionnaire') }}</h2>
      <p v-if="loadingKms">{{ $t('common.loading') }}</p>
      <ul v-else class="km-list">
        <li v-for="km in knowledgeModels" :key="`${km.id}@${km.version}`">
          <label class="km-option">
            <input
              type="radio"
              name="km"
              :value="`${km.id}@${km.version}`"
              v-model="selectedKmKey"
            />
            <span>{{ resolveLang(km.title, locale) ?? km.id }} (v{{ km.version }})</span>
          </label>
        </li>
      </ul>
    </section>

    <form v-else class="community-form" @submit.prevent="onSubmit">
      <h2>{{ $t('community.heading') }}</h2>

      <label class="field">
        <span>{{ $t('community.name') }} *</span>
        <input v-model="community.name" type="text" required :placeholder="$t('community.namePlaceholder')" />
      </label>

      <label class="field">
        <span>{{ $t('community.description') }}</span>
        <textarea v-model="community.description" rows="3" />
      </label>

      <label class="field">
        <span>{{ $t('community.domain') }}</span>
        <input v-model="community.domain" type="text" :placeholder="$t('community.domainPlaceholder')" />
      </label>

      <label class="field">
        <span>{{ $t('community.dataSteward') }}</span>
        <input
          v-model="orcid"
          type="text"
          :placeholder="$t('community.dataStewardPlaceholder')"
          @blur="validateOrcid"
        />
        <span v-if="orcidError" class="field-error">{{ $t('community.orcidInvalid') }}</span>
      </label>

      <p v-if="submitError" class="form-error">{{ submitError }}</p>

      <div class="form-actions">
        <button type="button" class="btn btn-secondary" @click="selectedKmKey = ''">{{ $t('common.back') }}</button>
        <button type="submit" class="btn btn-primary" :disabled="submitting">{{ $t('fipNew.submit') }}</button>
      </div>
    </form>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { listKnowledgeModels } from '@/api/knowledgeModels'
import { createFip } from '@/api/fips'
import { resolveLang } from '@/lib/lang'
import type { KnowledgeModelSummary } from '@/types/api'

// Spec 02 §3: GET /api/knowledge-models?status=published -> radio list, then the §2.1 community form.
const router = useRouter()
const { locale, t } = useI18n()

const knowledgeModels = ref<KnowledgeModelSummary[]>([])
const loadingKms = ref(true)
const selectedKmKey = ref('')
const submitting = ref(false)
const submitError = ref<string | null>(null)
const orcidError = ref(false)

const community = ref({ name: '', description: '', domain: '' })
const orcid = ref('')

const selectedKm = computed(() =>
  selectedKmKey.value
    ? knowledgeModels.value.find((km) => `${km.id}@${km.version}` === selectedKmKey.value)
    : null
)

const ORCID_PATTERN = /^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$/

function validateOrcid() {
  orcidError.value = orcid.value.trim() !== '' && !ORCID_PATTERN.test(orcid.value.trim())
}

async function onSubmit() {
  validateOrcid()
  const km = selectedKm.value
  if (!km) return
  submitting.value = true
  submitError.value = null
  try {
    const created = await createFip({
      questionnaireRef: { id: km.id, version: km.version },
      language: locale.value,
      community: {
        name: community.value.name,
        description: community.value.description || null,
        domain: community.value.domain || null,
        links: [],
        dataSteward: orcid.value.trim() ? { orcid: orcid.value.trim() } : null,
      },
    })
    await router.push(`/fips/${created.id}/edit`)
  } catch {
    submitError.value = t('errors.serverError')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  loadingKms.value = true
  try {
    const result = await listKnowledgeModels({ status: 'published' })
    knowledgeModels.value = result.items
  } finally {
    loadingKms.value = false
  }
})
</script>

<style scoped>
.fip-new-view {
  max-width: 600px;
  margin: 0 auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.km-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.km-option {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  min-height: 44px;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  cursor: pointer;
}

.km-option input {
  width: 1.25rem;
  height: 1.25rem;
}

.community-form {
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
.field textarea {
  min-height: 44px;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  font-size: 1rem;
  font-family: inherit;
}

.field-error,
.form-error {
  color: var(--color-error);
  font-size: var(--font-size-sm);
}

.form-actions {
  display: flex;
  gap: 0.75rem;
}

.btn {
  min-height: 44px;
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: var(--border-radius-sm);
  font-size: 1rem;
  font-weight: 500;
}

.btn-primary {
  background-color: var(--color-primary);
  color: var(--color-primary-text);
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
}

.btn:disabled {
  opacity: 0.7;
}
</style>
