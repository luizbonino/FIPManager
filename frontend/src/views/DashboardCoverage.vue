<template>
  <div class="dashboard-coverage">
    <header class="view-header">
      <h1>{{ $t('dashboard.coverage.title') }}</h1>
      <div class="controls no-print">
        <label class="field">
          <span>{{ $t('dashboard.coverage.groupBy') }}</span>
          <select v-model="groupBy">
            <option value="question">{{ $t('dashboard.coverage.level.question') }}</option>
            <option value="subPrinciple">{{ $t('dashboard.coverage.level.subPrinciple') }}</option>
            <option value="principle">{{ $t('dashboard.coverage.level.principle') }}</option>
            <option value="group">{{ $t('dashboard.coverage.level.group') }}</option>
          </select>
        </label>
        <label class="field">
          <span>{{ $t('dashboard.coverage.scope') }}</span>
          <select v-model="scope">
            <option value="any">{{ $t('dashboard.coverage.scopeAny') }}</option>
            <option value="metadata">{{ $t('dashboard.coverage.scopeMetadata') }}</option>
            <option value="data">{{ $t('dashboard.coverage.scopeData') }}</option>
          </select>
        </label>
        <label class="toggle">
          <input v-model="includeAssurance" type="checkbox" />
          {{ $t('dashboard.coverage.includeAssurance') }}
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
    <DegradedBanner
      v-if="view.envelope.value?.degraded"
      reason="projection_stale"
      variant="degraded"
      :stale-fips="view.envelope.value?.staleFips"
    />
    <DegradedBanner v-if="view.errorCode.value" :reason="view.errorCode.value" variant="error" :is-admin="isAdmin" :hint="errorHint" :minimum="errorMinimum" />

    <p v-if="view.loading.value && !view.envelope.value" class="loading">{{ $t('common.loading') }}</p>

    <template v-else-if="rolledRows.length > 0 || view.envelope.value">
      <p class="totals" v-if="view.envelope.value">
        {{ $t('dashboard.coverage.totals', { fips: formatCount(view.envelope.value.data.totals.fips), cells: formatCount(view.envelope.value.data.totals.cells) }) }}
      </p>
      <CoverageHeatMap :rows="rolledRows" />
      <DashboardLegend />
    </template>

    <div v-if="pendingRolledRows.length > 0" class="stale-payload dimmed">
      <p class="stale-label">{{ $t('dashboard.snapshot.staleShownBelow') }}</p>
      <CoverageHeatMap :rows="pendingRolledRows" />
    </div>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { dashboardCsvUrl, getCoverage, refreshDashboard } from '@/api/dashboard'
import {
  decodePopulationParam,
  emptyPopulationSpec,
  encodePopulationParam,
  formatCount,
  rollupCoverage,
} from '@/lib/dashboard'
import { useDashboardView } from '@/composables/useDashboardView'
import PopulationPicker from '@/components/PopulationPicker.vue'
import SnapshotBanner from '@/components/SnapshotBanner.vue'
import DegradedBanner from '@/components/DegradedBanner.vue'
import CoverageHeatMap from '@/components/CoverageHeatMap.vue'
import DashboardLegend from '@/components/DashboardLegend.vue'
import '@/assets/print-dashboard.css'
import type { CoverageData, GroupingLevel, SavedPopulation } from '@/types/dashboard'

/**
 * `/dashboard/coverage?pop=…&groupBy=…&scope=…` (spec 13 §3.1/§6.1).
 * `groupBy` never refetches (spec 13 AC-3) — the API call always requests
 * `groupBy=question` (see `api/dashboard.ts::getCoverage`) and
 * `lib/dashboard.ts::rollupCoverage` re-derives the display level
 * client-side, exactly like `SessionMatrix.vue`'s language switch.
 * `scope`/`includeAssurance`/`population` do refetch — they change what
 * the server aggregates over.
 */
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const isAdmin = computed(() => authStore.user?.role === 'admin')

const spec = ref(decodePopulationParam(String(route.query.pop ?? '')) ?? emptyPopulationSpec())
const savedLabel = ref<string | null>(null)
const savedFipCount = ref<number | null>(null)
const savedComputedAt = ref<string | null>(null)

const groupBy = ref<GroupingLevel>((route.query.groupBy as GroupingLevel) || 'subPrinciple')
const scope = ref<'metadata' | 'data' | 'any'>((route.query.scope as 'metadata' | 'data' | 'any') || 'any')
const includeAssurance = ref(route.query.includeAssurance === '1')

const view = useDashboardView<CoverageData>()

const popParam = computed(() => String(route.query.pop ?? ''))

const rolledRows = computed(() => (view.envelope.value ? rollupCoverage(view.envelope.value.data, groupBy.value) : []))
const pendingRolledRows = computed(() => (view.pending.value && view.stalePayload.value ? rollupCoverage(view.stalePayload.value, groupBy.value) : []))

const bannerStatus = computed<'live' | 'snapshot' | 'pending'>(() => {
  if (view.pending.value) return 'pending'
  if (view.envelope.value?.tier === 'snapshot') return 'snapshot'
  return 'live'
})

const errorHint = computed(() => (view.errorBody.value?.hint as string | undefined) ?? null)
const errorMinimum = computed(() => (view.errorBody.value?.minimum as number | undefined) ?? null)

const csvUrl = computed(() =>
  dashboardCsvUrl('coverage', popParam.value, { scope: scope.value, includeAssurance: includeAssurance.value ? 1 : undefined })
)

function load() {
  if (!popParam.value) return
  view.run((ifNoneMatch) =>
    getCoverage({ population: popParam.value, scope: scope.value, includeAssurance: includeAssurance.value }, { ifNoneMatch })
  )
}

function onSaved(saved: SavedPopulation) {
  savedLabel.value = saved.label
  savedFipCount.value = saved.fipCount ?? null
  savedComputedAt.value = saved.createdAt ?? null
  router.replace({ query: { ...route.query, pop: saved.hash } })
}

async function onRefresh() {
  await refreshDashboard({ population: popParam.value, views: ['coverage'] })
  load()
}

// Population / scope / includeAssurance changes refetch; groupBy alone
// only updates the URL and re-derives client-side (no watcher call to `load`).
watch([() => route.query.pop, scope, includeAssurance], load)

// A single combined watcher, not one per field: three independent
// `router.replace` calls racing against each other's async navigation
// would let a later field's `...route.query` spread read a stale
// snapshot and clobber an earlier field's still-in-flight update.
watch([groupBy, scope, includeAssurance], ([groupByValue, scopeValue, includeAssuranceValue]) => {
  router.replace({
    query: { ...route.query, groupBy: groupByValue, scope: scopeValue, includeAssurance: includeAssuranceValue ? '1' : undefined },
  })
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
.dashboard-coverage {
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

.field select {
  min-height: 44px;
  padding: 0.3rem 0.5rem;
}

.toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: var(--font-size-sm);
  min-height: 44px;
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

.totals {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  margin: 0;
}

.loading {
  color: var(--color-text-secondary);
}

.stale-payload.dimmed {
  opacity: 0.5;
}

.stale-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}
</style>
