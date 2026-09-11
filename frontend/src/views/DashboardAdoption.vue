<template>
  <div class="dashboard-adoption">
    <header class="view-header">
      <h1>{{ $t('dashboard.adoption.title') }}</h1>
      <div class="controls no-print">
        <label class="field">
          <span>{{ $t('dashboard.adoption.groupBy') }}</span>
          <select v-model="groupBy">
            <option value="fer">{{ $t('dashboard.adoption.groupByFer') }}</option>
            <option value="ferType">{{ $t('dashboard.adoption.groupByFerType') }}</option>
            <option value="area">{{ $t('dashboard.adoption.groupByArea') }}</option>
            <option value="question">{{ $t('dashboard.adoption.groupByQuestion') }}</option>
          </select>
        </label>
        <label class="field">
          <span>{{ $t('dashboard.adoption.status') }}</span>
          <select v-model="status">
            <option value="current">{{ $t('declarationStatus.current') }}</option>
            <option value="planned">{{ $t('declarationStatus.planned') }}</option>
            <option value="any">{{ $t('dashboard.adoption.statusAny') }}</option>
          </select>
        </label>
        <label class="field">
          <span>{{ $t('dashboard.adoption.catalogued') }}</span>
          <select v-model="catalogued">
            <option value="any">{{ $t('dashboard.adoption.cataloguedAny') }}</option>
            <option value="only">{{ $t('dashboard.adoption.cataloguedOnly') }}</option>
            <option value="exclude">{{ $t('dashboard.adoption.longTail') }}</option>
          </select>
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
      <p v-if="view.envelope.value.data.truncated" class="disclosure">
        {{ $t('dashboard.adoption.truncated', { total: formatCount(view.envelope.value.data.total) }) }}
      </p>
      <table class="adoption-table">
        <thead>
          <tr>
            <th scope="col">{{ $t('dashboard.adoption.colLabel') }}</th>
            <th scope="col">{{ $t('dashboard.adoption.colFerType') }}</th>
            <th scope="col">{{ $t('dashboard.adoption.colStatus') }}</th>
            <th scope="col">{{ $t('dashboard.adoption.colFips') }}</th>
            <th scope="col">{{ $t('dashboard.adoption.colShare') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in view.envelope.value.data.rows" :key="`${row.ferKey}-${row.status}`">
            <td>{{ row.label }}</td>
            <td>{{ row.ferType ?? '—' }}</td>
            <td>{{ $t(`declarationStatus.${statusI18nKey(row.status)}`) }}</td>
            <td>{{ formatCount(row.fips) }}</td>
            <td>{{ formatShare(row.share) }}</td>
          </tr>
        </tbody>
      </table>
      <div class="pager no-print">
        <button type="button" class="btn btn-secondary" :disabled="offset === 0" @click="offset = Math.max(0, offset - limit)">
          {{ $t('common.previous') }}
        </button>
        <span>{{ $t('dashboard.adoption.pageInfo', { from: offset + 1, to: offset + view.envelope.value.data.rows.length, total: formatCount(view.envelope.value.data.total) }) }}</span>
        <button type="button" class="btn btn-secondary" :disabled="offset + limit >= view.envelope.value.data.total" @click="offset += limit">
          {{ $t('common.next') }}
        </button>
      </div>
    </template>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { dashboardCsvUrl, getAdoption, refreshDashboard } from '@/api/dashboard'
import { decodePopulationParam, emptyPopulationSpec, encodePopulationParam, formatCount, formatShare } from '@/lib/dashboard'
import { useDashboardView } from '@/composables/useDashboardView'
import PopulationPicker from '@/components/PopulationPicker.vue'
import SnapshotBanner from '@/components/SnapshotBanner.vue'
import DegradedBanner from '@/components/DegradedBanner.vue'
import type { AdoptionData, SavedPopulation } from '@/types/dashboard'

/**
 * `/dashboard/adoption?pop=…&status=…&catalogued=…&page=…` (spec 13
 * §3.2/§6.1). Server-paginated, 50 rows a page (spec 13 §6.2) — every
 * control here refetches, unlike coverage's client-only `groupBy`.
 */
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const isAdmin = computed(() => authStore.user?.role === 'admin')

const spec = ref(decodePopulationParam(String(route.query.pop ?? '')) ?? emptyPopulationSpec())
const savedLabel = ref<string | null>(null)
const savedFipCount = ref<number | null>(null)
const savedComputedAt = ref<string | null>(null)

const groupBy = ref<'fer' | 'ferType' | 'area' | 'question'>((route.query.groupBy as never) || 'fer')
const status = ref<'current' | 'planned' | 'any'>((route.query.status as never) || 'current')
const catalogued = ref<'only' | 'exclude' | 'any'>((route.query.catalogued as never) || 'any')
const offset = ref(Number(route.query.offset) || 0)
const limit = 50

const view = useDashboardView<AdoptionData>()
const popParam = computed(() => String(route.query.pop ?? ''))

const bannerStatus = computed<'live' | 'snapshot' | 'pending'>(() => {
  if (view.pending.value) return 'pending'
  if (view.envelope.value?.tier === 'snapshot') return 'snapshot'
  return 'live'
})
const errorHint = computed(() => (view.errorBody.value?.hint as string | undefined) ?? null)
const errorMinimum = computed(() => (view.errorBody.value?.minimum as number | undefined) ?? null)

const csvUrl = computed(() => dashboardCsvUrl('adoption', popParam.value, { status: status.value, catalogued: catalogued.value, groupBy: groupBy.value }))

function statusI18nKey(s: string): string {
  const map: Record<string, string> = {
    current: 'current',
    planned: 'planned',
    'planned-development': 'plannedDevelopment',
    'planned-replacement': 'plannedReplacement',
    none: 'none',
  }
  return map[s] ?? 'current'
}

function load() {
  if (!popParam.value) return
  view.run((ifNoneMatch) =>
    getAdoption({ population: popParam.value, groupBy: groupBy.value, status: status.value, catalogued: catalogued.value, limit, offset: offset.value }, { ifNoneMatch })
  )
}

function onSaved(saved: SavedPopulation) {
  savedLabel.value = saved.label
  savedFipCount.value = saved.fipCount ?? null
  savedComputedAt.value = saved.createdAt ?? null
  router.replace({ query: { ...route.query, pop: saved.hash } })
}

async function onRefresh() {
  await refreshDashboard({ population: popParam.value, views: ['adoption'] })
  load()
}

watch([() => route.query.pop, groupBy, status, catalogued, offset], load)

watch([groupBy, status, catalogued, offset], () => {
  router.replace({
    query: { ...route.query, groupBy: groupBy.value, status: status.value, catalogued: catalogued.value, offset: offset.value || undefined },
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
.dashboard-adoption {
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

.adoption-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.adoption-table th,
.adoption-table td {
  text-align: left;
  padding: 0.4rem 0.5rem;
  border-bottom: 1px solid var(--color-border);
}

.pager {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: var(--font-size-sm);
}

.loading {
  color: var(--color-text-secondary);
}
</style>
