<template>
  <div class="fip-new-view">
    <h1>{{ $t('fipNew.title') }}</h1>

    <section v-if="!selectedKm" class="km-choice">
      <h2>{{ $t('fipNew.chooseQuestionnaire') }}</h2>
      <p v-if="loadingKms">{{ $t('common.loading') }}</p>
      <template v-else>
        <div v-for="group in groupedKms" :key="group.key" class="km-group">
          <h3 v-if="group.items.length > 0" class="km-group-title">{{ $t(group.labelKey) }}</h3>
          <ul class="km-list">
            <li v-for="km in group.items" :key="`${km.id}@${km.version}`">
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
        </div>
      </template>
    </section>

    <form v-else class="community-form" @submit.prevent="onSubmit">
      <p v-if="!authStore.isAuthenticated" class="anonymous-hint">{{ $t('fipNew.anonymousHint') }}</p>

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
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { listKnowledgeModels } from '@/api/knowledgeModels'
import { createFip } from '@/api/fips'
import { setToken } from '@/lib/editTokens'
import { createFipErrorMessage } from '@/lib/fipErrors'
import { resolveLang } from '@/lib/lang'
import { useAuthStore } from '@/stores/auth'
import type { KnowledgeModelSummary } from '@/types/api'

// Spec 02 §3 / spec 04 §4, extended by spec 09 (standalone FIPs): GET
// /api/knowledge-models?status=published -> radio list grouped
// System/Mine/Public via `isSystem`/`ownerId`, then the §2.1 community
// form. Reachable signed out since spec 09 — `POST /api/fips` itself
// grants edit rights to an anonymous caller via a returned edit token.
const route = useRoute()
const router = useRouter()
const { locale, t } = useI18n()
const authStore = useAuthStore()

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
    // Spec 09: an anonymous caller gets an edit token back exactly once —
    // store it before navigating, same as the session-joining flow.
    if (created.editToken) {
      setToken(created.id, created.editToken)
    }
    await router.push(`/fips/${created.id}/edit`)
  } catch (err) {
    submitError.value = createFipErrorMessage(t, err, 'standalone')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  loadingKms.value = true
  try {
    const result = await listKnowledgeModels({ status: 'published' })
    knowledgeModels.value = result.items

    // Spec 09: `?km=<id>@<version>` preselects a listed published model,
    // skipping the choice step — used by KnowledgeModelRead.vue's
    // "Start a FIP with this model" link. Silently ignored if it doesn't
    // match anything published and listed.
    const preselect = route.query.km
    if (typeof preselect === 'string') {
      const match = knowledgeModels.value.find((km) => `${km.id}@${km.version}` === preselect)
      if (match) selectedKmKey.value = preselect
    }
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

.km-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.km-group-title {
  margin: 0.5rem 0 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
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

.anonymous-hint {
  margin: 0;
  padding: 0.75rem;
  border-radius: var(--border-radius-sm);
  background-color: var(--color-hover);
  color: var(--color-text-secondary);
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
