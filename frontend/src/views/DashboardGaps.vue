<template>
  <div class="dashboard-gaps">
    <header class="view-header">
      <h1>{{ $t('dashboard.gaps.title') }}</h1>
      <div class="controls no-print">
        <label class="field">
          <span>{{ $t('dashboard.gaps.minShare') }}</span>
          <input v-model.number="minShare" type="number" min="0" max="1" step="0.05" />
        </label>
        <a class="btn btn-secondary" :href="csvUrl">{{ $t('dashboard.csv') }}</a>
      </div>
    </header>

    <PopulationPicker v-model="spec" :saved-label="savedLabel" :saved-fip-count="savedFipCount" :saved-computed-at="savedComputedAt" @saved="onSaved" />

    <SnapshotBanner
      :status="bannerStatus"
      :computed-at="view.envelope.value?.computedAt"
      :attempt="view.pendingAttempt.value"
      :max-attempts="view.maxPollAttempts"
      @refresh="onRefresh"
    />
    <DegradedBanner v-if="view.envelope.value?.degraded" reason="projection_stale" variant="degraded" :stale-fips="view.envelope.value?.staleFips" />
    <DegradedBanner v-if="view.errorCode.value" :reason="view.errorCode.value" variant="error" :is-admin="isAdmin" :hint="errorHint" :minimum="errorMinimum" />

    <p v-if="view.loading.value && !view.envelope.value" class="loading">{{ $t('common.loading') }}</p>

    <template v-else-if="view.envelope.value">
      <p v-if="view.envelope.value.data.truncated" class="disclosure">{{ $t('dashboard.gaps.truncated') }}</p>
      <table class="gaps-table">
        <thead>
          <tr>
            <th scope="col">{{ $t('dashboard.gaps.colQuestion') }}</th>
            <th scope="col">{{ $t('dashboard.gaps.colUnanswered') }}</th>
            <th scope="col">{{ $t('dashboard.gaps.colNone') }}</th>
            <th scope="col">{{ $t('dashboard.gaps.colNotApplicable') }}</th>
            <th scope="col">{{ $t('dashboard.gaps.colPlanned') }}</th>
            <th v-if="hasCoherenceFlags" scope="col">{{ $t('dashboard.gaps.colCoherence') }}</th>
            <th v-if="hasTypeMismatches" scope="col">{{ $t('dashboard.gaps.colTypeMismatch') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in visibleRows" :key="row.questionId">
            <td>{{ row.questionId }}</td>
            <td>{{ formatCount(row.unanswered) }}</td>
            <td>{{ formatCount(row.noneOnly) }}</td>
            <td>{{ formatCount(row.notApplicable) }}</td>
            <td>{{ formatCount(row.plannedOnly) }}</td>
            <td v-if="hasCoherenceFlags">{{ formatCount(row.coherenceFlags) }}</td>
            <td v-if="hasTypeMismatches">{{ formatCount(row.typeMismatches) }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { dashboardCsvUrl, getGaps, refreshDashboard } from '@/api/dashboard'
import { decodePopulationParam, emptyPopulationSpec, encodePopulationParam, formatCount } from '@/lib/dashboard'
import { useDashboardView } from '@/composables/useDashboardView'
import PopulationPicker from '@/components/PopulationPicker.vue'
import SnapshotBanner from '@/components/SnapshotBanner.vue'
import DegradedBanner from '@/components/DegradedBanner.vue'
import type { GapsData, SavedPopulation } from '@/types/dashboard'

/**
 * `/dashboard/gaps?pop=…` (spec 13 §3.4/§6.2): a question-indexed table,
 * one page, ≤500 rows by construction (bounded by the questionnaire, not
 * the population). `coherenceFlags`/`typeMismatches` columns hide when
 * every value is 0 (spec 12 §A2/§A3 not landed yet) — no dashboard change
 * needed when they do.
 */
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const isAdmin = computed(() => authStore.user?.role === 'admin')

const spec = ref(decodePopulationParam(String(route.query.pop ?? '')) ?? emptyPopulationSpec())
const savedLabel = ref<string | null>(null)
const savedFipCount = ref<number | null>(null)
const savedComputedAt = ref<string | null>(null)
const minShare = ref(Number(route.query.minShare) || 0)

const view = useDashboardView<GapsData>()
const popParam = computed(() => String(route.query.pop ?? ''))

const visibleRows = computed(() => view.envelope.value?.data.rows ?? [])
const hasCoherenceFlags = computed(() => visibleRows.value.some((r) => r.coherenceFlags > 0))
const hasTypeMismatches = computed(() => visibleRows.value.some((r) => r.typeMismatches > 0))

const bannerStatus = computed<'live' | 'snapshot' | 'pending'>(() => {
  if (view.pending.value) return 'pending'
  if (view.envelope.value?.tier === 'snapshot') return 'snapshot'
  return 'live'
})
const errorHint = computed(() => (view.errorBody.value?.hint as string | undefined) ?? null)
const errorMinimum = computed(() => (view.errorBody.value?.minimum as number | undefined) ?? null)

const csvUrl = computed(() => dashboardCsvUrl('gaps', popParam.value, { minShare: minShare.value || undefined }))

function load() {
  if (!popParam.value) return
  view.run((ifNoneMatch) => getGaps({ population: popParam.value, minShare: minShare.value }, { ifNoneMatch }))
}

function onSaved(saved: SavedPopulation) {
  savedLabel.value = saved.label
  savedFipCount.value = saved.fipCount ?? null
  savedComputedAt.value = saved.createdAt ?? null
  router.replace({ query: { ...route.query, pop: saved.hash } })
}

async function onRefresh() {
  await refreshDashboard({ population: popParam.value, views: ['gaps'] })
  load()
}

watch([() => route.query.pop, minShare], load)
watch(minShare, (value) => {
  router.replace({ query: { ...route.query, minShare: value || undefined } })
})
watch(spec, (value) => {
  try {
    const encoded = encodePopulationParam(value)
    if (encoded !== popParam.value) router.replace({ query: { ...route.query, pop: encoded } })
  } catch {
    // Too large to inline — use PopulationPicker's Save instead.
  }
})

onMounted(load)
</script>

<style scoped>
.dashboard-gaps {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.view-header {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.controls {
  display: flex;
  align-items: flex-end;
  gap: 1rem;
  flex-wrap: wrap;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: var(--font-size-sm);
}

.field input {
  min-height: 44px;
  padding: 0.3rem 0.5rem;
  width: 6rem;
}

.btn {
  min-height: 44px;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: var(--border-radius-sm);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
}

.disclosure {
  font-size: var(--font-size-xs);
  background-color: var(--color-hover);
  padding: 0.35rem 0.6rem;
  border-radius: var(--border-radius-sm);
}

.gaps-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.gaps-table th,
.gaps-table td {
  text-align: left;
  padding: 0.4rem 0.5rem;
  border-bottom: 1px solid var(--color-border);
}

.loading {
  color: var(--color-text-secondary);
}
</style>
