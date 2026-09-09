import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
import type { FipOut } from '@/types/api'

// Spec 09: standalone FIPs — Home.vue's anonymous block gains a "Start a
// FIP" entry point and a "FIPs on this device" list built from stored edit
// tokens, dropping any entry whose GET /fips/{id} fails.
vi.mock('@/api/fips', () => ({
  getFip: vi.fn(),
}))
vi.mock('@/lib/editTokens', () => ({
  listTokenFipIds: vi.fn(),
  clearToken: vi.fn(),
  getToken: vi.fn(),
}))

import { getFip } from '@/api/fips'
import { ApiResponseError } from '@/api/client'
import { clearToken, getToken, listTokenFipIds } from '@/lib/editTokens'
import Home from './Home.vue'

const getFipMock = vi.mocked(getFip)
const listTokenFipIdsMock = vi.mocked(listTokenFipIds)
const clearTokenMock = vi.mocked(clearToken)
const getTokenMock = vi.mocked(getToken)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function makeFip(overrides: Partial<FipOut> = {}): FipOut {
  return {
    id: 'fip-1',
    ownerId: null,
    sessionId: null,
    visibility: 'link',
    questionnaireId: 'km-1',
    questionnaireVersion: '1.0.0',
    title: 'My FIP',
    community: null,
    relatedDmps: [],
    answers: [],
    language: 'en',
    license: 'CC0-1.0',
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    ...overrides,
  } as FipOut
}

async function mountHome() {
  const pinia = createPinia()
  setActivePinia(pinia)

  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Home', component: Home },
      { path: '/fips/new', name: 'FipNew', component: { template: '<div/>' } },
      { path: '/fips/:id/edit', name: 'FipEditor', component: { template: '<div/>' } },
      { path: '/join/:joinCode', name: 'JoinSession', component: { template: '<div/>' } },
    ],
  })
  await router.push('/')
  await router.isReady()

  const wrapper = mount(Home, { global: { plugins: [pinia, makeI18n(), router] } })
  await flushPromises()
  return wrapper
}

describe('Home.vue (spec 09: standalone FIPs)', () => {
  beforeEach(() => {
    getFipMock.mockReset()
    listTokenFipIdsMock.mockReset()
    clearTokenMock.mockReset()
    getTokenMock.mockReset()
    listTokenFipIdsMock.mockReturnValue([])
    getTokenMock.mockReturnValue(null)
  })

  it('shows the "Start a FIP" entry point for an anonymous visitor', async () => {
    const wrapper = await mountHome()

    expect(wrapper.text()).toContain(en.home.standaloneHeading)
    const startLink = wrapper.find('a[href="/fips/new"]')
    expect(startLink.exists()).toBe(true)
    expect(startLink.text()).toBe(en.home.startFip)
  })

  it('lists device FIPs fetched by stored edit token, titled by the FIP', async () => {
    listTokenFipIdsMock.mockReturnValue(['fip-1', 'fip-2'])
    getFipMock.mockImplementation(async (id: string) =>
      id === 'fip-1' ? makeFip({ id: 'fip-1', title: 'Alpha' }) : makeFip({ id: 'fip-2', title: null })
    )

    const wrapper = await mountHome()

    expect(wrapper.text()).toContain(en.home.yourFipsOnDevice)
    expect(wrapper.text()).toContain('Alpha')
    expect(wrapper.find('a[href="/fips/fip-1/edit"]').exists()).toBe(true)
    // No title -> falls back to the id.
    expect(wrapper.find('a[href="/fips/fip-2/edit"]').text()).toBe('fip-2')
  })

  it('passes the stored edit token to getFip', async () => {
    listTokenFipIdsMock.mockReturnValue(['fip-1'])
    getTokenMock.mockReturnValue('secret-token')
    getFipMock.mockResolvedValue(makeFip({ id: 'fip-1', title: 'Alpha' }))

    await mountHome()

    expect(getFipMock).toHaveBeenCalledWith('fip-1', 'secret-token')
  })

  it('drops a device FIP on a 404 (gone) response, and clears its stale token', async () => {
    listTokenFipIdsMock.mockReturnValue(['fip-ok', 'fip-gone'])
    getFipMock.mockImplementation(async (id: string) => {
      if (id === 'fip-gone') throw new ApiResponseError(404, { detail: 'not_found' })
      return makeFip({ id: 'fip-ok', title: 'Still here' })
    })

    const wrapper = await mountHome()

    expect(wrapper.text()).toContain('Still here')
    expect(wrapper.find('a[href="/fips/fip-gone/edit"]').exists()).toBe(false)
    expect(clearTokenMock).toHaveBeenCalledWith('fip-gone')
  })

  it('drops a device FIP on a 403 (revoked) response, and clears its stale token', async () => {
    listTokenFipIdsMock.mockReturnValue(['fip-revoked'])
    getFipMock.mockRejectedValue(new ApiResponseError(403, { detail: 'forbidden' }))

    const wrapper = await mountHome()

    expect(wrapper.find('a[href="/fips/fip-revoked/edit"]').exists()).toBe(false)
    expect(clearTokenMock).toHaveBeenCalledWith('fip-revoked')
  })

  it('keeps the token and still shows the entry (by id) on a network error', async () => {
    listTokenFipIdsMock.mockReturnValue(['fip-flaky'])
    getFipMock.mockRejectedValue(new ApiResponseError(0, { detail: 'Network error' }))

    const wrapper = await mountHome()

    const link = wrapper.find('a[href="/fips/fip-flaky/edit"]')
    expect(link.exists()).toBe(true)
    expect(link.text()).toBe('fip-flaky')
    expect(clearTokenMock).not.toHaveBeenCalled()
  })

  it('shows no device-FIPs section when no tokens are stored', async () => {
    const wrapper = await mountHome()

    expect(wrapper.text()).not.toContain(en.home.yourFipsOnDevice)
  })
})
