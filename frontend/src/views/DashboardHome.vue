<template>
  <div class="dashboard-home">
    <h1>{{ $t('dashboard.home.title') }}</h1>

    <PopulationPicker
      ref="pickerRef"
      v-model="spec"
      :saved-label="savedLabel"
      :saved-fip-count="savedFipCount"
      :saved-computed-at="savedComputedAt"
      @saved="onSaved"
    />

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

    <div v-else-if="isEmptyPopulation" class="empty-population">
      <p class="empty-title">{{ $t('dashboard.home.emptyTitle') }}</p>
      <p>{{ $t('dashboard.home.emptyBody') }}</p>
      <p v-if="emptyStateVisibilityHint">{{ $t('dashboard.home.emptyVisibilityHint') }}</p>
      <p v-if="emptyStateNetworkHint">{{ $t('dashboard.home.emptyNetworkHint') }}</p>
      <div class="empty-actions no-print">
        <button type="button" class="btn btn-secondary" @click="pickerRef?.focusTerm('session')">
          {{ $t('dashboard.home.emptyTrySession') }}
        </button>
        <button type="button" class="btn btn-secondary" @click="pickerRef?.focusTerm('questionnaire')">
          {{ $t('dashboard.home.emptyTryQuestionnaire') }}
        </button>
      </div>
    </div>

    <div v-else-if="view.envelope.value" class="headline-row">
      <p class="headline-number">{{ headlineFipCount }}</p>
      <p class="headline-label">{{ $t('dashboard.home.fipsInPopulation') }}</p>
      <p v-if="networkIngestedAtLabel" class="headline-network-stamp">{{ networkIngestedAtLabel }}</p>
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
import { getCoverage, listPopulations, refreshDashboard } from '@/api/dashboard'
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
const { t, locale } = useI18n()

const isAdmin = computed(() => authStore.user?.role === 'admin')

const spec = ref(decodePopulationParam(String(route.query.pop ?? '')) ?? emptyPopulationSpec())
const savedLabel = ref<string | null>(null)
const savedFipCount = ref<number | null>(null)
const savedComputedAt = ref<string | null>(null)
const pickerRef = ref<InstanceType<typeof PopulationPicker> | null>(null)
const networkIngestedAt = ref<string | null>(null)

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

// A resolved population of exactly zero FIPs (spec 13 §9 A8 follow-up) is a
// distinct state from `fipCount === null` (k-anonymity withholding a
// nonzero count, handled by `headlineFipCount` above) — an honest "why"
// instead of an empty headline/grids.
const isEmptyPopulation = computed(() => view.envelope.value?.population.fipCount === 0)

// §2.2 D9: public/network populations deliberately exclude `link`-visibility
// FIPs. This only ever names the *rule*, never asserts that excluded FIPs
// exist on this instance — that would be a count this component has not
// fetched and has no way to verify.
const emptyStateVisibilityHint = computed(() => {
  const terms = spec.value.include
  return terms.length > 0 && terms.every((term) => term.kind === 'public' || term.kind === 'network')
})

// The "network" population reads a local copy ingested by an admin (`python
// -m fipm ingest-network-fips`), not a live query — unlike the Network FIPs
// browse page, which proxies live to Nanopub Query. An empty network
// population here can therefore look like "the network is empty" when it
// really means "nothing has been ingested to this instance yet".
const emptyStateNetworkHint = computed(() => {
  const terms = spec.value.include
  return terms.length > 0 && terms.some((term) => term.kind === 'network')
})

// spec 13 §5.4/§9 Q4: "the ingest timestamp always visible" next to any
// network-bearing view. `GET /api/dashboard/populations`'s
// `networkIngestedAt` is fetched lazily, the first time the selected
// population includes a `network` term (rather than unconditionally on
// every visit), and cached here so switching terms back and forth does not
// refetch.
const hasNetworkTerm = computed(() => spec.value.include.some((term) => term.kind === 'network'))
const networkIngestedAtFetched = ref(false)

const networkIngestedAtLabel = computed(() => {
  if (!hasNetworkTerm.value || !networkIngestedAt.value) return null
  const date = new Date(networkIngestedAt.value).toLocaleDateString(locale.value)
  return t('dashboard.home.networkIngestedAt', { date })
})

async function fetchNetworkIngestedAt() {
  if (networkIngestedAtFetched.value) return
  networkIngestedAtFetched.value = true
  try {
    const result = await listPopulations()
    networkIngestedAt.value = result.networkIngestedAt
  } catch {
    // Populations endpoint unreachable — the stamp just stays hidden.
  }
}

watch(
  hasNetworkTerm,
  (value) => {
    if (value) fetchNetworkIngestedAt()
  },
  { immediate: true }
)

function load() {
  if (!popParam.value) return
  view.run((ifNoneMatch) => getCoverage({ population: popParam.value }, { ifNoneMatch }))
}

/**
 * Spec 13 §9 A8: `/dashboard` with no `pop` at all starts from the network
 * population once `ingest-network-fips` has run, else the public
 * population — `GET /api/dashboard/populations`'s `networkIngestedAt` is
 * the signal. Setting `spec.value` here reuses the existing `watch(spec,
 * …)` below to reflect the choice into the URL exactly as a user-driven
 * picker edit would, so the view cards and a copied link carry it too.
 */
async function applyDefaultPopulation() {
  let kind: 'public' | 'network' = 'public'
  try {
    const result = await listPopulations()
    networkIngestedAt.value = result.networkIngestedAt
    networkIngestedAtFetched.value = true
    if (result.networkIngestedAt) kind = 'network'
  } catch {
    // Populations endpoint unreachable — fall back to the public default
    // rather than leaving the picker empty and the page requesting nothing.
  }
  spec.value = decodePopulationParam(kind) ?? emptyPopulationSpec()
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

onMounted(async () => {
  if (!route.query.pop) {
    await applyDefaultPopulation()
    return
  }
  load()
})
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

.headline-network-stamp {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.empty-population {
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  padding: 0.75rem 1rem;
  background-color: var(--color-hover);
}

.empty-population p {
  margin: 0 0 0.5rem;
  color: var(--color-text-secondary);
}

.empty-title {
  font-weight: var(--font-weight-medium);
  color: var(--color-text) !important;
}

.empty-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-top: 0.5rem;
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
