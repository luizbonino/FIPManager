<template>
  <div class="dashboard-similarity">
    <header class="view-header">
      <h1>{{ $t('dashboard.similarity.title') }}</h1>
      <div class="controls no-print">
        <label class="field">
          <span>{{ $t('dashboard.similarity.weighting') }}</span>
          <select v-model="weighting">
            <option value="principle">{{ $t('dashboard.similarity.weightingPrinciple') }}</option>
            <option value="question">{{ $t('dashboard.similarity.weightingQuestion') }}</option>
            <option value="letter">{{ $t('dashboard.similarity.weightingLetter') }}</option>
          </select>
        </label>
      </div>
    </header>

    <PopulationPicker v-model="spec" :saved-label="savedLabel" :saved-fip-count="savedFipCount" :saved-computed-at="savedComputedAt" @saved="onSaved" />

    <nav class="tabs no-print" role="tablist">
      <button type="button" role="tab" :aria-selected="tab === 'neighbours'" :class="{ active: tab === 'neighbours' }" @click="tab = 'neighbours'">
        {{ $t('dashboard.similarity.tabNeighbours') }}
      </button>
      <button type="button" role="tab" :aria-selected="tab === 'distribution'" :class="{ active: tab === 'distribution' }" @click="tab = 'distribution'">
        {{ $t('dashboard.similarity.tabDistribution') }}
      </button>
      <button type="button" role="tab" :aria-selected="tab === 'clusters'" :class="{ active: tab === 'clusters' }" @click="tab = 'clusters'">
        {{ $t('dashboard.similarity.tabClusters') }}
      </button>
    </nav>

    <section v-if="tab === 'neighbours'" class="panel">
      <FipTypeahead v-model="fipId" :population="popParam" />

      <SnapshotBanner :status="neighboursBannerStatus" :computed-at="neighboursView.envelope.value?.computedAt" :attempt="neighboursView.pendingAttempt.value" :max-attempts="neighboursView.maxPollAttempts" @refresh="() => onRefresh('neighbours')" />
      <DegradedBanner v-if="neighboursView.errorCode.value" :reason="neighboursView.errorCode.value" variant="error" :is-admin="isAdmin" :hint="neighboursErrorHint" :minimum="neighboursErrorMinimum" />

      <NeighbourList
        v-if="neighboursView.envelope.value"
        :neighbours="neighboursView.envelope.value.data.neighbours"
        :candidate-budget-exhausted="neighboursView.envelope.value.data.candidateBudgetExhausted"
        :posting-truncated="neighboursView.envelope.value.data.postingTruncated"
        :skipped-popular-keys="neighboursView.envelope.value.data.skippedPopularKeys"
      />
    </section>

    <section v-else-if="tab === 'distribution'" class="panel">
      <SnapshotBanner :status="mapBannerStatus" :computed-at="mapView.envelope.value?.computedAt" :attempt="mapView.pendingAttempt.value" :max-attempts="mapView.maxPollAttempts" @refresh="() => onRefresh('map')" />
      <DegradedBanner v-if="mapView.errorCode.value" :reason="mapView.errorCode.value" variant="error" :is-admin="isAdmin" :hint="mapErrorHint" :minimum="mapErrorMinimum" />

      <template v-if="mapView.envelope.value">
        <SimilarityHistogram :histogram="mapView.envelope.value.data.histogram" />

        <div v-if="mapView.envelope.value.data.hotBuckets.length > 0" class="disclosure">
          {{ $t('dashboard.similarity.hotBuckets', { count: mapView.envelope.value.data.hotBuckets.length }) }}
        </div>

        <p v-if="!mapView.envelope.value.data.scatterAvailable" class="scatter-unavailable">
          {{ $t('dashboard.similarity.scatterUnavailable') }}
        </p>
        <svg v-else-if="mapView.envelope.value.data.nodes" class="scatter" viewBox="0 0 300 300" role="img" :aria-label="$t('dashboard.similarity.scatterLabel')">
          <circle v-for="(node, i) in mapView.envelope.value.data.nodes" :key="node.id" :cx="20 + (i % 15) * 18" :cy="20 + Math.floor(i / 15) * 18" r="5" class="scatter-node" />
        </svg>
      </template>
    </section>

    <section v-else class="panel">
      <SnapshotBanner :status="clustersBannerStatus" :computed-at="clustersView.envelope.value?.computedAt" :attempt="clustersView.pendingAttempt.value" :max-attempts="clustersView.maxPollAttempts" @refresh="() => onRefresh('clusters')" />
      <DegradedBanner v-if="clustersView.errorCode.value" :reason="clustersView.errorCode.value" variant="error" :is-admin="isAdmin" :hint="clustersErrorHint" :minimum="clustersErrorMinimum" />

      <template v-if="clustersView.envelope.value">
        <p v-if="clustersView.envelope.value.data.truncated" class="disclosure">{{ $t('dashboard.similarity.clustersTruncated') }}</p>
        <div class="cluster-grid">
          <ClusterCard v-for="cluster in clustersView.envelope.value.data.clusters" :key="cluster.id" :cluster="cluster" />
        </div>
      </template>
    </section>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getSimilarityClusters, getSimilarityMap, getSimilarityNeighbours, refreshDashboard } from '@/api/dashboard'
import { decodePopulationParam, emptyPopulationSpec, encodePopulationParam } from '@/lib/dashboard'
import { useDashboardView } from '@/composables/useDashboardView'
import PopulationPicker from '@/components/PopulationPicker.vue'
import SnapshotBanner from '@/components/SnapshotBanner.vue'
import DegradedBanner from '@/components/DegradedBanner.vue'
import NeighbourList from '@/components/NeighbourList.vue'
import SimilarityHistogram from '@/components/SimilarityHistogram.vue'
import ClusterCard from '@/components/ClusterCard.vue'
import FipTypeahead from '@/components/FipTypeahead.vue'
import type { ClustersData, MapData, NeighboursData, SavedPopulation, SimilarityWeighting } from '@/types/dashboard'

/**
 * `/dashboard/similarity?pop=…&fip=…&weighting=…` (spec 13 §3.3/§6.1/§6.2):
 * three panels — Neighbours, Distribution (histogram + convergence +
 * scatter-or-explanation), Clusters. `…/pair` has no dedicated panel here:
 * §6.2 names exactly three panels for this view, not four.
 */
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const isAdmin = computed(() => authStore.user?.role === 'admin')

const spec = ref(decodePopulationParam(String(route.query.pop ?? '')) ?? emptyPopulationSpec())
const savedLabel = ref<string | null>(null)
const savedFipCount = ref<number | null>(null)
const savedComputedAt = ref<string | null>(null)

const tab = ref<'neighbours' | 'distribution' | 'clusters'>('neighbours')
const weighting = ref<SimilarityWeighting>((route.query.weighting as SimilarityWeighting) || 'principle')
const fipId = ref(String(route.query.fip ?? ''))

const popParam = computed(() => String(route.query.pop ?? ''))

const neighboursView = useDashboardView<NeighboursData>()
const mapView = useDashboardView<MapData>()
const clustersView = useDashboardView<ClustersData>()

function bannerStatusFor<T>(v: ReturnType<typeof useDashboardView<T>>): 'live' | 'snapshot' | 'pending' {
  if (v.pending.value) return 'pending'
  if (v.envelope.value?.tier === 'snapshot') return 'snapshot'
  return 'live'
}
const neighboursBannerStatus = computed(() => bannerStatusFor(neighboursView))
const mapBannerStatus = computed(() => bannerStatusFor(mapView))
const clustersBannerStatus = computed(() => bannerStatusFor(clustersView))

const neighboursErrorHint = computed(() => (neighboursView.errorBody.value?.hint as string | undefined) ?? null)
const neighboursErrorMinimum = computed(() => (neighboursView.errorBody.value?.minimum as number | undefined) ?? null)
const mapErrorHint = computed(() => (mapView.errorBody.value?.hint as string | undefined) ?? null)
const mapErrorMinimum = computed(() => (mapView.errorBody.value?.minimum as number | undefined) ?? null)
const clustersErrorHint = computed(() => (clustersView.errorBody.value?.hint as string | undefined) ?? null)
const clustersErrorMinimum = computed(() => (clustersView.errorBody.value?.minimum as number | undefined) ?? null)

function loadNeighbours() {
  if (!popParam.value || !fipId.value) return
  neighboursView.run((ifNoneMatch) => getSimilarityNeighbours({ fip: fipId.value, population: popParam.value, weighting: weighting.value }, { ifNoneMatch }))
}
function loadMap() {
  if (!popParam.value) return
  mapView.run((ifNoneMatch) => getSimilarityMap({ population: popParam.value, weighting: weighting.value }, { ifNoneMatch }))
}
function loadClusters() {
  if (!popParam.value) return
  clustersView.run((ifNoneMatch) => getSimilarityClusters({ population: popParam.value }, { ifNoneMatch }))
}

function onSaved(saved: SavedPopulation) {
  savedLabel.value = saved.label
  savedFipCount.value = saved.fipCount ?? null
  savedComputedAt.value = saved.createdAt ?? null
  router.replace({ query: { ...route.query, pop: saved.hash } })
}

async function onRefresh(view: 'neighbours' | 'map' | 'clusters') {
  await refreshDashboard({ population: popParam.value, views: [view === 'map' ? 'map' : view === 'clusters' ? 'clusters' : 'neighbours'] })
  if (view === 'neighbours') loadNeighbours()
  else if (view === 'map') loadMap()
  else loadClusters()
}

watch([() => route.query.pop, weighting, fipId], () => {
  loadNeighbours()
  loadMap()
})
watch(() => route.query.pop, loadClusters)

watch([weighting, fipId], () => {
  router.replace({ query: { ...route.query, weighting: weighting.value, fip: fipId.value || undefined } })
})
watch(spec, (value) => {
  try {
    const encoded = encodePopulationParam(value)
    if (encoded !== popParam.value) router.replace({ query: { ...route.query, pop: encoded } })
  } catch {
    // Too large to inline — use PopulationPicker's Save instead.
  }
})

onMounted(() => {
  loadNeighbours()
  loadMap()
  loadClusters()
})
</script>

<style scoped>
.dashboard-similarity {
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
  gap: 1rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: var(--font-size-sm);
}

.field input,
.field select {
  min-height: 44px;
  padding: 0.3rem 0.5rem;
}

.tabs {
  display: flex;
  gap: 0.5rem;
  border-bottom: 1px solid var(--color-border);
}

.tabs button {
  min-height: 44px;
  padding: 0.5rem 1rem;
  border: none;
  background: none;
  cursor: pointer;
  border-bottom: 2px solid transparent;
}

.tabs button.active {
  border-bottom-color: var(--color-primary);
  font-weight: var(--font-weight-medium);
}

.panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.disclosure {
  font-size: var(--font-size-xs);
  background-color: var(--color-hover);
  padding: 0.35rem 0.6rem;
  border-radius: var(--border-radius-sm);
}

.scatter-unavailable {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}

.scatter {
  width: 100%;
  max-width: 300px;
}

.scatter-node {
  fill: var(--color-primary);
}

.cluster-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
  gap: 0.75rem;
}
</style>
