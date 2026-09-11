<template>
  <div class="dashboard-home">
    <h1>{{ $t('dashboard.home.title') }}</h1>

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

    <p v-if="view.loading.value" class="loading">{{ $t('common.loading') }}</p>

    <div v-else-if="view.envelope.value" class="headline-row">
      <p class="headline-number">{{ headlineFipCount }}</p>
      <p class="headline-label">{{ $t('dashboard.home.fipsInPopulation') }}</p>
    </div>

    <nav class="view-cards no-print">
      <router-link v-for="card in cards" :key="card.name" :to="{ name: card.name, query: query }" class="view-card">
        <h2>{{ $t(card.titleKey) }}</h2>
        <p>{{ $t(card.descKey) }}</p>
      </router-link>
    </nav>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getCoverage, refreshDashboard } from '@/api/dashboard'
import { decodePopulationParam, emptyPopulationSpec, encodePopulationParam, formatCount } from '@/lib/dashboard'
import { useDashboardView } from '@/composables/useDashboardView'
import PopulationPicker from '@/components/PopulationPicker.vue'
import SnapshotBanner from '@/components/SnapshotBanner.vue'
import DegradedBanner from '@/components/DegradedBanner.vue'
import type { CoverageData, SavedPopulation } from '@/types/dashboard'

/**
 * `/dashboard?pop=…` (spec 13 §6.1): the population picker plus a
 * lightweight headline (the population's `fipCount`, from the cheapest
 * view — coverage) and navigation cards into the five views, each
 * carrying the same `pop` query param forward.
 */
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { t } = useI18n()

const isAdmin = computed(() => authStore.user?.role === 'admin')

const spec = ref(decodePopulationParam(String(route.query.pop ?? '')) ?? emptyPopulationSpec())
const savedLabel = ref<string | null>(null)
const savedFipCount = ref<number | null>(null)
const savedComputedAt = ref<string | null>(null)

const view = useDashboardView<CoverageData>()

const popParam = computed(() => String(route.query.pop ?? ''))

const query = computed(() => ({ pop: popParam.value || undefined }))

const cards = [
  { name: 'DashboardCoverage', titleKey: 'dashboard.nav.coverage', descKey: 'dashboard.home.coverageDesc' },
  { name: 'DashboardAdoption', titleKey: 'dashboard.nav.adoption', descKey: 'dashboard.home.adoptionDesc' },
  { name: 'DashboardSimilarity', titleKey: 'dashboard.nav.similarity', descKey: 'dashboard.home.similarityDesc' },
  { name: 'DashboardGaps', titleKey: 'dashboard.nav.gaps', descKey: 'dashboard.home.gapsDesc' },
  { name: 'DashboardEvolution', titleKey: 'dashboard.nav.evolution', descKey: 'dashboard.home.evolutionDesc' },
]

const bannerStatus = computed<'live' | 'snapshot' | 'pending'>(() => {
  if (view.pending.value) return 'pending'
  if (view.envelope.value?.tier === 'snapshot') return 'snapshot'
  return 'live'
})

const errorHint = computed(() => (view.errorBody.value?.hint as string | undefined) ?? null)
const errorMinimum = computed(() => (view.errorBody.value?.minimum as number | undefined) ?? null)

// `fipCount` is `null` whenever any FIP in the population is one the viewer
// could not open individually (spec 13 §2.4 k-anonymity) — the count itself
// would disclose that FIP, so the withheld case renders as text, never `0`.
const headlineFipCount = computed(() => {
  const count = view.envelope.value?.population.fipCount ?? null
  return count === null ? t('dashboard.home.fipCountWithheld') : formatCount(count)
})

function load() {
  if (!popParam.value) return
  view.run((ifNoneMatch) => getCoverage({ population: popParam.value }, { ifNoneMatch }))
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

watch(
  () => route.query.pop,
  () => {
    load()
  }
)

watch(spec, (value) => {
  try {
    const encoded = encodePopulationParam(value)
    if (encoded !== popParam.value) router.replace({ query: { ...route.query, pop: encoded } })
  } catch {
    // Too large to inline — the picker's own "Save" flow handles that case.
  }
})

onMounted(load)
</script>

<style scoped>
.dashboard-home {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.headline-row {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}

.headline-number {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  margin: 0;
}

.headline-label {
  margin: 0;
  color: var(--color-text-secondary);
}

.view-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(14rem, 1fr));
  gap: 0.75rem;
}

.view-card {
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  padding: 0.75rem 1rem;
  text-decoration: none;
  color: var(--color-text);
}

.view-card h2 {
  margin: 0 0 0.25rem;
  font-size: var(--font-size-md);
}

.view-card p {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.loading {
  color: var(--color-text-secondary);
}
</style>
