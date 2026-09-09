<template>
  <div class="session-new-view">
    <h1>{{ $t('sessionAdmin.newTitle') }}</h1>

    <form class="session-form" @submit.prevent="onSubmit">
      <label class="field">
        <span>{{ $t('sessionAdmin.titleLabel') }} *</span>
        <input v-model="title" type="text" required />
      </label>

      <div v-for="(row, index) in rows" :key="row.key" class="questionnaire-row">
        <label class="field">
          <span>{{ $t('sessionAdmin.knowledgeModel') }} {{ rows.length > 1 ? index + 1 : '' }} *</span>
          <select v-model="row.kmKey" required @change="onRowKmChange(row)">
            <option value="" disabled>{{ $t('fipNew.chooseQuestionnaire') }}</option>
            <optgroup v-for="group in groupedKms" :key="group.key" :label="$t(group.labelKey)">
              <option v-for="km in group.items" :key="`${km.id}@${km.version}`" :value="`${km.id}@${km.version}`">
                {{ resolveLang(km.title, locale) ?? km.id }} (v{{ km.version }})
              </option>
            </optgroup>
          </select>
        </label>

        <label v-if="rows.length > 1" class="field">
          <span>{{ $t('sessionAdmin.areaLabel') }}</span>
          <input v-model="row.label" type="text" maxlength="80" :placeholder="$t('sessionAdmin.areaLabelPlaceholder')" />
        </label>

        <div v-if="isRowKmPrivate(row)" class="private-model-notice">
          <p>{{ $t('sessionAdmin.privateModelNotice') }}</p>
          <label class="checkbox-field">
            <input v-model="row.makeLinkVisible" type="checkbox" />
            <span>{{ $t('sessionAdmin.makeModelLinkVisible') }}</span>
          </label>
        </div>

        <button
          v-if="rows.length > 1"
          type="button"
          class="btn btn-secondary remove-row-btn"
          @click="removeRow(row.key)"
        >
          {{ $t('sessionAdmin.removeQuestionnaire') }}
        </button>
      </div>

      <button
        v-if="rows.length < MAX_QUESTIONNAIRE_REFS"
        type="button"
        class="btn btn-secondary add-row-btn"
        @click="addRow"
      >
        {{ $t('sessionAdmin.addQuestionnaire') }}
      </button>

      <label class="field">
        <span>{{ $t('sessionAdmin.defaultLanguage') }}</span>
        <select v-model="defaultLanguage">
          <option v-for="l in SUPPORTED_LOCALES" :key="l" :value="l">{{ $t(`languages.${l}`) }}</option>
        </select>
      </label>

      <p v-if="submitError" class="form-error">{{ submitError }}</p>

      <button type="submit" class="btn btn-primary" :disabled="submitting || !canSubmit">
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
import type { KnowledgeModelSummary, QuestionnaireRefLabelled } from '@/types/api'

// Spec 02 §4.1 / spec 04 §4: options grouped System/Mine/Public via `isSystem`/`ownerId`.
// Spec 08 §3.1/§3.3: 1..12 questionnaire rows, each an independent model +
// short per-session area label; a single row posts exactly the legacy
// `questionnaireRef` body (no visible behaviour change for the common case).
const MAX_QUESTIONNAIRE_REFS = 12

interface QuestionnaireRow {
  key: string
  kmKey: string
  /** Prefilled from the model's title once picked; the participant-facing area label (spec §3.3). */
  label: string
  makeLinkVisible: boolean
}

let rowSeq = 0
function newRow(): QuestionnaireRow {
  rowSeq += 1
  return { key: `row-${rowSeq}`, kmKey: '', label: '', makeLinkVisible: true }
}

const router = useRouter()
const { locale, t } = useI18n()
const authStore = useAuthStore()

const title = ref('')
const rows = ref<QuestionnaireRow[]>([newRow()])
const defaultLanguage = ref(locale.value)
const knowledgeModels = ref<KnowledgeModelSummary[]>([])
const submitting = ref(false)
const submitError = ref<string | null>(null)

function findKm(kmKey: string): KnowledgeModelSummary | null {
  return knowledgeModels.value.find((km) => `${km.id}@${km.version}` === kmKey) ?? null
}

function isRowKmPrivate(row: QuestionnaireRow): boolean {
  return findKm(row.kmKey)?.visibility === 'private'
}

/** Prefill the label from the model's own title, current locale, only while the participant hasn't typed one yet. */
function onRowKmChange(row: QuestionnaireRow) {
  if (row.label.trim() !== '') return
  const km = findKm(row.kmKey)
  if (km) row.label = (resolveLang(km.title, defaultLanguage.value) ?? km.id).slice(0, 80)
}

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

const canSubmit = computed(() => rows.value.length > 0 && rows.value.every((r) => r.kmKey !== ''))

function addRow() {
  if (rows.value.length >= MAX_QUESTIONNAIRE_REFS) return
  rows.value = [...rows.value, newRow()]
}

function removeRow(key: string) {
  rows.value = rows.value.filter((r) => r.key !== key)
}

async function onSubmit() {
  if (!canSubmit.value) return
  submitting.value = true
  submitError.value = null
  try {
    // Visibility fixes land before the session is created (spec 02 §4.1) —
    // a participant must never race a still-private questionnaire.
    for (const row of rows.value) {
      if (isRowKmPrivate(row) && row.makeLinkVisible) {
        const [id, version] = row.kmKey.split('@')
        await patchKnowledgeModel(id, version, { visibility: 'link' })
        const km = findKm(row.kmKey)
        if (km) km.visibility = 'link'
      }
    }

    const [firstId, firstVersion] = rows.value[0].kmKey.split('@')
    if (rows.value.length === 1) {
      // Spec §3.3: "A single-row form posts exactly what it posts today."
      const created = await createSession({
        title: title.value,
        questionnaireRef: { id: firstId, version: firstVersion },
        defaultLanguage: defaultLanguage.value,
      })
      await router.push(`/sessions/${created.id}`)
      return
    }

    const questionnaireRefs: QuestionnaireRefLabelled[] = rows.value.map((row) => {
      const [id, version] = row.kmKey.split('@')
      const label = row.label.trim() || findKm(row.kmKey)?.id || id
      return { id, version, label: { [defaultLanguage.value]: label.slice(0, 80) } }
    })
    const created = await createSession({
      title: title.value,
      questionnaireRef: { id: firstId, version: firstVersion },
      questionnaireRefs,
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

.questionnaire-row {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
}

.remove-row-btn,
.add-row-btn {
  align-self: flex-start;
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
  padding: 0.6rem 1.2rem;
  border: none;
  border-radius: var(--border-radius-sm);
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
}

.btn-primary {
  background-color: var(--color-primary);
  color: var(--color-primary-text);
  padding: 0.75rem 1.5rem;
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
}

.btn:disabled {
  opacity: 0.7;
}
</style>
