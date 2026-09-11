import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
import type { FipOut } from '@/types/api'

// Spec 09: standalone FIPs — Home.vue's anonymous block gains a "Start a
// FIP" entry point and a "FIPs on this device" list built from stored edit
// tokens, dropping any entry whose GET /fips/{id} fails. The signed-in
// strip (this task) reuses GET /api/me/fips (Workspace's own data source)
// and GET /api/health for the dashboard-enabled flag (App.vue's own idiom).
vi.mock('@/api/fips', () => ({
  getFip: vi.fn(),
}))
vi.mock('@/lib/editTokens', () => ({
  listTokenFipIds: vi.fn(),
  clearToken: vi.fn(),
  getToken: vi.fn(),
}))
vi.mock('@/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/api/client')>('@/api/client')
  return { ...actual, get: vi.fn() }
})
vi.mock('@/api/me', () => ({
  myFips: vi.fn(),
}))

import { getFip } from '@/api/fips'
import { ApiResponseError, get } from '@/api/client'
import { myFips } from '@/api/me'
import { clearToken, getToken, listTokenFipIds } from '@/lib/editTokens'
import { useAuthStore, type User } from '@/stores/auth'
import Home from './Home.vue'

const getFipMock = vi.mocked(getFip)
const listTokenFipIdsMock = vi.mocked(listTokenFipIds)
const clearTokenMock = vi.mocked(clearToken)
const getTokenMock = vi.mocked(getToken)
const healthGetMock = vi.mocked(get)
const myFipsMock = vi.mocked(myFips)

function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: 'u1',
    email: 'a@example.org',
    displayName: 'Ada',
    role: 'user',
    language: 'en',
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    mustChangePassword: false,
    privacyAcceptedVersion: '1.0',
    emailVerifiedAt: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

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

async function mountHome(options: { authenticated?: boolean; dashboardEnabled?: boolean } = {}) {
  const { authenticated = false, dashboardEnabled = true } = options
  const pinia = createPinia()
  setActivePinia(pinia)

  healthGetMock.mockImplementation(async (path: string) => {
    if (path === '/auth/me') {
      if (!authenticated) throw new ApiResponseError(401, { detail: 'unauthorized' })
      return { ...makeUser(), verificationRequired: false }
    }
    if (path === '/health') {
      return { dashboardEnabled }
    }
    throw new Error(`unexpected path ${path}`)
  })

  const authStore = useAuthStore()
  await authStore.restoreSession()

  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Home', component: Home },
      { path: '/fips/new', name: 'FipNew', component: { template: '<div/>' } },
      { path: '/fips/:id', name: 'FipRead', component: { template: '<div/>' } },
      { path: '/fips/:id/edit', name: 'FipEditor', component: { template: '<div/>' } },
      { path: '/join/:joinCode', name: 'JoinSession', component: { template: '<div/>' } },
      { path: '/workspace', name: 'Workspace', component: { template: '<div/>' } },
      { path: '/sessions/new', name: 'SessionNew', component: { template: '<div/>' } },
      { path: '/dashboard', name: 'DashboardHome', component: { template: '<div/>' } },
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
    healthGetMock.mockReset()
    myFipsMock.mockReset()
    listTokenFipIdsMock.mockReturnValue([])
    getTokenMock.mockReturnValue(null)
    myFipsMock.mockResolvedValue({ items: [], total: 0 })
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

  describe('signed-in visitor', () => {
    it('adds a welcome strip with quick links, without removing the join-code box', async () => {
      const wrapper = await mountHome({ authenticated: true })

      expect(wrapper.text()).toContain('Ada')
      expect(wrapper.find('a[href="/workspace"]').exists()).toBe(true)
      expect(wrapper.find('a[href="/sessions/new"]').exists()).toBe(true)

      // Task: signing in ADDS to the home page — the tagline, join-code
      // box and "fill in a FIP on your own" block all stay visible.
      expect(wrapper.text()).toContain(en.home.tagline)
      expect(wrapper.find('#home-join-code').exists()).toBe(true)
      expect(wrapper.text()).toContain(en.home.standaloneHeading)
    })

    it('hides the dashboard quick link when the deployment has it disabled', async () => {
      const wrapper = await mountHome({ authenticated: true, dashboardEnabled: false })

      expect(wrapper.find('a[href="/dashboard"]').exists()).toBe(false)
    })

    it('shows the dashboard quick link when the deployment has it enabled', async () => {
      const wrapper = await mountHome({ authenticated: true, dashboardEnabled: true })

      expect(wrapper.find('a[href="/dashboard"]').exists()).toBe(true)
    })

    it('lists recent FIPs from GET /api/me/fips', async () => {
      myFipsMock.mockResolvedValue({
        items: [makeFip({ id: 'fip-9', title: 'Recent one' })],
        total: 1,
      })

      const wrapper = await mountHome({ authenticated: true })

      expect(myFipsMock).toHaveBeenCalledWith({ limit: 5 })
      expect(wrapper.text()).toContain('Recent one')
      expect(wrapper.find('a[href="/fips/fip-9"]').exists()).toBe(true)
    })

    it('does not fetch recent FIPs for an anonymous visitor', async () => {
      await mountHome({ authenticated: false })

      expect(myFipsMock).not.toHaveBeenCalled()
    })

    // Workshop devices are shared between groups, and an edit token grants
    // write access: if the device list followed the signed-in user, user B
    // would get a working edit link for the anonymous FIP user A left in this
    // browser. The list stays anonymous-only.
    it('does not expose device FIPs, or their edit links, to a signed-in visitor', async () => {
      listTokenFipIdsMock.mockReturnValue(['fip-1'])
      getFipMock.mockResolvedValue(makeFip({ id: 'fip-1', title: 'Alpha' }))

      const wrapper = await mountHome({ authenticated: true })

      expect(wrapper.text()).not.toContain(en.home.yourFipsOnDevice)
      expect(wrapper.find('a[href="/fips/fip-1/edit"]').exists()).toBe(false)
      expect(getFipMock).not.toHaveBeenCalled()
    })
  })
})
