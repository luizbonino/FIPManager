import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
import type { ClustersData, DashboardEnvelope, MapData, NeighboursData } from '@/types/dashboard'

vi.mock('@/api/dashboard', () => ({
  getSimilarityNeighbours: vi.fn(),
  getSimilarityMap: vi.fn(),
  getSimilarityClusters: vi.fn(),
  refreshDashboard: vi.fn(),
  getFipLookup: vi.fn(),
}))

import { getFipLookup, getSimilarityClusters, getSimilarityMap, getSimilarityNeighbours } from '@/api/dashboard'
import DashboardSimilarity from './DashboardSimilarity.vue'

const neighboursMock = vi.mocked(getSimilarityNeighbours)
const mapMock = vi.mocked(getSimilarityMap)
const fipLookupMock = vi.mocked(getFipLookup)
const clustersMock = vi.mocked(getSimilarityClusters)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function mapEnvelope(overrides: Partial<MapData> = {}): DashboardEnvelope<MapData> {
  return {
    population: { hash: 'h1', authScope: 'pub', fipCount: 40 },
    tier: 'live',
    computedAt: '2026-09-11T10:00:00Z',
    degraded: false,
    etag: 'W/"map-abc"',
    data: {
      histogram: Array.from({ length: 10 }, (_, i) => ({ bucket: i, from: i / 10, to: (i + 1) / 10, count: 5 })),
      principleBuckets: {},
      convergence: [],
      topClusters: [],
      hotBuckets: [],
      scatterAvailable: true,
      nodes: [{ id: 'fip-1', label: 'Fip 1', clusterId: 'c1' }],
      edges: [],
      edgesTruncated: false,
      ...overrides,
    },
  }
}

function clustersEnvelope(clusters: ClustersData['clusters'] = []): DashboardEnvelope<ClustersData> {
  return {
    population: { hash: 'h1', authScope: 'pub', fipCount: 40 },
    tier: 'live',
    computedAt: '2026-09-11T10:00:00Z',
    degraded: false,
    etag: 'W/"clusters-abc"',
    data: { clusters, truncated: false },
  }
}

function neighboursEnvelope(overrides: Partial<NeighboursData> = {}): DashboardEnvelope<NeighboursData> {
  return {
    population: { hash: 'h1', authScope: 'pub', fipCount: 40 },
    tier: 'live',
    computedAt: '2026-09-11T10:00:00Z',
    degraded: false,
    etag: 'W/"neighbours-abc"',
    data: {
      fip: { id: 'fip-1', label: 'Fip 1' },
      neighbours: [],
      weighting: 'principle',
      statuses: 'current',
      candidateBudgetExhausted: false,
      postingTruncated: false,
      skippedPopularKeys: [],
      keysUsed: 0,
      candidatesScored: 0,
      ...overrides,
    },
  }
}

async function mountView(query: Record<string, string> = { pop: 'public', fip: 'fip-1' }) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/dashboard/similarity', name: 'DashboardSimilarity', component: DashboardSimilarity },
      { path: '/fips/:id', name: 'FipRead', component: { template: '<div/>' } },
    ],
  })
  await router.push({ path: '/dashboard/similarity', query })
  await router.isReady()
  const wrapper = mount(DashboardSimilarity, { global: { plugins: [pinia, makeI18n(), router] } })
  await flushPromises()
  return { wrapper, router }
}

describe('DashboardSimilarity.vue (spec 13 §3.3/§4/§6.2)', () => {
  beforeEach(() => {
    neighboursMock.mockReset()
    mapMock.mockReset()
    clustersMock.mockReset()
    fipLookupMock.mockReset()
    neighboursMock.mockResolvedValue({ status: 'ok', envelope: neighboursEnvelope() })
    mapMock.mockResolvedValue({ status: 'ok', envelope: mapEnvelope() })
    clustersMock.mockResolvedValue({ status: 'ok', envelope: clustersEnvelope() })
    fipLookupMock.mockResolvedValue({ items: [] })
  })

  it('fetches neighbours, map and clusters once each on mount', async () => {
    await mountView()
    expect(neighboursMock).toHaveBeenCalledTimes(1)
    expect(mapMock).toHaveBeenCalledTimes(1)
    expect(clustersMock).toHaveBeenCalledTimes(1)
  })

  it('shows the scatter when scatterAvailable is true', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()
    expect(wrapper.find('.scatter').exists()).toBe(true)
  })

  it('shows a one-line explanation instead of a scatter when scatterAvailable is false (spec 13 AC-2)', async () => {
    mapMock.mockResolvedValue({ status: 'ok', envelope: mapEnvelope({ scatterAvailable: false, nodes: undefined }) })
    const { wrapper } = await mountView()
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()
    expect(wrapper.find('.scatter').exists()).toBe(false)
    expect(wrapper.find('.scatter-unavailable').exists()).toBe(true)
    expect(wrapper.text()).toContain(en.dashboard.similarity.scatterUnavailable)
  })

  it('caps cluster cards at 200 even when many are returned (spec 13 AC-2)', async () => {
    const clusters = Array.from({ length: 200 }, (_, i) => ({
      id: `c${i}`,
      size: 3,
      representative: { fipId: `fip-${i}`, label: `Fip ${i}` },
      meanSimilarity: 0.7,
      principles: ['F1'],
      members: [],
    }))
    clustersMock.mockResolvedValue({ status: 'ok', envelope: clustersEnvelope(clusters) })
    const { wrapper } = await mountView()
    await wrapper.findAll('[role="tab"]')[2].trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.cluster-card')).toHaveLength(200)
  })

  it('surfaces the neighbours disclosure fields (candidateBudgetExhausted, postingTruncated, skippedPopularKeys)', async () => {
    neighboursMock.mockResolvedValue({
      status: 'ok',
      envelope: neighboursEnvelope({ candidateBudgetExhausted: true, postingTruncated: true, skippedPopularKeys: ['https://doi.org/'] }),
    })
    const { wrapper } = await mountView()
    expect(wrapper.text()).toContain(en.dashboard.similarity.candidateBudgetExhausted)
    expect(wrapper.text()).toContain(en.dashboard.similarity.postingTruncated)
    expect(wrapper.text()).toContain('https://doi.org/')
  })

  it('picks the subject FIP via the population-scoped typeahead, not a plain text id field (spec 13 §3.7/§6.2)', async () => {
    vi.useFakeTimers()
    try {
      fipLookupMock.mockResolvedValue({ items: [{ fipId: 'fip-42', label: 'Fip Forty-Two', areaKey: null }] })
      const { wrapper } = await mountView({ pop: 'session:s_abc', fip: 'fip-1' })
      const combobox = wrapper.find('input[role="combobox"]')
      expect(combobox.exists()).toBe(true)
      await combobox.trigger('focus')
      await vi.advanceTimersByTimeAsync(300)
      expect(fipLookupMock).toHaveBeenCalledWith(expect.objectContaining({ population: 'session:s_abc' }))
      await wrapper.find('[role="option"]').trigger('mousedown')
      await flushPromises()
      expect(neighboursMock).toHaveBeenLastCalledWith(expect.objectContaining({ fip: 'fip-42' }), expect.anything())
    } finally {
      vi.useRealTimers()
    }
  })

  it('a weighting change refetches neighbours and map', async () => {
    const { wrapper } = await mountView()
    await wrapper.find('select').setValue('question')
    await flushPromises()
    expect(neighboursMock).toHaveBeenCalledTimes(2)
    expect(mapMock).toHaveBeenCalledTimes(2)
  })
})
