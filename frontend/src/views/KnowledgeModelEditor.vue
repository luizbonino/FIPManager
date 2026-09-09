<template>
  <div class="km-editor-view">
    <div v-if="store.loading" class="loading">
      <p>{{ $t('common.loading') }}</p>
    </div>

    <div v-else-if="store.notFound" class="message-box">
      <p>{{ $t('common.notFound') }}</p>
      <router-link to="/knowledge-models" class="btn btn-secondary">{{ $t('km.title') }}</router-link>
    </div>

    <template v-else-if="store.model && store.content">
      <header class="editor-header">
        <div class="header-row">
          <div class="header-title">
            <h1>{{ resolveLang(store.content.title, locale) ?? store.model.id }}</h1>
            <span class="ref-chip">{{ store.model.id }}@{{ store.model.version }}</span>
            <span class="status-chip">{{ $t(`km.${store.model.status}`) }}</span>
          </div>
          <SaveIndicator :state="store.saveState" :last-saved-at="store.lastSavedAt" @retry="store.save" />
        </div>

        <div class="header-row">
          <TranslationMeter
            :done="meterFor(locale).done"
            :total="meterFor(locale).total"
            :language="locale"
          />
          <div class="header-actions no-print">
            <button type="button" class="btn btn-secondary validate-btn" @click="onValidate">{{ $t('km.validate') }}</button>
            <button type="button" class="btn btn-secondary save-btn" :disabled="store.readOnly" @click="store.save">
              {{ $t('km.save') }}
            </button>
            <button
              type="button"
              class="btn btn-primary publish-trigger-btn"
              :disabled="store.model.status === 'published'"
              @click="publishOpen = true"
            >
              {{ $t('km.publish') }}
            </button>
          </div>
        </div>

        <p v-if="readOnlyMessage" class="readonly-banner">{{ readOnlyMessage }}</p>

        <div v-if="store.conflict" class="conflict-banner">
          <span>{{ $t('km.conflict') }}</span>
          <button type="button" class="btn btn-secondary reload-btn" @click="onReload">{{ $t('km.reload') }}</button>
        </div>

        <KmValidationList v-if="showValidation" :errors="store.errors" />
      </header>

      <section class="metadata-block">
        <div class="field-group">
          <span class="field-label">{{ $t('common.name') }}</span>
          <KmLangTabs
            :model-value="store.content.title"
            :default-lang="locale"
            :disabled="store.readOnly"
            @change="(lang, value) => store.apply((c) => setText(c, { field: 'title' }, lang, value))"
          />
        </div>
        <div class="field-group">
          <span class="field-label">{{ $t('common.description') }}</span>
          <KmLangTabs
            :model-value="store.content.description"
            multiline
            :default-lang="locale"
            :disabled="store.readOnly"
            @change="(lang, value) => store.apply((c) => setText(c, { field: 'description' }, lang, value))"
          />
        </div>
        <VisibilitySelect
          :model-value="(store.model.visibility as Visibility)"
          @update:model-value="onVisibilityChange"
        />
        <p v-if="visibilityError" class="visibility-error">{{ visibilityError }}</p>
      </section>

      <KmSectionList :sections="store.content.sections" :fer-type-options="ferTypes" :read-only="store.readOnly" />

      <div class="footer-actions no-print">
        <a class="btn btn-secondary" :href="kmExportJsonUrl(store.model.id, store.model.version)">{{ $t('km.export') }}</a>
        <button type="button" class="btn btn-secondary" @click="onFork">{{ $t('km.fork') }}</button>
        <template v-if="store.model.status === 'published'">
          <label class="bump-field">
            <span>{{ $t('km.bump') }}</span>
            <select v-model="newVersionBump">
              <option value="minor">{{ $t('km.bumpMinor') }}</option>
              <option value="patch">{{ $t('km.bumpPatch') }}</option>
              <option value="major">{{ $t('km.bumpMajor') }}</option>
            </select>
          </label>
          <button type="button" class="btn btn-secondary" @click="onNewVersion">
            {{ $t('km.newVersion') }}
          </button>
        </template>
        <button type="button" class="btn btn-danger" @click="onDelete">{{ $t('km.deleteModel') }}</button>
      </div>

      <KmPublishDialog
        :open="publishOpen"
        :version="store.model.version"
        :errors="store.errors"
        :publishing="publishing"
        @close="publishOpen = false"
        @publish="onPublish"
      />
    </template>
  </div>
</template>

<script lang="ts" setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useKmEditorStore } from '@/stores/kmEditor'
import { getFerTypes } from '@/api/ferTypes'
import { kmExportJsonUrl } from '@/api/knowledgeModels'
import { ApiResponseError } from '@/api/client'
import { resolveLang } from '@/lib/lang'
import { setText } from '@/lib/kmContent'
import SaveIndicator from '@/components/SaveIndicator.vue'
import TranslationMeter from '@/components/TranslationMeter.vue'
import VisibilitySelect from '@/components/VisibilitySelect.vue'
import KmSectionList from '@/components/KmSectionList.vue'
import KmLangTabs from '@/components/KmLangTabs.vue'
import KmValidationList from '@/components/KmValidationList.vue'
import KmPublishDialog from '@/components/KmPublishDialog.vue'
import type { FerType, Visibility } from '@/types/api'

/**
 * Desktop-first, phone-safe (spec 04 §5 A1: single column, no drag). Sticky
 * header: model title, `id@version`, status chip, `SaveIndicator`,
 * `TranslationMeter`, Validate, Save, Publish. Body: metadata block then
 * the sections accordion (`KmSectionList`).
 */
const route = useRoute()
const router = useRouter()
const { locale, t } = useI18n()
const store = useKmEditorStore()

const ferTypes = ref<FerType[]>([])
const showValidation = ref(false)
const publishOpen = ref(false)
const publishing = ref(false)
const newVersionBump = ref<'minor' | 'patch' | 'major'>('minor')
const visibilityError = ref<string | null>(null)

function meterFor(lang: string) {
  return store.completeness(lang)
}

const readOnlyMessage = computed(() => {
  if (store.readOnlyReason === 'published') return t('km.readOnlyPublished')
  if (store.readOnlyReason === 'system') return t('km.readOnlySystem')
  return null
})

function onValidate() {
  store.validate()
  showValidation.value = true
}

async function onReload() {
  await store.reload()
}

async function onVisibilityChange(visibility: Visibility) {
  visibilityError.value = null
  try {
    await store.patchMeta({ visibility })
  } catch (err) {
    // spec 07 §2 gate rule: same 403 `email_verification_required` as a
    // FIP's public-visibility write, surfaced the same way.
    if (err instanceof ApiResponseError && err.data.detail === 'email_verification_required') {
      visibilityError.value = t('errors.emailVerificationRequired')
    }
  }
}

async function onFork() {
  if (!store.model) return
  const created = await store.fork(store.model.id, store.model.version)
  await router.push(`/knowledge-models/${created.id}/${created.version}/edit`)
}

async function onNewVersion() {
  const created = await store.newVersion({ bump: newVersionBump.value })
  await router.push(`/knowledge-models/${created.id}/${created.version}/edit`)
}

async function onDelete() {
  if (!store.model) return
  if (!confirm(t('km.deleteModelConfirm'))) return
  try {
    await store.remove()
    await router.push('/knowledge-models')
  } catch {
    alert(t('km.inUse'))
  }
}

async function onPublish(notes: string) {
  publishing.value = true
  try {
    await store.publish(notes)
    publishOpen.value = false
    showValidation.value = false
  } catch {
    showValidation.value = true
  } finally {
    publishing.value = false
  }
}

async function init() {
  const id = String(route.params.id)
  const version = String(route.params.version)
  try {
    const [, ferTypesResult] = await Promise.all([
      store.load(id, version),
      getFerTypes().catch(() => ({ items: [], total: 0 })),
    ])
    ferTypes.value = ferTypesResult.items
  } catch {
    // store.notFound already reflects a 404; any other failure also just
    // leaves the view on its loading/not-found branches.
  }
}

onMounted(init)

// Fork / New version push to another `id`/`version` on this same route
// (`KnowledgeModelEditor`), so the component instance is reused rather
// than remounted — without this, `onMounted` never fires again and the
// previous model stays on screen. Flush any pending edit on the old
// model first, then reset and load the new one.
watch(
  () => [route.params.id, route.params.version],
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
.km-editor-view {
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

.header-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.header-title h1 {
  margin: 0;
  font-size: 1.25rem;
  color: var(--color-primary);
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

.header-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.readonly-banner {
  margin: 0;
  padding: 0.5rem 0.75rem;
  background-color: var(--color-error-bg);
  color: var(--color-error);
  border-radius: var(--border-radius-sm);
  font-size: var(--font-size-sm);
}

.visibility-error {
  margin: 0;
  padding: 0.5rem 0.75rem;
  background-color: var(--color-error-bg);
  color: var(--color-error);
  border-radius: var(--border-radius-sm);
  font-size: var(--font-size-sm);
}

.conflict-banner {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  background-color: var(--color-error-bg);
  color: var(--color-error);
  border-radius: var(--border-radius-sm);
  font-size: var(--font-size-sm);
}

.metadata-block {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.field-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
}

.footer-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.bump-field {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: var(--font-size-sm);
}

.bump-field select {
  min-height: 44px;
  padding: 0.3rem 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
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

.btn-danger {
  background-color: var(--color-error-bg);
  color: var(--color-error);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@media (max-width: 480px) {
  .header-row {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
