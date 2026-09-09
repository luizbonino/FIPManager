<template>
  <div class="fip-editor-view">
    <div v-if="store.loading" class="loading">
      <p>{{ $t('common.loading') }}</p>
    </div>

    <div v-else-if="store.notFound" class="message-box">
      <p>{{ $t('common.notFound') }}</p>
      <router-link to="/" class="btn btn-secondary">{{ $t('nav.home') }}</router-link>
    </div>

    <template v-else-if="store.fip && km">
      <header class="editor-header">
        <div class="header-row">
          <h1 class="community-name">{{ store.fip.community?.name || store.fip.id }}</h1>
          <SaveIndicator
            :state="store.saveState"
            :last-saved-at="store.lastSavedAt"
            :retries-exhausted="store.retryExhausted"
            @retry="store.retry"
          />
        </div>
        <div class="header-row">
          <ProgressBar :answered="answeredCount" :total="totalQuestions" />
          <LanguageSwitcher @changed="onLocaleChanged" />
        </div>
        <p v-if="store.readOnly" class="readonly-banner">{{ readOnlyMessage }}</p>
        <div v-if="isOwner" class="owner-row no-print">
          <VisibilitySelect v-model="visibilityModel" />
          <button type="button" class="delete-btn" @click="onDelete">{{ $t('common.delete') }}</button>
        </div>
        <button v-if="canClaim" type="button" class="claim-btn no-print" @click="onClaim">
          {{ $t('editor.claim') }}
        </button>
        <p v-if="claimed" class="claimed-msg">{{ $t('editor.claimed') }}</p>
        <router-link :to="`/fips/${store.fip.id}`" class="preview-link no-print">
          {{ $t('editor.preview') }}
        </router-link>
      </header>

      <div class="sections" @blur.capture="onFieldBlur">
        <details class="section dmp-section" @toggle="onSectionToggle">
          <summary>
            <span class="section-title">{{ $t('dmp.heading') }}</span>
          </summary>
          <div class="section-body">
            <DmpLinkList
              :entries="store.fip.relatedDmps"
              :read-only="store.readOnly"
              @update="onDmpUpdate"
            />
          </div>
        </details>

        <details
          v-for="section in km.content.sections"
          :key="section.id"
          class="section"
          :open="section.id === 'F'"
          @toggle="onSectionToggle"
        >
          <summary>
            <span class="section-title">{{ resolveLang(section.title, locale) ?? section.id }}</span>
          </summary>
          <div class="section-body">
            <QuestionCard
              v-for="question in section.questions"
              :key="question.id"
              :question="question"
              :fer-type-label="ferTypeLabel(question.ferType)"
            />
          </div>
        </details>
      </div>

      <ShareBox v-if="store.fip.visibility !== 'private'" :url="shareUrl" :fip-id="store.fip.id" />
      <ExportButtons
        :json-url="fipExportJsonUrl(store.fip.id)"
        :csv-url="fipExportCsvUrl(store.fip.id)"
        :ttl-url="fipExportTtlUrl(store.fip.id)"
        :jsonld-url="fipExportJsonldUrl(store.fip.id)"
      />

      <AttributionFooter :questionnaire-license="km.content.license" :fip-license="store.fip.license" />
    </template>
  </div>
</template>

<script lang="ts" setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useFipEditorStore } from '@/stores/fipEditor'
import { useAuthStore } from '@/stores/auth'
import { answeredCount as computeAnsweredCount, visibleQuestionCount } from '@/lib/progress'
import { resolveLang } from '@/lib/lang'
import { getToken } from '@/lib/editTokens'
import { getFerTypes } from '@/api/ferTypes'
import { fipExportCsvUrl, fipExportJsonldUrl, fipExportJsonUrl, fipExportTtlUrl } from '@/api/fips'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import SaveIndicator from '@/components/SaveIndicator.vue'
import QuestionCard from '@/components/QuestionCard.vue'
import ShareBox from '@/components/ShareBox.vue'
import ExportButtons from '@/components/ExportButtons.vue'
import AttributionFooter from '@/components/AttributionFooter.vue'
import VisibilitySelect from '@/components/VisibilitySelect.vue'
import DmpLinkList from '@/components/DmpLinkList.vue'
import type { FerType, RelatedDmp, Visibility } from '@/types/api'

// Spec 02 §2.2/§2.3/§2.4: the participant + owner editor.
const route = useRoute()
const router = useRouter()
const { locale, t } = useI18n()
const store = useFipEditorStore()
const authStore = useAuthStore()

const km = computed(() => store.km)
const ferTypes = ref<Record<string, FerType>>({})
const claimed = ref(false)

const answeredCount = computed(() => computeAnsweredCount(store.fip?.answers))
// Spec 04 §4: the denominator is the loaded model's non-hidden question
// count, not the hardcoded 21 — falls back to 21 only while `km` hasn't loaded yet.
const totalQuestions = computed(() => visibleQuestionCount(km.value))

const isOwner = computed(
  () => !!store.fip?.ownerId && !!authStore.user && store.fip.ownerId === authStore.user.id
)

const canClaim = computed(
  () => !!store.fip && !store.fip.ownerId && authStore.isAuthenticated && !!getToken(store.fip.id)
)

const shareUrl = computed(() => `${location.origin}/fips/${store.fip?.id}`)

const readOnlyMessage = computed(() => {
  if (store.lastError === 'forbidden') return t('editor.editRightsLost')
  if (store.lastError === 'session_closed') return t('join.closed')
  return t('editor.readOnly')
})

const visibilityModel = computed<Visibility>({
  get: () => store.fip?.visibility ?? 'private',
  set: (v) => {
    void store.updateVisibility(v)
  },
})

function ferTypeLabel(key: string | null): string | null {
  if (!key) return null
  const entry = ferTypes.value[key]
  if (!entry) return key
  return resolveLang(entry.label, locale.value) ?? key
}

function onDmpUpdate(entries: RelatedDmp[]) {
  store.setRelatedDmps(entries)
}

function onLocaleChanged(newLocale: string) {
  if (store.canEdit) {
    store.setLanguage(newLocale)
  }
}

function onSectionToggle(event: Event) {
  const details = event.target as HTMLDetailsElement
  if (!details.open) {
    void store.flush()
  }
}

function onFieldBlur(event: FocusEvent) {
  const tag = (event.target as HTMLElement)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
    void store.flush()
  }
}

async function onClaim() {
  await store.claim()
  claimed.value = true
}

async function onDelete() {
  if (!store.fip) return
  if (!confirm(t('common.deleteFipConfirm'))) return
  await store.remove()
  await router.push('/workspace')
}

async function init() {
  const id = String(route.params.id)
  try {
    const [, ferTypesResult] = await Promise.all([
      store.load(id),
      getFerTypes().catch(() => ({ items: [], total: 0 })),
    ])
    ferTypes.value = Object.fromEntries(ferTypesResult.items.map((f) => [f.key, f]))
  } catch {
    // store.notFound / a network failure both render from state above.
    return
  }
  if (!store.notFound && !store.canEdit) {
    await router.replace(`/fips/${id}`)
  }
}

onMounted(init)

// Navigating between two FIPs while already on this route (same route
// record, different `:id`) reuses the component instance instead of
// remounting it — flush any pending edit on the old FIP first, then
// reset and load the new one.
watch(
  () => route.params.id,
  async () => {
    await store.flush()
    await init()
  }
)

onBeforeUnmount(() => {
  void store.flush()
})
</script>

<style scoped>
.fip-editor-view {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding-bottom: 3rem;
}

.loading,
.message-box {
  text-align: center;
  padding: 3rem 1rem;
}

.editor-header {
  position: sticky;
  top: 0;
  z-index: 10;
  background-color: var(--color-background);
  border-bottom: 1px solid var(--color-border);
  padding: 0.75rem 0 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.community-name {
  margin: 0;
  font-size: 1.25rem;
  color: var(--color-primary);
}

.readonly-banner {
  margin: 0;
  padding: 0.5rem 0.75rem;
  background-color: var(--color-error-bg);
  color: var(--color-error);
  border-radius: var(--border-radius-sm);
  font-size: var(--font-size-sm);
}

.owner-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.delete-btn {
  min-height: 44px;
  padding: 0.4rem 0.9rem;
  border: 1px solid var(--color-error);
  border-radius: var(--border-radius-sm);
  background: none;
  color: var(--color-error);
}

.claim-btn {
  align-self: flex-start;
  min-height: 44px;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: var(--border-radius-sm);
  background-color: var(--color-primary);
  color: var(--color-primary-text);
}

.claimed-msg {
  margin: 0;
  color: var(--color-success);
  font-size: var(--font-size-sm);
}

.preview-link {
  align-self: flex-start;
  font-size: var(--font-size-sm);
}

.sections {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.section {
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  overflow: hidden;
}

.section > summary {
  cursor: pointer;
  min-height: 44px;
  display: flex;
  align-items: center;
  padding: 0.75rem 1rem;
  background-color: var(--color-hover);
  font-weight: var(--font-weight-bold);
  font-size: 1.1rem;
}

.section-body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem;
}

@media (min-width: 900px) {
  .fip-editor-view {
    display: grid;
    grid-template-columns: 1fr;
  }
}
</style>
