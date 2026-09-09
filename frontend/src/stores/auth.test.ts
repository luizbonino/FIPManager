import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/client', () => ({
  get: vi.fn(),
  post: vi.fn(),
}))

import { get, post } from '@/api/client'
import { useAuthStore, type User } from './auth'

const getMock = vi.mocked(get)
const postMock = vi.mocked(post)

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

beforeEach(() => {
  setActivePinia(createPinia())
  getMock.mockReset()
  postMock.mockReset()
})

describe('auth store — logout', () => {
  it('clears `me` on a successful logout', async () => {
    const store = useAuthStore()
    store.state.me = makeUser()
    postMock.mockResolvedValue(undefined)

    await store.logout()

    expect(store.state.me).toBeNull()
  })

  // Finding: a failed logout POST (network blip, already-expired cookie)
  // must not leave the client still reading as authenticated.
  it('clears `me` even when the logout POST fails', async () => {
    const store = useAuthStore()
    store.state.me = makeUser()
    postMock.mockRejectedValue(new Error('network error'))

    await store.logout()

    expect(store.state.me).toBeNull()
    expect(store.state.error).toBe('Failed to logout')
  })
})

describe('auth store — login', () => {
  it('sets `me` from the login response, then refreshes it from /auth/me', async () => {
    const loginUser = makeUser({ displayName: 'From login' })
    const meUser = makeUser({ displayName: 'From me' })
    postMock.mockResolvedValue(loginUser)
    getMock.mockResolvedValue({ ...meUser, verificationRequired: false })

    const store = useAuthStore()
    await store.login('a@example.org', 'password123')

    expect(store.state.me?.displayName).toBe('From me')
    expect(store.state.error).toBeNull()
  })

  // Finding: a follow-up /auth/me failure right after a successful login
  // must not silently sign the user back out — keep `me` from the login
  // response and surface an error instead.
  it('keeps `me` from the login response and surfaces an error when the follow-up /auth/me fails', async () => {
    const loginUser = makeUser()
    postMock.mockResolvedValue(loginUser)
    getMock.mockRejectedValue(new Error('network error'))

    const store = useAuthStore()
    await store.login('a@example.org', 'password123')

    expect(store.state.me).toEqual(loginUser)
    expect(store.state.error).toBeTruthy()
  })

  it('clears `me` and sets an error when the login POST itself fails', async () => {
    postMock.mockRejectedValue(new Error('invalid credentials'))

    const store = useAuthStore()
    await expect(store.login('a@example.org', 'wrong')).rejects.toThrow()

    expect(store.state.me).toBeNull()
    expect(store.state.error).toBe('Invalid email or password')
  })
})
