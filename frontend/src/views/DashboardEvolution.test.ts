import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
import type { DashboardEnvelope, EvolutionData } from '@/types/dashboard'

vi.mock('@/api/dashboard', () => ({
  getEvolution: vi.fn(),
  dashboardCsvUrl: (view: string) => `/api/dashboard/${view}.csv?population=public`,
  refreshDashboard: vi.fn(),
}))

import { getEvolution } from '@/api/dashboard'
import DashboardEvolution from './DashboardEvolution.vue'

const getEvolutionMock = vi.mocked(getEvolution)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function makeEnvelope(overrides: Partial<EvolutionData> = {}): DashboardEnvelope<EvolutionData> {
  return {
    population: { hash: 'h1', authScope: 'pub', fipCount: 40 },
    tier: 'live',
    computedAt: '2026-09-11T10:00:00Z',
    degraded: false,
    etag: 'W/"evolution-abc"',
    data: {
      planned: [{ subPrinciple: 'F1', questionId: 'F1-metadata', status: 'planned', ferKey: 'text:x', ferLabel: 'X', successorFerKey: null, successorLabel: null, fips: 4 }],
      migrations: [{ questionnaireId: 'gofair-fip-mini', questionnaireVersion: '2.0.0', migratedFromId: 'gofair-fip-mini', migratedFromVersion: '1.0.0', fips: 6 }],
      truncated: false,
      ...overrides,
    },
  }
}

async function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/dashboard/evolution', name: 'DashboardEvolution', component: DashboardEvolution }],
  })
  await router.push({ path: '/dashboard/evolution', query: { pop: 'public' } })
  await router.isReady()
  const wrapper = mount(DashboardEvolution, { global: { plugins: [pinia, makeI18n(), router] } })
  await flushPromises()
  return { wrapper, router }
}

describe('DashboardEvolution.vue (spec 13 §3.5/§6.2)', () => {
  beforeEach(() => {
    getEvolutionMock.mockReset()
    getEvolutionMock.mockResolvedValue({ status: 'ok', envelope: makeEnvelope() })
  })

  it('fetches evolution once on mount', async () => {
    await mountView()
    expect(getEvolutionMock).toHaveBeenCalledTimes(1)
    expect(getEvolutionMock.mock.calls[0][0]).toMatchObject({ population: 'public' })
  })

  it('renders both the planned and migration tables', async () => {
    const { wrapper } = await mountView()
    expect(wrapper.text()).toContain('F1-metadata')
    expect(wrapper.text()).toContain('gofair-fip-mini@1.0.0')
  })

  it('a groupBy change refetches (evolution has no client rollup)', async () => {
    const { wrapper } = await mountView()
    await wrapper.find('select').setValue('question')
    await flushPromises()
    expect(getEvolutionMock).toHaveBeenCalledTimes(2)
    expect(getEvolutionMock.mock.calls[1][0]).toMatchObject({ groupBy: 'question' })
  })

  it('shows a truncated disclosure for the migration history when flagged', async () => {
    getEvolutionMock.mockResolvedValue({ status: 'ok', envelope: makeEnvelope({ truncated: true }) })
    const { wrapper } = await mountView()
    expect(wrapper.text()).toContain(en.dashboard.evolution.truncated)
  })
})
