import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import en from '@/i18n/en.json'

vi.mock('@/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/api/client')>('@/api/client')
  return { ...actual, get: vi.fn() }
})
vi.mock('@/api/me', () => ({
  myFips: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  mySessions: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  myKnowledgeModels: vi.fn().mockResolvedValue({ items: [], total: 0 }),
}))
vi.mock('@/api/knowledgeModels', () => ({
  listKnowledgeModels: vi.fn().mockResolvedValue({ items: [], total: 0 }),
}))
vi.mock('@/api/auth', () => ({
  resendVerification: vi.fn(),
}))

import { get } from '@/api/client'
import { listKnowledgeModels } from '@/api/knowledgeModels'
import { resendVerification } from '@/api/auth'
import { useAuthStore, type User } from '@/stores/auth'
import Workspace from './Workspace.vue'
import type { KnowledgeModelSummary } from '@/types/api'

const getMock = vi.mocked(get)
const listKnowledgeModelsMock = vi.mocked(listKnowledgeModels)
const resendVerificationMock = vi.mocked(resendVerification)

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
    emailVerifiedAt: null,
    ...overrides,
  }
}

async function mountWorkspace(
  verificationRequired: boolean,
  emailVerifiedAt: string | null,
  userOverrides: Partial<User> = {}
) {
  const pinia = createPinia()
  setActivePinia(pinia)
  getMock.mockResolvedValue({ ...makeUser({ emailVerifiedAt, ...userOverrides }), verificationRequired })
  const authStore = useAuthStore()
  await authStore.restoreSession()

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', name: 'Home', component: { template: '<div/>' } }],
  })

  const wrapper = mount(Workspace, {
    global: {
      plugins: [pinia, makeI18n(), router],
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
    },
  })
  await flushPromises()
  return wrapper
}

function unownedDraft(id: string): KnowledgeModelSummary {
  return {
    id,
    version: '1.0.0',
    status: 'draft',
    visibility: 'private',
    license: 'CC0-1.0',
    title: { en: 'Shipped draft' },
    description: { en: '' },
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    ownerId: null,
    isSystem: false,
    isUnownedDraft: true,
    questionCount: 3,
    forkedFrom: null,
  }
}

// Criterion 10: Workspace.vue shows the verify banner only when
// `verificationRequired && !emailVerifiedAt` (spec 07 §3).
describe('Workspace.vue — email verification banner', () => {
  beforeEach(() => {
    getMock.mockReset()
    resendVerificationMock.mockReset()
  })

  it('shows the banner when verification is required and the account is unverified', async () => {
    const wrapper = await mountWorkspace(true, null)
    expect(wrapper.text()).toContain(en.auth.verifyBanner)
  })

  it('hides the banner when verification is required but the account is already verified', async () => {
    const wrapper = await mountWorkspace(true, '2026-02-01T00:00:00Z')
    expect(wrapper.text()).not.toContain(en.auth.verifyBanner)
  })

  it('hides the banner when verification is not required, even for an unverified account', async () => {
    const wrapper = await mountWorkspace(false, null)
    expect(wrapper.text()).not.toContain(en.auth.verifyBanner)
  })

  it('calls the resend endpoint from the banner’s button', async () => {
    resendVerificationMock.mockResolvedValue(undefined)
    const wrapper = await mountWorkspace(true, null)

    const resendBtn = wrapper.findAll('button').find((b) => b.text() === en.auth.resend)
    expect(resendBtn).toBeTruthy()
    await resendBtn!.trigger('click')
    await flushPromises()

    expect(resendVerificationMock).toHaveBeenCalled()
    expect(wrapper.text()).toContain(en.auth.verifySent)
  })
})

// Workspace links to the public catalogue, and points admins at unowned
// (shipped-draft) knowledge models awaiting review, computed from the same
// listKnowledgeModels() call fetchData already makes for the FIP progress
// denominator — no extra request.
describe('Workspace.vue — browse-models link and unowned-drafts notice', () => {
  beforeEach(() => {
    getMock.mockReset()
    listKnowledgeModelsMock.mockReset()
  })

  it('always shows a link to browse all knowledge models', async () => {
    listKnowledgeModelsMock.mockResolvedValue({ items: [], total: 0 })
    const wrapper = await mountWorkspace(false, null)

    const browseLink = wrapper.findAll('a').find((a) => a.text() === en.workspace.browseModels)
    expect(browseLink).toBeTruthy()
  })

  it('shows the unowned-drafts notice to an admin when drafts are waiting for review', async () => {
    listKnowledgeModelsMock.mockResolvedValue({ items: [unownedDraft('km-a'), unownedDraft('km-b')], total: 2 })
    const wrapper = await mountWorkspace(false, null, { role: 'admin' })

    expect(wrapper.text()).toContain('2')
    expect(wrapper.find('.notice').exists()).toBe(true)
    const reviewLink = wrapper.findAll('a').find((a) => a.text() === en.workspace.reviewDrafts)
    expect(reviewLink).toBeTruthy()
  })

  it('hides the unowned-drafts notice for a non-admin, even when drafts exist', async () => {
    listKnowledgeModelsMock.mockResolvedValue({ items: [unownedDraft('km-a')], total: 1 })
    const wrapper = await mountWorkspace(false, null, { role: 'user' })

    expect(wrapper.find('.notice').exists()).toBe(false)
  })

  it('hides the unowned-drafts notice for an admin when there are no unowned drafts', async () => {
    listKnowledgeModelsMock.mockResolvedValue({ items: [], total: 0 })
    const wrapper = await mountWorkspace(false, null, { role: 'admin' })

    expect(wrapper.find('.notice').exists()).toBe(false)
  })
})
