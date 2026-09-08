import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
import type { KnowledgeModelOut, KnowledgeModelSummary, SessionOut } from '@/types/api'

// Bug: a private model was selectable here (SessionNew.vue lists any
// published model the owner can read, private or not), but participants
// then hit 404 `questionnaire_not_found` joining the session. The fix
// offers to flip the model's visibility to "link" before creating the
// session.
vi.mock('@/api/knowledgeModels', () => ({
  listKnowledgeModels: vi.fn(),
  patchKnowledgeModel: vi.fn(),
}))
vi.mock('@/api/sessions', () => ({
  createSession: vi.fn(),
}))

import { listKnowledgeModels, patchKnowledgeModel } from '@/api/knowledgeModels'
import { createSession } from '@/api/sessions'
import SessionNew from './SessionNew.vue'

const listKnowledgeModelsMock = vi.mocked(listKnowledgeModels)
const patchKnowledgeModelMock = vi.mocked(patchKnowledgeModel)
const createSessionMock = vi.mocked(createSession)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function privateModel(): KnowledgeModelSummary {
  return {
    id: 'km-private',
    version: '1.0.0',
    status: 'published',
    visibility: 'private',
    license: 'CC0-1.0',
    title: { en: 'Private model' },
    description: { en: '' },
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    ownerId: 'user-1',
    isSystem: false,
    questionCount: 3,
    forkedFrom: null,
  }
}

async function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  listKnowledgeModelsMock.mockResolvedValue({ items: [privateModel()], total: 1 })

  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/sessions/new', name: 'SessionNew', component: SessionNew },
      { path: '/sessions/:id', name: 'SessionDetail', component: { template: '<div/>' } },
    ],
  })
  await router.push('/sessions/new')
  await router.isReady()

  const wrapper = mount(SessionNew, { global: { plugins: [pinia, makeI18n(), router] } })
  await flushPromises()
  return wrapper
}

describe('SessionNew.vue', () => {
  beforeEach(() => {
    listKnowledgeModelsMock.mockReset()
    patchKnowledgeModelMock.mockReset()
    createSessionMock.mockReset()
  })

  it('shows a private-model notice with a checkbox checked by default once a private model is selected', async () => {
    const wrapper = await mountView()
    await wrapper.get('select').setValue('km-private@1.0.0')
    await flushPromises()

    expect(wrapper.text()).toContain(en.sessionAdmin.privateModelNotice)
    expect(wrapper.text()).toContain(en.sessionAdmin.makeModelLinkVisible)
    const checkbox = wrapper.get('input[type="checkbox"]')
    expect((checkbox.element as HTMLInputElement).checked).toBe(true)
  })

  it('PATCHes the model to visibility "link" before creating the session, when the checkbox stays checked', async () => {
    patchKnowledgeModelMock.mockResolvedValue({} as unknown as KnowledgeModelOut)
    createSessionMock.mockResolvedValue({ id: 'session-1' } as unknown as SessionOut)

    const wrapper = await mountView()
    await wrapper.get('select').setValue('km-private@1.0.0')
    await wrapper.get('input[type="text"]').setValue('My session')
    await flushPromises()

    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(patchKnowledgeModelMock).toHaveBeenCalledWith('km-private', '1.0.0', { visibility: 'link' })
    expect(createSessionMock).toHaveBeenCalled()
    // The patch must land before the session is created, or a participant
    // could still be handed a session pinned to a private questionnaire.
    const patchOrder = patchKnowledgeModelMock.mock.invocationCallOrder[0]
    const createOrder = createSessionMock.mock.invocationCallOrder[0]
    expect(patchOrder).toBeLessThan(createOrder)
  })

  it('does not PATCH visibility when the checkbox is unchecked', async () => {
    createSessionMock.mockResolvedValue({ id: 'session-1' } as unknown as SessionOut)

    const wrapper = await mountView()
    await wrapper.get('select').setValue('km-private@1.0.0')
    await wrapper.get('input[type="text"]').setValue('My session')
    await wrapper.get('input[type="checkbox"]').setValue(false)
    await flushPromises()

    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(patchKnowledgeModelMock).not.toHaveBeenCalled()
    expect(createSessionMock).toHaveBeenCalled()
  })
})
