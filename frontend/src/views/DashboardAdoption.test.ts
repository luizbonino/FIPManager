import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
import type { AdoptionData, DashboardEnvelope } from '@/types/dashboard'

vi.mock('@/api/dashboard', () => ({
  getAdoption: vi.fn(),
  dashboardCsvUrl: (view: string) => `/api/dashboard/${view}.csv?population=public`,
  refreshDashboard: vi.fn(),
}))

import { getAdoption } from '@/api/dashboard'
import DashboardAdoption from './DashboardAdoption.vue'

const getAdoptionMock = vi.mocked(getAdoption)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function makeEnvelope(overrides: Partial<DashboardEnvelope<AdoptionData>> = {}): DashboardEnvelope<AdoptionData> {
  return {
    population: { hash: 'h1', authScope: 'pub', fipCount: 40 },
    tier: 'live',
    computedAt: '2026-09-11T10:00:00Z',
    degraded: false,
    etag: 'W/"adoption-abc"',
    data: {
      rows: [
        { ferKey: 'https://orcid.org/', ferId: 'https://orcid.org/', label: 'ORCID', ferType: 'identifier-service', status: 'current', fips: 30, declarations: 32, share: 0.75 },
      ],
      total: 60214,
      truncated: false,
    },
    ...overrides,
  }
}

async function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/dashboard/adoption', name: 'DashboardAdoption', component: DashboardAdoption }],
  })
  await router.push({ path: '/dashboard/adoption', query: { pop: 'public' } })
  await router.isReady()
  const wrapper = mount(DashboardAdoption, { global: { plugins: [pinia, makeI18n(), router] } })
  await flushPromises()
  return { wrapper, router }
}

describe('DashboardAdoption.vue (spec 13 §3.2/§6.2)', () => {
  beforeEach(() => {
    getAdoptionMock.mockReset()
    getAdoptionMock.mockResolvedValue({ status: 'ok', envelope: makeEnvelope() })
  })

  it('fetches adoption once on mount, server-paginated at 50 rows/page by default', async () => {
    await mountView()
    expect(getAdoptionMock).toHaveBeenCalledTimes(1)
    expect(getAdoptionMock.mock.calls[0][0]).toMatchObject({ population: 'public', limit: 50, offset: 0 })
  })

  it('a status filter change refetches with the new status', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('select')[1].setValue('planned')
    await flushPromises()
    expect(getAdoptionMock).toHaveBeenCalledTimes(2)
    expect(getAdoptionMock.mock.calls[1][0]).toMatchObject({ status: 'planned' })
  })

  it('renders the truncated disclosure when the server flags it', async () => {
    getAdoptionMock.mockResolvedValue({ status: 'ok', envelope: makeEnvelope({ data: { rows: [], total: 60214, truncated: true } }) })
    const { wrapper } = await mountView()
    expect(wrapper.text()).toContain('60,214')
  })

  it('exposes CSV as a plain <a href>', async () => {
    const { wrapper } = await mountView()
    const link = wrapper.find('a.btn-secondary')
    expect(link.attributes('href')).toContain('/api/dashboard/adoption.csv')
  })

  it('caps rendered rows at 50 (server pagination bound), even when total is 60000+ (spec 13 AC-2)', async () => {
    const rows = Array.from({ length: 50 }, (_, i) => ({
      ferKey: `key-${i}`,
      ferId: `key-${i}`,
      label: `FER ${i}`,
      ferType: null,
      status: 'current',
      fips: 1,
      declarations: 1,
      share: 0.01,
    }))
    getAdoptionMock.mockResolvedValue({ status: 'ok', envelope: makeEnvelope({ data: { rows, total: 60214, truncated: false } }) })
    const { wrapper } = await mountView()
    expect(wrapper.findAll('.adoption-table tbody tr')).toHaveLength(50)
  })
})
