import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
import { ApiResponseError } from '@/api/client'
import type { NetworkCommunityListResponse } from '@/types/network'

// spec 11 §3.5: `/network` — search is server-side (debounced 300 ms,
// passing `q`; empty field lists without `q`), paged 50 at a time via
// `limit`/`offset` with a "Load more" button; three distinct empty states.
vi.mock('@/api/network', () => ({
  listCommunities: vi.fn(),
}))

import { listCommunities } from '@/api/network'
import NetworkFipList from './NetworkFipList.vue'

const listCommunitiesMock = vi.mocked(listCommunities)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function makeResponse(overrides: Partial<NetworkCommunityListResponse> = {}): NetworkCommunityListResponse {
  return {
    items: [
      { iri: 'http://purl.org/np/RA1#PARCToxicology', label: 'PARCToxicology', fipCount: 3 },
      { iri: 'http://purl.org/np/RA2#Metabolomics', label: 'Metabolomics Community', fipCount: 1 },
    ],
    total: 2,
    cachedAt: '2026-09-10T12:00:00Z',
    source: 'https://query.knowledgepixels.com',
    ...overrides,
  }
}

function makeRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/network', name: 'NetworkFipList', component: NetworkFipList },
      { path: '/network/:communityIri', name: 'NetworkFipDetail', component: { template: '<div/>' } },
    ],
  })
}

async function mountList() {
  const router = makeRouter()
  await router.push('/network')
  await router.isReady()
  const wrapper = mount(NetworkFipList, { global: { plugins: [makeI18n(), router] } })
  await flushPromises()
  return wrapper
}

describe('NetworkFipList.vue', () => {
  beforeEach(() => {
    listCommunitiesMock.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders the fetched communities: label, fipCount, a link, and "shown of total"', async () => {
    listCommunitiesMock.mockResolvedValue(makeResponse())

    const wrapper = await mountList()

    expect(listCommunitiesMock).toHaveBeenCalledWith({ q: undefined, limit: 50 })
    expect(wrapper.text()).toContain('PARCToxicology')
    expect(wrapper.text()).toContain('Metabolomics Community')
    const link = wrapper.find(`a[href="/network/${encodeURIComponent('http://purl.org/np/RA1#PARCToxicology')}"]`)
    expect(link.exists()).toBe(true)
    expect(wrapper.text()).toContain('2 of 2 communities')
  })

  it('shows the disabled state (no retry) on network_disabled', async () => {
    listCommunitiesMock.mockRejectedValue(new ApiResponseError(503, { detail: 'network_disabled' }))

    const wrapper = await mountList()

    expect(wrapper.text()).toContain(en.network.disabledMessage)
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('shows the unavailable state with a Retry button that re-fetches on click', async () => {
    listCommunitiesMock.mockRejectedValue(new ApiResponseError(502, { detail: 'network_unavailable' }))

    const wrapper = await mountList()

    expect(wrapper.text()).toContain(en.network.unavailableMessage)
    const retryBtn = wrapper.find('button')
    expect(retryBtn.exists()).toBe(true)

    listCommunitiesMock.mockResolvedValue(makeResponse())
    await retryBtn.trigger('click')
    await flushPromises()

    expect(listCommunitiesMock).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('PARCToxicology')
  })

  it('debounces the search box and calls the API with q (server-side search, not client-side filtering)', async () => {
    vi.useFakeTimers()
    listCommunitiesMock.mockResolvedValue(makeResponse())

    const router = makeRouter()
    await router.push('/network')
    await router.isReady()
    const wrapper = mount(NetworkFipList, { global: { plugins: [makeI18n(), router] } })
    await flushPromises()
    listCommunitiesMock.mockClear()

    listCommunitiesMock.mockResolvedValue(
      makeResponse({
        items: [
          { iri: 'http://purl.org/np/RA1#PARCToxicology', label: 'PARCToxicology', fipCount: 3 },
          { iri: 'http://purl.org/np/RA9#PARCChemicals', label: 'PARC Chemicals', fipCount: 2 },
        ],
        total: 2,
      })
    )

    const input = wrapper.find('input[type="search"]')
    await input.setValue('PARC')
    // Not called before the debounce fires.
    expect(listCommunitiesMock).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    expect(listCommunitiesMock).toHaveBeenCalledTimes(1)
    expect(listCommunitiesMock).toHaveBeenCalledWith({ q: 'PARC', limit: 50 })
    expect(wrapper.text()).toContain('PARCToxicology')
    expect(wrapper.text()).toContain('PARC Chemicals')
  })

  it('resets to an unfiltered fetch (no q) when the search field is cleared', async () => {
    vi.useFakeTimers()
    listCommunitiesMock.mockResolvedValue(makeResponse())

    const router = makeRouter()
    await router.push('/network')
    await router.isReady()
    const wrapper = mount(NetworkFipList, { global: { plugins: [makeI18n(), router] } })
    await flushPromises()

    const input = wrapper.find('input[type="search"]')
    await input.setValue('PARC')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    listCommunitiesMock.mockClear()
    listCommunitiesMock.mockResolvedValue(makeResponse())

    await input.setValue('')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    expect(listCommunitiesMock).toHaveBeenCalledTimes(1)
    expect(listCommunitiesMock).toHaveBeenCalledWith({ q: undefined, limit: 50 })
  })

  it('shows "no results for x" distinct from the network error states, after the debounced search', async () => {
    vi.useFakeTimers()
    listCommunitiesMock.mockResolvedValue(makeResponse())

    const router = makeRouter()
    await router.push('/network')
    await router.isReady()
    const wrapper = mount(NetworkFipList, { global: { plugins: [makeI18n(), router] } })
    await flushPromises()

    listCommunitiesMock.mockResolvedValue(makeResponse({ items: [], total: 0 }))
    await wrapper.find('input[type="search"]').setValue('no-such-community')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    expect(wrapper.text()).toContain('no-such-community')
    expect(wrapper.text()).not.toContain(en.network.disabledMessage)
    expect(wrapper.text()).not.toContain(en.network.unavailableMessage)
  })

  it('shows a "Load more" button when total > items.length, which appends the next page via offset', async () => {
    listCommunitiesMock.mockResolvedValue(
      makeResponse({
        items: [{ iri: 'http://purl.org/np/RA1#PARCToxicology', label: 'PARCToxicology', fipCount: 3 }],
        total: 79,
      })
    )

    const wrapper = await mountList()

    expect(wrapper.text()).toContain('1 of 79 communities')
    const loadMoreBtn = wrapper.findAll('button').find((b) => b.text() === en.network.loadMore)
    expect(loadMoreBtn).toBeTruthy()

    listCommunitiesMock.mockResolvedValue(
      makeResponse({
        items: [{ iri: 'http://purl.org/np/RA2#Metabolomics', label: 'Metabolomics Community', fipCount: 1 }],
        total: 79,
      })
    )
    await loadMoreBtn!.trigger('click')
    await flushPromises()

    expect(listCommunitiesMock).toHaveBeenLastCalledWith({ q: undefined, limit: 50, offset: 1 })
    expect(wrapper.text()).toContain('PARCToxicology')
    expect(wrapper.text()).toContain('Metabolomics Community')
    expect(wrapper.text()).toContain('2 of 79 communities')
  })

  it('hides "Load more" once every community has been loaded', async () => {
    listCommunitiesMock.mockResolvedValue(makeResponse({ total: 2 }))

    const wrapper = await mountList()

    const loadMoreBtn = wrapper.findAll('button').find((b) => b.text() === en.network.loadMore)
    expect(loadMoreBtn).toBeUndefined()
  })
})
