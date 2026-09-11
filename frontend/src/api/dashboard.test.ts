import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getCoverage, populationQueryParam } from './dashboard'
import type { CoverageData, DashboardEnvelope } from '@/types/dashboard'

function makeEnvelope(): DashboardEnvelope<CoverageData> {
  return {
    population: { hash: 'h1', authScope: 'pub', fipCount: 1 },
    tier: 'live',
    computedAt: '2026-09-11T10:00:00Z',
    degraded: false,
    etag: 'W/"x"',
    data: { rows: [], totals: { fips: 1, cells: 0 }, order: [] },
  }
}

describe('populationQueryParam (spec 13 §6.1 population/pop split)', () => {
  it('routes a shorthand through `pop`', () => {
    expect(populationQueryParam('public')).toEqual({ pop: 'public' })
    expect(populationQueryParam('network')).toEqual({ pop: 'network' })
    expect(populationQueryParam('session:s_abc')).toEqual({ pop: 'session:s_abc' })
  })

  it('routes an inline base64 spec through `pop`', () => {
    // Not one of the three shorthands and not valid base64url JSON -> still
    // opaque-looking, but `decodePopulationParam` only returns null for a
    // value it cannot parse as inline JSON either; use a real inline value.
    const inline = 'eyJ2ZXJzaW9uIjoxLCJpbmNsdWRlIjpbXSwiZXhjbHVkZSI6W10sInVwZGF0ZWRBZnRlciI6bnVsbCwidXBkYXRlZEJlZm9yZSI6bnVsbH0'
    expect(populationQueryParam(inline)).toEqual({ pop: inline })
  })

  it('routes an opaque saved-population hash through `population`', () => {
    expect(populationQueryParam('ph_9f8e7d6c')).toEqual({ population: 'ph_9f8e7d6c' })
  })

  it('returns an empty object for an empty pop value', () => {
    expect(populationQueryParam('')).toEqual({})
  })
})

describe('getCoverage query params (spec 13 §6.1)', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: async () => makeEnvelope(),
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends `pop=` for a shorthand population', async () => {
    await getCoverage({ population: 'session:s_abc' })
    const url = new URL(fetchMock.mock.calls[0][0] as string, 'http://localhost')
    expect(url.searchParams.get('pop')).toBe('session:s_abc')
    expect(url.searchParams.has('population')).toBe(false)
  })

  it('sends `population=` for a saved-population hash', async () => {
    await getCoverage({ population: 'ph_9f8e7d6c' })
    const url = new URL(fetchMock.mock.calls[0][0] as string, 'http://localhost')
    expect(url.searchParams.get('population')).toBe('ph_9f8e7d6c')
    expect(url.searchParams.has('pop')).toBe(false)
  })
})
