import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// `router/index.ts` keeps a module-level `sessionRestored` flag and creates
// the router instance at import time, so each test re-imports it fresh
// (`vi.resetModules()`) with its own Pinia instance and its own mocked
// `GET /auth/me` response.
vi.mock('@/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/api/client')>('@/api/client')
  return { ...actual, get: vi.fn() }
})

import { get } from '@/api/client'
import type { User } from '@/stores/auth'

const getMock = vi.mocked(get)

function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: 'u1',
    email: 'a@example.org',
    displayName: 'A',
    role: 'user',
    language: 'en',
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    mustChangePassword: false,
    privacyAcceptedVersion: '1.0',
    emailVerifiedAt: null,
    ...overrides,
  }
}

describe('router — /admin and mustChangePassword guards', () => {
  beforeEach(() => {
    vi.resetModules()
    setActivePinia(createPinia())
    getMock.mockReset()
  })

  it('redirects an anonymous visitor away from /admin, to /login with a redirect query', async () => {
    getMock.mockRejectedValue(new Error('not signed in'))
    const { default: router } = await import('./index')

    await router.push('/admin')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('Login')
    expect(router.currentRoute.value.query.redirect).toBe('/admin')
  })

  it('lets any signed-in user reach the /admin route (Admin.vue itself gates non-admin content)', async () => {
    getMock.mockResolvedValue(makeUser({ role: 'user' }))
    const { default: router } = await import('./index')

    await router.push('/admin')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('Admin')
  })

  it('forces a mustChangePassword user to /account/password from an unrelated authenticated route', async () => {
    getMock.mockResolvedValue(makeUser({ mustChangePassword: true }))
    const { default: router } = await import('./index')

    await router.push('/workspace')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('ChangePassword')
    expect(router.currentRoute.value.query.redirect).toBe('/workspace')
  })

  it('lets a mustChangePassword user reach ChangePassword itself, no redirect loop', async () => {
    getMock.mockResolvedValue(makeUser({ mustChangePassword: true }))
    const { default: router } = await import('./index')

    await router.push('/account/password')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('ChangePassword')
  })

  it.each(['/privacy', '/forgot-password', '/reset-password', '/verify'])(
    'lets a mustChangePassword user reach %s without being bounced to /account/password',
    async (path) => {
      getMock.mockResolvedValue(makeUser({ mustChangePassword: true }))
      const { default: router } = await import('./index')

      await router.push(path)
      await router.isReady()

      expect(router.currentRoute.value.path).toBe(path)
    }
  )

  it('does not force a public route for a mustChangePassword user off course before login (anonymous is unaffected)', async () => {
    getMock.mockRejectedValue(new Error('not signed in'))
    const { default: router } = await import('./index')

    await router.push('/privacy')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('Privacy')
  })
})
