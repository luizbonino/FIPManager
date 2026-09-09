<template>
  <div class="km-print-view">
    <div v-if="loading" class="loading no-print">
      <p>{{ $t('common.loading') }}</p>
    </div>

    <div v-else-if="notFound" class="message-box no-print">
      <p>{{ $t('common.notFound') }}</p>
      <router-link to="/knowledge-models" class="btn btn-secondary">{{ $t('km.title') }}</router-link>
    </div>

    <template v-else-if="model">
      <div class="print-controls no-print">
        <label class="declarations-field">
          <span>{{ $t('print.declarationsPerQuestion') }}</span>
          <select v-model.number="declarationsPerQuestion">
            <option v-for="n in [1, 2, 3]" :key="n" :value="n">{{ n }}</option>
          </select>
        </label>
        <LanguageSwitcher />
        <button type="button" class="btn btn-primary" @click="onPrint">{{ $t('print.questionnaire') }}</button>
      </div>

      <article class="print-sheet">
        <section class="title-page">
          <p class="handout-title">{{ $t('print.handoutTitle') }}</p>
          <h1>{{ resolveLang(model.title, locale) ?? model.id }}</h1>
          <p class="ref-chip">{{ model.id }}@{{ model.version }}</p>

          <ul class="section-toc">
            <li v-for="section in model.content.sections" :key="section.id">
              {{ resolveLang(section.title, locale) ?? section.id }}
            </li>
          </ul>

          <p class="instructions">{{ $t('print.instructions') }}</p>

          <div class="fill-line"><span class="fill-label">{{ $t('print.group') }}</span></div>
          <div class="fill-line"><span class="fill-label">{{ $t('community.name') }}</span></div>
          <div class="fill-line"><span class="fill-label">{{ $t('community.description') }}</span></div>
          <div class="fill-line"><span class="fill-label">{{ $t('community.domain') }}</span></div>
          <div class="fill-line"><span class="fill-label">{{ $t('community.dataSteward') }}</span></div>
          <div class="fill-line"><span class="fill-label">{{ $t('print.date') }}</span></div>
        </section>

        <section v-for="section in model.content.sections" :key="section.id" class="section">
          <h2 class="section-title">{{ resolveLang(section.title, locale) ?? section.id }}</h2>

          <div v-for="question in visibleQuestions(section)" :key="question.id" class="question">
            <div class="question-head">
              <span class="question-id">{{ question.id }}</span>
              <span v-if="question.ferType" class="fer-type">
                {{ $t('print.ferType') }}: {{ ferTypeLabel(question.ferType) }}
              </span>
            </div>
            <p class="question-text">{{ resolveLang(question.text, locale) ?? question.id }}</p>
            <p v-if="resolveLang(question.help, locale)" class="question-help">
              {{ resolveLang(question.help, locale) }}
            </p>

            <div v-for="n in declarationsPerQuestion" :key="n" class="decl-block">
              <div class="fill-line"><span class="fill-label">{{ $t('print.resource') }} {{ n }}</span></div>
              <div class="tick-row">
                <label v-for="status in STATUSES" :key="status" class="tick-item">
                  <span class="tick-box"></span>
                  <span class="tick-label">{{ $t(`declarationStatus.${STATUS_KEYS[status]}`) }}</span>
                </label>
              </div>
              <div class="fill-line"><span class="fill-label">{{ $t('editor.note') }}</span></div>
            </div>

            <div class="fill-line comment-line"><span class="fill-label">{{ $t('editor.comment') }}</span></div>
          </div>
        </section>

        <footer class="print-footer">
          <p>{{ $t('attribution.questionnaire') }}</p>
          <p>{{ $t('attribution.ontology') }}</p>
          <p>{{ $t('print.footerTool') }}</p>
        </footer>
      </article>
    </template>
  </div>
</template>

<script lang="ts" setup>
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { ApiResponseError } from '@/api/client'
import { getKnowledgeModel } from '@/api/knowledgeModels'
import { getFerTypes } from '@/api/ferTypes'
import { resolveLang } from '@/lib/lang'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import '@/assets/print-questionnaire.css'
import type { DeclarationStatus, FerType, KnowledgeModelOut, KnowledgeModelSection } from '@/types/api'

// spec 05 §3: the paper-fallback questionnaire, public and print-only in
// intent (a `window.print()` button drives it) but rendered fully on
// screen too, so a facilitator can proof-read it before printing.
const route = useRoute()
const { locale } = useI18n()

const loading = ref(true)
const notFound = ref(false)
const model = ref<KnowledgeModelOut | null>(null)
const ferTypes = ref<Record<string, FerType>>({})

const STATUSES: DeclarationStatus[] = ['current', 'planned', 'planned-development', 'planned-replacement', 'none']
const STATUS_KEYS: Record<DeclarationStatus, string> = {
  current: 'current',
  planned: 'planned',
  'planned-development': 'plannedDevelopment',
  'planned-replacement': 'plannedReplacement',
  none: 'none',
}

const declarationsPerQuestion = ref(3)

function clampDeclarations(value: number): number {
  if (!Number.isFinite(value)) return 3
  return Math.min(3, Math.max(1, Math.round(value)))
}

function visibleQuestions(section: KnowledgeModelSection) {
  return section.questions.filter((q) => q.hidden !== true)
}

function ferTypeLabel(key: string): string {
  const entry = ferTypes.value[key]
  return entry ? (resolveLang(entry.label, locale.value) ?? key) : key
}

function onPrint() {
  window.print()
}

async function load() {
  loading.value = true
  notFound.value = false
  const id = String(route.params.id)
  const version = String(route.params.version)
  try {
    const [loaded, ferTypesResult] = await Promise.all([
      getKnowledgeModel(id, version),
      getFerTypes().catch(() => ({ items: [], total: 0 })),
    ])
    model.value = loaded
    ferTypes.value = Object.fromEntries(ferTypesResult.items.map((f) => [f.key, f]))
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

onMounted(() => {
  const q = Number(route.query.declarations)
  declarationsPerQuestion.value = clampDeclarations(Number.isFinite(q) && q > 0 ? q : 3)
  void load()
})

watch(() => [route.params.id, route.params.version], load)
</script>

<style scoped>
.km-print-view {
  max-width: 800px;
  margin: 0 auto;
  padding: 1rem;
}

.loading,
.message-box {
  text-align: center;
  padding: 3rem 1rem;
}

.print-controls {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  padding-bottom: 1rem;
  margin-bottom: 1rem;
  border-bottom: 1px solid var(--color-border);
}

.declarations-field {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: var(--font-size-sm);
}

.declarations-field select {
  min-height: 44px;
  padding: 0.3rem 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
}

.btn {
  min-height: 44px;
  padding: 0.5rem 1.2rem;
  border: none;
  border-radius: var(--border-radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
}

.btn-primary {
  background-color: var(--color-primary);
  color: var(--color-primary-text);
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
}

.print-sheet {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding-bottom: 4rem;
}

.title-page {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.handout-title {
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.title-page h1 {
  margin: 0;
  color: var(--color-primary);
}

.ref-chip {
  font-family: monospace;
  font-size: var(--font-size-xs);
  color: var(--color-id-chip-text);
  background-color: var(--color-id-chip-bg);
  padding: 0.15rem 0.4rem;
  border-radius: var(--border-radius-sm);
  align-self: flex-start;
}

.section-toc {
  margin: 0.5rem 0;
  padding-left: 1.25rem;
}

.instructions {
  font-style: italic;
  color: var(--color-text-secondary);
}

.fill-line {
  display: flex;
  align-items: flex-end;
  border-bottom: 1px solid var(--color-border);
  min-height: 2rem;
  padding-bottom: 0.2rem;
}

.fill-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.comment-line {
  margin-top: 0.25rem;
}

.section-title {
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 0.4rem;
}

.question {
  padding: 0.75rem 0;
  border-bottom: 1px dashed var(--color-border);
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.question-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
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

.fer-type {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.question-text {
  margin: 0;
  font-weight: var(--font-weight-medium);
}

.question-help {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.decl-block {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  padding: 0.4rem 0;
}

.tick-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.tick-item {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: var(--font-size-xs);
}

.tick-box {
  display: inline-block;
  width: 3.5mm;
  height: 3.5mm;
  border: 1px solid var(--color-text);
}

.print-footer {
  margin-top: 2rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--color-border);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.print-footer p {
  margin: 0.15rem 0;
}
</style>
