import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
import type { CoverageData, DashboardEnvelope } from '@/types/dashboard'

vi.mock('@/api/dashboard', () => ({
  getCoverage: vi.fn(),
  refreshDashboard: vi.fn(),
  listPopulations: vi.fn(),
}))

import { getCoverage, listPopulations } from '@/api/dashboard'
import DashboardHome from './DashboardHome.vue'

const getCoverageMock = vi.mocked(getCoverage)
const listPopulationsMock = vi.mocked(listPopulations)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function makeEnvelope(overrides: Partial<DashboardEnvelope<CoverageData>> = {}): DashboardEnvelope<CoverageData> {
  return {
    population: { hash: 'h1', authScope: 'pub', fipCount: 9412, label: 'All public FIPs' },
    tier: 'live',
    computedAt: '2026-09-11T10:00:00Z',
    degraded: false,
    etag: 'W/"coverage-abc"',
    data: { rows: [], totals: { fips: 9412, cells: 197652 }, order: [] },
    ...overrides,
  }
}

async function mountView(query: Record<string, string> = { pop: 'public' }) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/dashboard', name: 'DashboardHome', component: DashboardHome },
      { path: '/dashboard/coverage', name: 'DashboardCoverage', component: { template: '<div/>' } },
      { path: '/dashboard/adoption', name: 'DashboardAdoption', component: { template: '<div/>' } },
      { path: '/dashboard/similarity', name: 'DashboardSimilarity', component: { template: '<div/>' } },
      { path: '/dashboard/gaps', name: 'DashboardGaps', component: { template: '<div/>' } },
      { path: '/dashboard/evolution', name: 'DashboardEvolution', component: { template: '<div/>' } },
    ],
  })
  await router.push({ path: '/dashboard', query })
  await router.isReady()
  const wrapper = mount(DashboardHome, { global: { plugins: [pinia, makeI18n(), router] }, attachTo: document.body })
  await flushPromises()
  return { wrapper, router }
}

describe('DashboardHome.vue (spec 13 §6.1)', () => {
  beforeEach(() => {
    getCoverageMock.mockReset()
    getCoverageMock.mockResolvedValue({ status: 'ok', envelope: makeEnvelope() })
    listPopulationsMock.mockReset()
    listPopulationsMock.mockResolvedValue({ items: [], networkIngestedAt: null })
  })

  it('shows the population picker and the headline FIP count', async () => {
    const { wrapper } = await mountView()
    expect(wrapper.text()).toContain(en.dashboard.population.title)
    expect(wrapper.text()).toContain('9,412')
  })

  it('links to all five views, carrying the population forward', async () => {
    const { wrapper } = await mountView()
    const links = wrapper.findAll('.view-card')
    expect(links).toHaveLength(5)
    for (const link of links) {
      expect(link.attributes('href')).toContain('pop=public')
    }
  })

  // ---------------------------------------------------------------------
  // Task 1 (spec 13 §9 A8): `/dashboard` with no `pop` at all must default
  // to the network population when an ingest has run, else public — and
  // must actually issue a request, unlike the empty-spec bug this fixes.
  // ---------------------------------------------------------------------

  it('defaults to the public population and requests it when no pop is given and no network ingest exists', async () => {
    listPopulationsMock.mockResolvedValue({ items: [], networkIngestedAt: null })
    const { wrapper, router } = await mountView({})
    expect(listPopulationsMock).toHaveBeenCalledTimes(1)
    expect(getCoverageMock).toHaveBeenCalledTimes(1)
    expect(getCoverageMock.mock.calls[0][0]).toMatchObject({ population: 'public' })
    expect(router.currentRoute.value.query.pop).toBe('public')
    const links = wrapper.findAll('.view-card')
    for (const link of links) {
      expect(link.attributes('href')).toContain('pop=public')
    }
  })

  it('defaults to the network population and requests it when a network ingest exists and no pop is given', async () => {
    listPopulationsMock.mockResolvedValue({ items: [], networkIngestedAt: '2026-09-10T08:00:00Z' })
    const { router } = await mountView({})
    expect(getCoverageMock).toHaveBeenCalledTimes(1)
    expect(getCoverageMock.mock.calls[0][0]).toMatchObject({ population: 'network' })
    expect(router.currentRoute.value.query.pop).toBe('network')
  })

  it('does not override an explicit pop with the default', async () => {
    listPopulationsMock.mockResolvedValue({ items: [], networkIngestedAt: '2026-09-10T08:00:00Z' })
    await mountView({ pop: 'public' })
    expect(listPopulationsMock).not.toHaveBeenCalled()
    expect(getCoverageMock.mock.calls[0][0]).toMatchObject({ population: 'public' })
  })

  // ---------------------------------------------------------------------
  // Task 2: the empty state is distinct from the k-anonymity withheld
  // state, and names the visibility-exclusion rule only for a public/
  // network population.
  // ---------------------------------------------------------------------

  it('renders an honest empty state, not a zero headline, for a zero-FIP population', async () => {
    getCoverageMock.mockResolvedValue({
      status: 'ok',
      envelope: makeEnvelope({ population: { hash: 'h2', authScope: 'pub', fipCount: 0 } }),
    })
    const { wrapper } = await mountView({ pop: 'public' })
    expect(wrapper.text()).toContain(en.dashboard.home.emptyTitle)
    expect(wrapper.text()).toContain(en.dashboard.home.emptyVisibilityHint)
    expect(wrapper.text()).not.toContain('0 FIPs')
    expect(wrapper.find('.headline-row').exists()).toBe(false)
  })

  it('does not show the visibility hint for a non-public/network empty population', async () => {
    getCoverageMock.mockResolvedValue({
      status: 'ok',
      envelope: makeEnvelope({ population: { hash: 'h3', authScope: 'pub', fipCount: 0 } }),
    })
    const { wrapper } = await mountView({ pop: 'session:s1' })
    expect(wrapper.text()).toContain(en.dashboard.home.emptyTitle)
    expect(wrapper.text()).not.toContain(en.dashboard.home.emptyVisibilityHint)
  })

  it('shows the network ingest hint for an empty network population', async () => {
    getCoverageMock.mockResolvedValue({
      status: 'ok',
      envelope: makeEnvelope({ population: { hash: 'h5', authScope: 'pub', fipCount: 0 } }),
    })
    const { wrapper } = await mountView({ pop: 'network' })
    expect(wrapper.text()).toContain(en.dashboard.home.emptyNetworkHint)
  })

  it('does not show the network ingest hint for a session-only empty population', async () => {
    getCoverageMock.mockResolvedValue({
      status: 'ok',
      envelope: makeEnvelope({ population: { hash: 'h6', authScope: 'pub', fipCount: 0 } }),
    })
    const { wrapper } = await mountView({ pop: 'session:s1' })
    expect(wrapper.text()).not.toContain(en.dashboard.home.emptyNetworkHint)
  })

  it('offers one-click routes to session/questionnaire terms from the empty state', async () => {
    getCoverageMock.mockResolvedValue({
      status: 'ok',
      envelope: makeEnvelope({ population: { hash: 'h2', authScope: 'pub', fipCount: 0 } }),
    })
    const { wrapper } = await mountView({ pop: 'public' })
    const buttons = wrapper.findAll('.empty-actions button')
    expect(buttons.map((b) => b.text())).toEqual([en.dashboard.home.emptyTrySession, en.dashboard.home.emptyTryQuestionnaire])
    await buttons[0].trigger('click')
    await flushPromises()
    const idInput = wrapper.find('.term-add-row input[type="text"]')
    expect((idInput.element as HTMLInputElement)).toBe(document.activeElement)
  })

  it('keeps the k-anonymity withheld state distinct from the empty state', async () => {
    getCoverageMock.mockResolvedValue({
      status: 'ok',
      envelope: makeEnvelope({ population: { hash: 'h4', authScope: 'u', fipCount: null } }),
    })
    const { wrapper } = await mountView({ pop: 'public' })
    expect(wrapper.text()).toContain(en.dashboard.home.fipCountWithheld)
    expect(wrapper.text()).not.toContain(en.dashboard.home.emptyTitle)
  })

  it('still renders the normal headline for a non-empty population', async () => {
    getCoverageMock.mockResolvedValue({ status: 'ok', envelope: makeEnvelope() })
    const { wrapper } = await mountView({ pop: 'public' })
    expect(wrapper.text()).toContain('9,412')
    expect(wrapper.text()).not.toContain(en.dashboard.home.emptyTitle)
  })

  // ---------------------------------------------------------------------
  // networkIngestedAt stamp (spec 13 §5.4/§9 Q4: "the ingest timestamp
  // always visible" next to any network-bearing view).
  // ---------------------------------------------------------------------

  it('shows the network ingest stamp for a network population with a timestamp', async () => {
    listPopulationsMock.mockResolvedValue({ items: [], networkIngestedAt: '2026-09-10T08:00:00Z' })
    const { wrapper } = await mountView({ pop: 'network' })
    expect(wrapper.text()).toContain('Network copy from')
  })

  it('does not show the network ingest stamp for a session-only population', async () => {
    const { wrapper } = await mountView({ pop: 'session:s1' })
    expect(listPopulationsMock).not.toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('Network copy from')
  })

  it('does not show the network ingest stamp when networkIngestedAt is null', async () => {
    listPopulationsMock.mockResolvedValue({ items: [], networkIngestedAt: null })
    const { wrapper } = await mountView({ pop: 'network' })
    expect(wrapper.text()).not.toContain('Network copy from')
  })
})
