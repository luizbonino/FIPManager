import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
import type { DashboardEnvelope, GapsData } from '@/types/dashboard'

vi.mock('@/api/dashboard', () => ({
  getGaps: vi.fn(),
  dashboardCsvUrl: (view: string) => `/api/dashboard/${view}.csv?population=public`,
  refreshDashboard: vi.fn(),
}))

import { getGaps } from '@/api/dashboard'
import DashboardGaps from './DashboardGaps.vue'

const getGapsMock = vi.mocked(getGaps)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function makeRow(id: string, overrides: Partial<GapsData['rows'][number]> = {}) {
  return {
    questionId: id,
    questionIndex: 0,
    subPrinciple: 'F1',
    principleGroup: 'F',
    ferType: null,
    fips: 40,
    unanswered: 5,
    noneOnly: 2,
    notApplicable: 1,
    plannedOnly: 3,
    coherenceFlags: 0,
    typeMismatches: 0,
    ...overrides,
  }
}

function makeEnvelope(rows = [makeRow('F1-metadata')]): DashboardEnvelope<GapsData> {
  return {
    population: { hash: 'h1', authScope: 'pub', fipCount: 40 },
    tier: 'live',
    computedAt: '2026-09-11T10:00:00Z',
    degraded: false,
    etag: 'W/"gaps-abc"',
    data: { rows, total: rows.length, truncated: false },
  }
}

async function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/dashboard/gaps', name: 'DashboardGaps', component: DashboardGaps }],
  })
  await router.push({ path: '/dashboard/gaps', query: { pop: 'public' } })
  await router.isReady()
  const wrapper = mount(DashboardGaps, { global: { plugins: [pinia, makeI18n(), router] } })
  await flushPromises()
  return { wrapper, router }
}

describe('DashboardGaps.vue (spec 13 §3.4/§6.2)', () => {
  beforeEach(() => {
    getGapsMock.mockReset()
    getGapsMock.mockResolvedValue({ status: 'ok', envelope: makeEnvelope() })
  })

  it('fetches gaps once on mount for the population in the URL', async () => {
    await mountView()
    expect(getGapsMock).toHaveBeenCalledTimes(1)
    expect(getGapsMock.mock.calls[0][0]).toMatchObject({ population: 'public' })
  })

  it('renders one row per question, capped at the questionnaire size regardless of population (spec 13 AC-2: ≤21)', async () => {
    const rows = Array.from({ length: 21 }, (_, i) => makeRow(`Q${i}`))
    getGapsMock.mockResolvedValue({ status: 'ok', envelope: makeEnvelope(rows) })
    const { wrapper } = await mountView()
    expect(wrapper.findAll('.gaps-table tbody tr')).toHaveLength(21)
  })

  it('hides the coherence/type-mismatch columns when every value is 0 (spec 12 §A2/§A3 not landed)', async () => {
    const { wrapper } = await mountView()
    expect(wrapper.text()).not.toContain(en.dashboard.gaps.colCoherence)
    expect(wrapper.text()).not.toContain(en.dashboard.gaps.colTypeMismatch)
  })

  it('shows the coherence column once any row has a non-zero flag', async () => {
    getGapsMock.mockResolvedValue({ status: 'ok', envelope: makeEnvelope([makeRow('F1-metadata', { coherenceFlags: 2 })]) })
    const { wrapper } = await mountView()
    expect(wrapper.text()).toContain(en.dashboard.gaps.colCoherence)
  })

  it('a minShare change refetches', async () => {
    const { wrapper } = await mountView()
    await wrapper.find('input[type="number"]').setValue(0.5)
    await flushPromises()
    expect(getGapsMock).toHaveBeenCalledTimes(2)
    expect(getGapsMock.mock.calls[1][0]).toMatchObject({ minShare: 0.5 })
  })
})
