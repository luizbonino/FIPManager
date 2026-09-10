<template>
  <div class="km-read-view">
    <div v-if="loading" class="loading">
      <p>{{ $t('common.loading') }}</p>
    </div>

    <div v-else-if="notFound" class="message-box">
      <p>{{ $t('common.notFound') }}</p>
      <router-link to="/knowledge-models" class="btn btn-secondary">{{ $t('km.title') }}</router-link>
    </div>

    <template v-else-if="model">
      <header class="km-header">
        <h1>{{ resolveLang(model.title, locale) ?? model.id }}</h1>
        <div class="header-meta">
          <span class="ref-chip">{{ model.id }}@{{ model.version }}</span>
          <span class="status-chip">{{ $t(`km.${model.status}`) }}</span>
        </div>
        <p v-if="model.description && resolveLang(model.description, locale)" class="description">
          {{ resolveLang(model.description, locale) }}
        </p>
        <p v-if="model.content.forkedFrom" class="fork-note">
          {{ $t('km.forkOf', { id: model.content.forkedFrom.id, version: model.content.forkedFrom.version }) }}
        </p>

        <div class="actions no-print">
          <a class="btn btn-secondary" :href="kmExportJsonUrl(model.id, model.version)">{{ $t('km.export') }}</a>
          <router-link :to="`/knowledge-models/${model.id}/${model.version}/print`" class="btn btn-secondary">
            {{ $t('print.questionnaire') }}
          </router-link>
          <button type="button" class="btn btn-secondary" @click="onFork">{{ $t('km.fork') }}</button>
          <button
            v-if="isOwner && model.status === 'published'"
            type="button"
            class="btn btn-secondary"
            @click="onNewVersion"
          >
            {{ $t('km.newVersion') }}
          </button>
          <router-link
            v-if="isOwner && model.status === 'draft'"
            :to="`/knowledge-models/${model.id}/${model.version}/edit`"
            class="btn btn-primary"
          >
            {{ $t('km.edit') }}
          </router-link>
          <!-- Spec 09: anyone, signed in or not, can start a standalone FIP straight from a published model. -->
          <router-link
            v-if="model.status === 'published'"
            :to="`/fips/new?km=${model.id}@${model.version}`"
            class="btn btn-primary"
          >
            {{ $t('km.startFip') }}
          </router-link>
        </div>
      </header>

      <section v-if="model.changelog.length > 0" class="changelog">
        <h2>{{ $t('km.changelog') }}</h2>
        <ul>
          <li v-for="(entry, i) in model.changelog" :key="i">
            <strong>{{ entry.version }}</strong> — {{ entry.date }}: {{ entry.notes }}
          </li>
        </ul>
      </section>

      <div class="sections">
        <section v-for="section in model.content.sections" :key="section.id" class="section">
          <h2>{{ resolveLang(section.title, locale) ?? section.id }}</h2>
          <div class="questions">
            <article
              v-for="question in section.questions"
              :key="question.id"
              class="question"
              :class="{ hidden: question.hidden }"
            >
              <div class="question-head">
                <span class="question-id">{{ question.id }}</span>
                <span v-if="question.principle" class="badge">{{ question.principle }}</span>
                <span v-if="question.scope" class="badge">{{ $t(`matrix.scope${question.scope === 'metadata' ? 'Metadata' : 'Data'}`) }}</span>
                <span v-if="question.ferType" class="badge">{{ ferTypeLabel(question.ferType) }}</span>
                <span v-if="question.required" class="badge">{{ $t('km.required') }}</span>
                <span v-if="question.hidden" class="badge hidden-badge">{{ $t('km.hidden') }}</span>
              </div>
              <p class="question-text">{{ resolveLang(question.text, locale) ?? question.id }}</p>
              <p v-if="resolveLang(question.help, locale)" class="question-help">{{ resolveLang(question.help, locale) }}</p>

              <div v-if="hasSuggestions(question)" class="suggested-options">
                <span class="suggested-options-label">{{ $t('editor.suggestedOptions') }}</span>
                <ul>
                  <li v-for="ferId in question.suggestedFerIds ?? []" :key="ferId">{{ resolveFerLabel(ferId) }}</li>
                  <li v-for="(phrase, i) in question.suggestedPhrases ?? []" :key="`phrase-${i}`">
                    {{ resolveLang(phrase.text, locale) }}
                  </li>
                </ul>
              </div>
            </article>
          </div>
        </section>
      </div>

      <!--
        Reused as-is (spec §5); its second line reads "This FIP's answers:
        {license}" which is FIP-specific wording, imprecise here — the
        model's own `license` is passed through regardless so the line at
        least states a real value rather than an empty one.
      -->
      <AttributionFooter :questionnaire-license="model.license" :fip-license="model.license" />
    </template>
  </div>
</template>

<script lang="ts" setup>
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { ApiResponseError } from '@/api/client'
import {
  forkKnowledgeModel,
  getKnowledgeModel,
  kmExportJsonUrl,
  listKnowledgeModels,
  newKnowledgeModelVersion,
} from '@/api/knowledgeModels'
import { getFerTypes } from '@/api/ferTypes'
import { listFers } from '@/api/fers'
import { resolveLang } from '@/lib/lang'
import { resolveSuggestedFer } from '@/lib/kmContent'
import { useAuthStore } from '@/stores/auth'
import AttributionFooter from '@/components/AttributionFooter.vue'
import type { FerOut, FerType, KnowledgeModelOut, KnowledgeModelQuestion } from '@/types/api'

// Spec 04 §5: public, read-only view of one knowledge-model version.
const route = useRoute()
const router = useRouter()
const { locale } = useI18n()
const authStore = useAuthStore()

const loading = ref(true)
const notFound = ref(false)
const model = ref<KnowledgeModelOut | null>(null)
const ferTypes = ref<Record<string, FerType>>({})
const fers = ref<Record<string, FerOut>>({})

// `KnowledgeModelOut` carries no `ownerId` (spec §3 #3's body is
// unchanged), so ownership is resolved with a side query against
// `?mine=true` (added to `api/knowledgeModels.ts` for exactly this) rather
// than left to the reader's own judgement — the API is still the final
// authority and rejects a stale-owned attempt with 403/404 regardless.
const isOwner = ref(false)

function ferTypeLabel(key: string): string {
  const entry = ferTypes.value[key]
  return entry ? (resolveLang(entry.label, locale.value) ?? key) : key
}

/** spec 08 §1.5: resolves a suggested id against `content.inlineFers` then the catalogue (spec §1.3). */
function resolveFerLabel(ferId: string): string {
  if (!model.value) return ferId
  const resolved = resolveSuggestedFer(ferId, model.value.content, fers.value)
  return (resolved && resolveLang(resolved.label, locale.value)) || ferId
}

function hasSuggestions(question: KnowledgeModelQuestion): boolean {
  return (question.suggestedFerIds?.length ?? 0) > 0 || (question.suggestedPhrases?.length ?? 0) > 0
}

async function onFork() {
  if (!model.value) return
  const created = await forkKnowledgeModel(model.value.id, model.value.version)
  await router.push(`/knowledge-models/${created.id}/${created.version}/edit`)
}

async function onNewVersion() {
  if (!model.value) return
  const created = await newKnowledgeModelVersion(model.value.id, model.value.version)
  await router.push(`/knowledge-models/${created.id}/${created.version}/edit`)
}

async function load() {
  loading.value = true
  notFound.value = false
  isOwner.value = false
  const id = String(route.params.id)
  const version = String(route.params.version)
  try {
    const [loaded, ferTypesResult, fersResult] = await Promise.all([
      getKnowledgeModel(id, version),
      getFerTypes().catch(() => ({ items: [], total: 0 })),
      listFers({ limit: 500 }).catch(() => ({ items: [], total: 0 })),
    ])
    model.value = loaded
    ferTypes.value = Object.fromEntries(ferTypesResult.items.map((f) => [f.key, f]))
    fers.value = Object.fromEntries(fersResult.items.map((f) => [f.id, f]))
    if (authStore.isAuthenticated) {
      const mine = await listKnowledgeModels({ mine: true }).catch(() => ({ items: [], total: 0 }))
      isOwner.value = mine.items.some((m) => m.id === id && m.version === version)
    }
  } catch (err) {
    if (err instanceof ApiResponseError && err.status === 404) {
      notFound.value = true
    } else {
      notFound.value = true
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)

// Fork / New version (and any other in-app link) push to another
// `id`/`version` on this same route (`KnowledgeModelRead`), reusing the
// component instance rather than remounting it — without this, the
// previously loaded model stays on screen.
watch(() => [route.params.id, route.params.version], load)
</script>

<style scoped>
.km-read-view {
  max-width: 800px;
  margin: 0 auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.loading,
.message-box {
  text-align: center;
  padding: 3rem 1rem;
}

.km-header h1 {
  margin: 0 0 0.5rem;
  color: var(--color-primary);
}

.header-meta {
  display: flex;
  gap: 0.5rem;
  align-items: center;
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

.description {
  color: var(--color-text-secondary);
}

.fork-note {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-top: 0.75rem;
}

.changelog h2 {
  font-size: 1.1rem;
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 0.4rem;
}

.changelog ul {
  margin: 0;
  padding-left: 1.25rem;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.sections {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.section h2 {
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 0.4rem;
}

.questions {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.question {
  padding: 0.75rem 1rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
}

.question.hidden {
  opacity: 0.65;
  background-color: var(--color-hover);
}

.question-head {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.question-id {
  font-family: monospace;
  font-size: var(--font-size-xs);
  color: var(--color-id-chip-text);
  background-color: var(--color-id-chip-bg);
  padding: 0.15rem 0.4rem;
  border-radius: var(--border-radius-sm);
}

.badge {
  font-size: var(--font-size-xs);
  color: var(--color-chip-text);
  background-color: var(--color-chip-bg);
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
}

.hidden-badge {
  background-color: var(--color-status-planned);
  color: #ffffff;
}

.question-text {
  margin: 0.35rem 0;
  font-weight: var(--font-weight-medium);
}

.question-help {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.suggested-options {
  margin-top: 0.5rem;
  padding: 0.5rem 0.6rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-hover);
}

.suggested-options-label {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
}

.suggested-options ul {
  margin: 0.25rem 0 0;
  padding-left: 1.25rem;
  font-size: var(--font-size-sm);
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
