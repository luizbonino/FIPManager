<template>
  <div class="dashboard-evolution">
    <header class="view-header">
      <h1>{{ $t('dashboard.evolution.title') }}</h1>
      <div class="controls no-print">
        <label class="field">
          <span>{{ $t('dashboard.evolution.groupBy') }}</span>
          <select v-model="groupBy">
            <option value="subPrinciple">{{ $t('dashboard.coverage.level.subPrinciple') }}</option>
            <option value="question">{{ $t('dashboard.coverage.level.question') }}</option>
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
      <section>
        <h2>{{ $t('dashboard.evolution.plannedTitle') }}</h2>
        <table class="evolution-table">
          <thead>
            <tr>
              <th scope="col">{{ $t('dashboard.evolution.colQuestion') }}</th>
              <th scope="col">{{ $t('dashboard.evolution.colStatus') }}</th>
              <th scope="col">{{ $t('dashboard.evolution.colFer') }}</th>
              <th scope="col">{{ $t('dashboard.evolution.colSuccessor') }}</th>
              <th scope="col">{{ $t('dashboard.evolution.colFips') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in view.envelope.value.data.planned" :key="i">
              <td>{{ row.questionId }}</td>
              <td>{{ $t(`declarationStatus.${statusI18nKey(row.status)}`) }}</td>
              <td>{{ row.ferLabel ?? row.ferKey }}</td>
              <td>{{ row.successorLabel ?? row.successorFerKey ?? '—' }}</td>
              <td>{{ formatCount(row.fips) }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section>
        <h2>{{ $t('dashboard.evolution.migrationTitle') }}</h2>
        <p v-if="view.envelope.value.data.truncated" class="disclosure">{{ $t('dashboard.evolution.truncated') }}</p>
        <table class="evolution-table">
          <thead>
            <tr>
              <th scope="col">{{ $t('dashboard.evolution.colFrom') }}</th>
              <th scope="col">{{ $t('dashboard.evolution.colTo') }}</th>
              <th scope="col">{{ $t('dashboard.evolution.colFips') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in view.envelope.value.data.migrations" :key="i">
              <td>{{ row.migratedFromId ? `${row.migratedFromId}@${row.migratedFromVersion}` : '—' }}</td>
              <td>{{ `${row.questionnaireId}@${row.questionnaireVersion}` }}</td>
              <td>{{ formatCount(row.fips) }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { dashboardCsvUrl, getEvolution, refreshDashboard } from '@/api/dashboard'
import { decodePopulationParam, emptyPopulationSpec, encodePopulationParam, formatCount } from '@/lib/dashboard'
import { useDashboardView } from '@/composables/useDashboardView'
import PopulationPicker from '@/components/PopulationPicker.vue'
import SnapshotBanner from '@/components/SnapshotBanner.vue'
import DegradedBanner from '@/components/DegradedBanner.vue'
import type { EvolutionData, SavedPopulation } from '@/types/dashboard'

/** `/dashboard/evolution?pop=…` (spec 13 §3.5/§6.2). */
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const isAdmin = computed(() => authStore.user?.role === 'admin')

const spec = ref(decodePopulationParam(String(route.query.pop ?? '')) ?? emptyPopulationSpec())
const savedLabel = ref<string | null>(null)
const savedFipCount = ref<number | null>(null)
const savedComputedAt = ref<string | null>(null)
const groupBy = ref<'question' | 'subPrinciple'>((route.query.groupBy as never) || 'subPrinciple')

const view = useDashboardView<EvolutionData>()
const popParam = computed(() => String(route.query.pop ?? ''))

const bannerStatus = computed<'live' | 'snapshot' | 'pending'>(() => {
  if (view.pending.value) return 'pending'
  if (view.envelope.value?.tier === 'snapshot') return 'snapshot'
  return 'live'
})
const errorHint = computed(() => (view.errorBody.value?.hint as string | undefined) ?? null)
const errorMinimum = computed(() => (view.errorBody.value?.minimum as number | undefined) ?? null)

const csvUrl = computed(() => dashboardCsvUrl('evolution', popParam.value, { groupBy: groupBy.value }))

function statusI18nKey(s: string): string {
  const map: Record<string, string> = {
    current: 'current',
    planned: 'planned',
    'planned-development': 'plannedDevelopment',
    'planned-replacement': 'plannedReplacement',
    none: 'none',
  }
  return map[s] ?? 'planned'
}

function load() {
  if (!popParam.value) return
  view.run((ifNoneMatch) => getEvolution({ population: popParam.value, groupBy: groupBy.value }, { ifNoneMatch }))
}

function onSaved(saved: SavedPopulation) {
  savedLabel.value = saved.label
  savedFipCount.value = saved.fipCount ?? null
  savedComputedAt.value = saved.createdAt ?? null
  router.replace({ query: { ...route.query, pop: saved.hash } })
}

async function onRefresh() {
  await refreshDashboard({ population: popParam.value, views: ['evolution'] })
  load()
}

watch([() => route.query.pop, groupBy], load)
watch(groupBy, (value) => {
  router.replace({ query: { ...route.query, groupBy: value } })
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
.dashboard-evolution {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
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

.evolution-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.evolution-table th,
.evolution-table td {
  text-align: left;
  padding: 0.4rem 0.5rem;
  border-bottom: 1px solid var(--color-border);
}

.loading {
  color: var(--color-text-secondary);
}
</style>
