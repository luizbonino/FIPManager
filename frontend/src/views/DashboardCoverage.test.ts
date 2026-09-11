import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
import type { CoverageData, DashboardEnvelope } from '@/types/dashboard'

vi.mock('@/api/dashboard', () => ({
  getCoverage: vi.fn(),
  dashboardCsvUrl: (view: string, pop: string, params: Record<string, unknown>) => {
    const qs = new URLSearchParams({ pop, ...(params as Record<string, string>) }).toString()
    return `/api/dashboard/${view}.csv?${qs}`
  },
  refreshDashboard: vi.fn(),
}))

import { getCoverage, refreshDashboard } from '@/api/dashboard'
import DashboardCoverage from './DashboardCoverage.vue'

const getCoverageMock = vi.mocked(getCoverage)
const refreshDashboardMock = vi.mocked(refreshDashboard)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function makeQuestionRow(id: string, principle: string, principleGroup: string) {
  return {
    key: id,
    level: 'question' as const,
    subPrinciple: principle,
    principle: principle.split('.')[0],
    principleGroup,
    questions: [id],
    ferTypes: [],
    counts: { current: 5, planned: 1, none: 1, notApplicable: 1, unanswered: 2, absent: 0 },
    shares: { current: 0.5, planned: 0.1, none: 0.1, notApplicable: 0.1, unanswered: 0.2, absent: 0 },
  }
}

function makeEnvelope(rows = [makeQuestionRow('F1-metadata', 'F1', 'F')], overrides: Partial<DashboardEnvelope<CoverageData>> = {}): DashboardEnvelope<CoverageData> {
  return {
    population: { hash: 'h1', authScope: 'pub', fipCount: 40, label: 'Public' },
    tier: 'live',
    computedAt: '2026-09-11T10:00:00Z',
    degraded: false,
    etag: 'W/"coverage-abc"',
    data: { rows, totals: { fips: 40, cells: rows.length * 40 }, order: rows.map((r) => r.subPrinciple) },
    ...overrides,
  }
}

async function mountView(initialQuery: Record<string, string> = { pop: 'public' }) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/dashboard/coverage', name: 'DashboardCoverage', component: DashboardCoverage },
      { path: '/dashboard', name: 'DashboardHome', component: { template: '<div/>' } },
    ],
  })
  await router.push({ path: '/dashboard/coverage', query: initialQuery })
  await router.isReady()
  const wrapper = mount(DashboardCoverage, { global: { plugins: [pinia, makeI18n(), router] } })
  await flushPromises()
  return { wrapper, router }
}

describe('DashboardCoverage.vue (spec 13 §3.1/§6/AC-2..AC-9)', () => {
  beforeEach(() => {
    getCoverageMock.mockReset()
    refreshDashboardMock.mockReset()
    getCoverageMock.mockResolvedValue({ status: 'ok', envelope: makeEnvelope() })
  })

  it('fetches coverage once on mount for the population in the URL', async () => {
    await mountView()
    expect(getCoverageMock).toHaveBeenCalledTimes(1)
    expect(getCoverageMock.mock.calls[0][0]).toMatchObject({ population: 'public' })
  })

  it('a groupBy change does not refetch (spec 13 AC-3)', async () => {
    const { wrapper } = await mountView()
    expect(getCoverageMock).toHaveBeenCalledTimes(1)
    const select = wrapper.findAll('select')[0]
    await select.setValue('principle')
    await flushPromises()
    expect(getCoverageMock).toHaveBeenCalledTimes(1)
  })

  it('a scope change refetches', async () => {
    const { wrapper } = await mountView()
    expect(getCoverageMock).toHaveBeenCalledTimes(1)
    const scopeSelect = wrapper.findAll('select')[1]
    await scopeSelect.setValue('metadata')
    await flushPromises()
    expect(getCoverageMock).toHaveBeenCalledTimes(2)
    expect(getCoverageMock.mock.calls[1][0]).toMatchObject({ scope: 'metadata' })
  })

  it('round-trips groupBy/scope state through the URL query', async () => {
    const { wrapper, router } = await mountView()
    await wrapper.findAll('select')[0].setValue('group')
    await wrapper.findAll('select')[1].setValue('data')
    await flushPromises()
    expect(router.currentRoute.value.query.groupBy).toBe('group')
    expect(router.currentRoute.value.query.scope).toBe('data')

    // Reload from that exact query and confirm identical rendering.
    const { wrapper: reloaded } = await mountView({ pop: 'public', groupBy: 'group', scope: 'data' })
    expect(reloaded.findAll('select')[0].element.value).toBe('group')
    expect(reloaded.findAll('select')[1].element.value).toBe('data')
  })

  it('renders a snapshot banner with age and a Refresh that POSTs exactly once per click', async () => {
    getCoverageMock.mockResolvedValue({ status: 'ok', envelope: makeEnvelope(undefined, { tier: 'snapshot' }) })
    refreshDashboardMock.mockResolvedValue({ status: 'done' })
    const { wrapper } = await mountView()
    expect(wrapper.find('.snapshot-banner.snapshot').exists()).toBe(true)
    await wrapper.find('.snapshot-banner button').trigger('click')
    await flushPromises()
    expect(refreshDashboardMock).toHaveBeenCalledTimes(1)
  })

  it('renders a degraded banner naming the reason', async () => {
    getCoverageMock.mockResolvedValue({ status: 'ok', envelope: makeEnvelope(undefined, { degraded: true, degradedReason: 'projection_stale', staleFips: 3 }) })
    const { wrapper } = await mountView()
    expect(wrapper.find('.degraded-banner').exists()).toBe(true)
    expect(wrapper.text()).toContain(en.dashboard.errors.projection_stale)
  })

  it('polls a 202 snapshot_pending response and renders the stale payload dimmed', async () => {
    vi.useFakeTimers()
    getCoverageMock.mockResolvedValueOnce({ status: 'pending', retryAfter: 1, stalePayload: makeEnvelope().data, degraded: true })
    getCoverageMock.mockResolvedValueOnce({ status: 'ok', envelope: makeEnvelope() })
    const { wrapper } = await mountView()
    expect(wrapper.find('.snapshot-banner.pending').exists()).toBe(true)
    expect(wrapper.find('.stale-payload.dimmed').exists()).toBe(true)
    await vi.advanceTimersByTimeAsync(1100)
    await flushPromises()
    expect(getCoverageMock).toHaveBeenCalledTimes(2)
    vi.useRealTimers()
  })

  it('renders the dashboard_disabled error with no retry action', async () => {
    const { ApiResponseError } = await import('@/api/client')
    getCoverageMock.mockRejectedValue(new ApiResponseError(503, { detail: 'dashboard_disabled' }))
    const { wrapper } = await mountView()
    expect(wrapper.find('.degraded-banner.error').exists()).toBe(true)
    expect(wrapper.text()).toContain(en.dashboard.errors.dashboard_disabled)
    // No retry button anywhere in the error banner.
    expect(wrapper.find('.degraded-banner.error button').exists()).toBe(false)
  })

  it('renders projection_stale as an error with an admin-only CLI hint hidden from a non-admin', async () => {
    const { ApiResponseError } = await import('@/api/client')
    getCoverageMock.mockRejectedValue(
      new ApiResponseError(409, {
        detail: 'projection_stale',
        staleFips: 12,
        totalFips: 500,
        hint: 'python -m fipm backfill-declarations --only-stale',
      } as never)
    )
    const { wrapper } = await mountView()
    expect(wrapper.text()).toContain(en.dashboard.errors.projection_stale)
    expect(wrapper.text()).not.toContain('backfill-declarations')
  })

  it('exposes CSV as a plain <a href> (no fetch-then-blob)', async () => {
    const { wrapper } = await mountView()
    const link = wrapper.find('a.btn-secondary')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toContain('/api/dashboard/coverage.csv')
  })

  it('never renders more than questions x 6 cells even at fipCount 10000 (spec 13 AC-2)', async () => {
    const rows = Array.from({ length: 21 }, (_, i) => makeQuestionRow(`Q${i}`, `Q${i}`, 'F'))
    getCoverageMock.mockResolvedValue({
      status: 'ok',
      envelope: makeEnvelope(rows, { population: { hash: 'h', authScope: 'pub', fipCount: 10000 } }),
    })
    const { wrapper } = await mountView()
    expect(wrapper.findAll('.hm-value').length).toBeLessThanOrEqual(126)
  })
})
