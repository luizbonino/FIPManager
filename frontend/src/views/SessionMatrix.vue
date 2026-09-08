<template>
  <div class="session-matrix-view">
    <div v-if="loading" class="loading">
      <p>{{ $t('common.loading') }}</p>
    </div>

    <div v-else-if="notFound" class="message-box">
      <p>{{ $t('common.notFound') }}</p>
      <router-link to="/" class="btn btn-secondary no-print">{{ $t('nav.home') }}</router-link>
    </div>

    <template v-else-if="session">
      <header class="matrix-header">
        <div class="header-row">
          <h1>{{ $t('matrix.title') }}</h1>
          <span class="join-code-chip">{{ session.joinCode }}</span>
          <p v-if="store.reconnecting" class="reconnecting no-print">
            <span class="dot" aria-hidden="true" />
            {{ $t('sessionAdmin.reconnecting') }}
          </p>
        </div>
        <p class="session-title">{{ session.title }}</p>
        <p v-if="matrix" class="subtitle">
          {{ $t('matrix.subtitle', { fips: matrix.columns.length, questions: matrix.questionCount }) }}
        </p>

        <div class="controls no-print">
          <LanguageSwitcher />
          <label class="toggle">
            <input v-model="onlyCurrent" type="checkbox" />
            {{ $t('matrix.onlyCurrent') }}
          </label>
          <label class="toggle">
            <input v-model="hideUnanswered" type="checkbox" />
            {{ $t('matrix.hideUnanswered') }}
          </label>
          <label class="toggle">
            <input v-model="compact" type="checkbox" />
            {{ $t('matrix.compact') }}
          </label>
          <button type="button" class="btn btn-secondary" @click="printPage">{{ $t('matrix.print') }}</button>
          <a class="btn btn-secondary" :href="sessionExportTtlUrl(session.id)">{{ $t('export.sessionTtl') }}</a>
        </div>

        <MatrixLegend />
      </header>

      <p v-if="store.fips.length === 0" class="empty-state">{{ $t('matrix.noFips') }}</p>
      <MatrixView v-else-if="matrix" :matrix="matrix" :compact="compact" />
    </template>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useSessionStore } from '@/stores/session'
import { sessionExportTtlUrl } from '@/api/sessions'
import { getKnowledgeModel } from '@/api/knowledgeModels'
import { listFers } from '@/api/fers'
import { getFerTypes } from '@/api/ferTypes'
import { applyMatrixOptions, buildMatrix, type MatrixOptions } from '@/lib/matrix'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import MatrixLegend from '@/components/MatrixLegend.vue'
import MatrixView from '@/components/MatrixView.vue'
import '@/assets/print-matrix.css'
import type { FerOut, FerType, KnowledgeModelOut } from '@/types/api'

/**
 * Spec 03 §1.3: everything here is derived client-side from calls the app
 * already makes — no `GET /api/sessions/{id}/matrix` endpoint exists. A
 * non-owner gets 404 from `GET /api/sessions/{id}`, rendered as
 * `common.notFound` (owner/admin-only, spec 03 §5 A1).
 */
const OPTS_KEY = 'fipm.matrix.opts'

const route = useRoute()
const { locale } = useI18n()
const store = useSessionStore()

const loading = ref(true)
const notFound = ref(false)
const km = ref<KnowledgeModelOut | null>(null)
const fers = ref<Map<string, FerOut>>(new Map())
const ferTypes = ref<Map<string, FerType>>(new Map())

const onlyCurrent = ref(false)
const hideUnanswered = ref(false)
const compact = ref(false)

function loadOpts() {
  try {
    const raw = localStorage.getItem(OPTS_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw) as Partial<Record<string, boolean>>
    onlyCurrent.value = !!parsed.onlyCurrent
    hideUnanswered.value = !!parsed.hideUnanswered
    compact.value = !!parsed.compact
  } catch {
    // Storage unavailable or corrupt: fall back to the defaults.
  }
}

function saveOpts() {
  try {
    localStorage.setItem(
      OPTS_KEY,
      JSON.stringify({
        onlyCurrent: onlyCurrent.value,
        hideUnanswered: hideUnanswered.value,
        compact: compact.value,
      })
    )
  } catch {
    // Storage unavailable: toggles simply won't persist across reloads.
  }
}

watch([onlyCurrent, hideUnanswered, compact], saveOpts)

const session = computed(() => store.session)

// Re-derived whenever the poll refreshes `store.fips` or the locale
// switches — no refetch either way (spec 03 §1.4).
const rawMatrix = computed(() => {
  if (!km.value) return null
  return buildMatrix(store.fips, km.value, fers.value, ferTypes.value, locale.value)
})

const matrixOptions = computed<MatrixOptions>(() => ({
  onlyCurrent: onlyCurrent.value,
  hideUnanswered: hideUnanswered.value,
}))

const matrix = computed(() => (rawMatrix.value ? applyMatrixOptions(rawMatrix.value, matrixOptions.value) : null))

function printPage() {
  window.print()
}

async function init() {
  loadOpts()
  loading.value = true
  notFound.value = false
  const id = String(route.params.id)
  try {
    await store.load(id)
  } catch {
    notFound.value = true
    loading.value = false
    return
  }
  await store.loadFips()
  store.startPolling()
  try {
    const [kmResult, fersResult, ferTypesResult] = await Promise.all([
      getKnowledgeModel(store.session!.questionnaireId, store.session!.questionnaireVersion),
      listFers({ limit: 500 }),
      getFerTypes(),
    ])
    km.value = kmResult
    fers.value = new Map(fersResult.items.map((f) => [f.id, f]))
    ferTypes.value = new Map(ferTypesResult.items.map((f) => [f.key, f]))
  } catch {
    // The FIP list still renders via SessionFipList-style fallback; the
    // matrix body simply cannot draw without the knowledge model.
  }
  loading.value = false
}

onMounted(init)

onUnmounted(() => {
  store.stopPolling()
})
</script>

<style scoped>
.session-matrix-view {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-width: 100%;
}

.loading,
.message-box {
  text-align: center;
  padding: 3rem 1rem;
}

.matrix-header {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.header-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.header-row h1 {
  margin: 0;
  font-size: var(--font-size-xl);
}

.join-code-chip {
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: var(--font-size-sm);
  letter-spacing: 0.08em;
  padding: 0.15rem 0.6rem;
  border-radius: var(--border-radius-sm);
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
}

.reconnecting {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin: 0;
}

.reconnecting .dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background-color: var(--color-status-planned);
}

.session-title {
  margin: 0;
  font-weight: var(--font-weight-medium);
}

.subtitle {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.controls {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: var(--font-size-sm);
  min-height: 44px;
}

.empty-state {
  color: var(--color-text-secondary);
  padding: 1rem 0;
}

.btn {
  min-height: 44px;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: var(--border-radius-sm);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
}
</style>
