import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/en.json'
import { useAuthStore, type User } from '@/stores/auth'

vi.mock('@/api/admin', () => ({
  listAdminUsers: vi.fn(),
  listAdminFers: vi.fn(),
  resetUserPassword: vi.fn(),
  promoteFer: vi.fn(),
  mergeFer: vi.fn(),
}))
vi.mock('@/api/fers', () => ({
  listFers: vi.fn(),
}))

import { listAdminFers, listAdminUsers } from '@/api/admin'
import Admin from './Admin.vue'

const listAdminUsersMock = vi.mocked(listAdminUsers)
const listAdminFersMock = vi.mocked(listAdminFers)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

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
    ...overrides,
  }
}

function mountAdmin(user: User | null) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.state.me = user
  const wrapper = mount(Admin, { global: { plugins: [pinia, makeI18n()] } })
  return { wrapper, auth }
}

// Criterion 14 (docs/specs/05-v1-completion.md §8): a signed-in non-admin
// (and an anonymous visitor, which the router itself would normally bounce
// to /login before ever reaching this component — this asserts the
// component-level fallback holds regardless) sees `common.notFound` and
// the view calls no `/api/admin/*` route at all.
describe('Admin.vue — non-admin route guard', () => {
  beforeEach(() => {
    listAdminUsersMock.mockReset()
    listAdminFersMock.mockReset()
  })

  it('renders common.notFound and calls no admin API for a signed-in non-admin', async () => {
    const { wrapper } = mountAdmin(makeUser({ role: 'user' }))
    await flushPromises()

    expect(wrapper.text()).toContain(en.common.notFound)
    expect(wrapper.find('.users-table').exists()).toBe(false)
    expect(listAdminUsersMock).not.toHaveBeenCalled()
    expect(listAdminFersMock).not.toHaveBeenCalled()
  })

  it('renders common.notFound and calls no admin API for an anonymous visitor', async () => {
    const { wrapper } = mountAdmin(null)
    await flushPromises()

    expect(wrapper.text()).toContain(en.common.notFound)
    expect(listAdminUsersMock).not.toHaveBeenCalled()
    expect(listAdminFersMock).not.toHaveBeenCalled()
  })

  it('loads and renders the users table and pending FERs for an admin', async () => {
    listAdminUsersMock.mockResolvedValue({
      items: [
        {
          id: 'u2',
          email: 'b@example.org',
          displayName: 'B',
          role: 'user',
          language: 'en',
          createdAt: '2026-01-01T00:00:00Z',
          mustChangePassword: false,
          privacyAcceptedVersion: null,
          fipCount: 2,
          sessionCount: 1,
          knowledgeModelCount: 0,
        },
      ],
      total: 1,
    })
    listAdminFersMock.mockResolvedValue({ items: [], total: 0 })

    const { wrapper } = mountAdmin(makeUser({ role: 'admin' }))
    await flushPromises()

    expect(listAdminUsersMock).toHaveBeenCalledTimes(1)
    expect(listAdminFersMock).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('b@example.org')
    expect(wrapper.text()).not.toContain(en.common.notFound)
  })
})
