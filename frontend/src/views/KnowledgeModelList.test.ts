import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
import { useAuthStore, type User } from '@/stores/auth'
import type { KnowledgeModelSummary } from '@/types/api'

// Bug: the backend now sends `isUnownedDraft: true` on shipped drafts
// imported from data/ (ownerId NULL, isSystem false). An admin should see
// them grouped under "Drafts to review" above "Mine", with an Edit link;
// a normal user must never see the group or the model at all.
vi.mock('@/api/knowledgeModels', () => ({
  listKnowledgeModels: vi.fn(),
  forkKnowledgeModel: vi.fn(),
  importKnowledgeModel: vi.fn(),
}))

import { listKnowledgeModels } from '@/api/knowledgeModels'
import KnowledgeModelList from './KnowledgeModelList.vue'

const listKnowledgeModelsMock = vi.mocked(listKnowledgeModels)

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

function unownedDraft(): KnowledgeModelSummary {
  return {
    id: 'km-shipped',
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

async function mountView(user: User | null) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.state.me = user
  listKnowledgeModelsMock.mockResolvedValue({ items: [unownedDraft()], total: 1 })

  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/knowledge-models', name: 'KnowledgeModelList', component: KnowledgeModelList },
      { path: '/knowledge-models/new', name: 'KnowledgeModelNew', component: { template: '<div/>' } },
      { path: '/knowledge-models/:id/:version', name: 'KnowledgeModelRead', component: { template: '<div/>' } },
      { path: '/knowledge-models/:id/:version/edit', name: 'KnowledgeModelEditor', component: { template: '<div/>' } },
    ],
  })
  await router.push('/knowledge-models')
  await router.isReady()

  const wrapper = mount(KnowledgeModelList, { global: { plugins: [pinia, makeI18n(), router] } })
  await flushPromises()
  return wrapper
}

describe('KnowledgeModelList.vue — unowned drafts', () => {
  beforeEach(() => {
    listKnowledgeModelsMock.mockReset()
  })

  it('groups an isUnownedDraft item under "Drafts to review" with an Edit link, for an admin', async () => {
    const wrapper = await mountView(makeUser({ role: 'admin' }))

    expect(wrapper.text()).toContain(en.km.unownedDrafts)
    expect(wrapper.text()).toContain(en.km.unownedDraftHint)
    expect(wrapper.text()).toContain('Shipped draft')

    const editLinks = wrapper.findAll('a').filter((a) => a.text() === en.km.edit)
    expect(editLinks).toHaveLength(1)
    expect(editLinks[0].attributes('href')).toBe('/knowledge-models/km-shipped/1.0.0/edit')
  })

  it('hides the "Drafts to review" group and the model for a normal user', async () => {
    const wrapper = await mountView(makeUser({ role: 'user' }))

    expect(wrapper.text()).not.toContain(en.km.unownedDrafts)
    expect(wrapper.text()).not.toContain('Shipped draft')
  })
})
