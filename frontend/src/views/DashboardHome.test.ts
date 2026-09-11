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
}))

import { getCoverage } from '@/api/dashboard'
import DashboardHome from './DashboardHome.vue'

const getCoverageMock = vi.mocked(getCoverage)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function makeEnvelope(): DashboardEnvelope<CoverageData> {
  return {
    population: { hash: 'h1', authScope: 'pub', fipCount: 9412, label: 'All public FIPs' },
    tier: 'live',
    computedAt: '2026-09-11T10:00:00Z',
    degraded: false,
    etag: 'W/"coverage-abc"',
    data: { rows: [], totals: { fips: 9412, cells: 197652 }, order: [] },
  }
}

async function mountView() {
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
  await router.push({ path: '/dashboard', query: { pop: 'public' } })
  await router.isReady()
  const wrapper = mount(DashboardHome, { global: { plugins: [pinia, makeI18n(), router] } })
  await flushPromises()
  return { wrapper, router }
}

describe('DashboardHome.vue (spec 13 §6.1)', () => {
  beforeEach(() => {
    getCoverageMock.mockReset()
    getCoverageMock.mockResolvedValue({ status: 'ok', envelope: makeEnvelope() })
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
})
