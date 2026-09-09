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

  // Spec 08 §3.3 / criterion 17: the facilitator can pick several published
  // models, one per row, each with a short label; a single row still posts
  // exactly the legacy body (no `questionnaireRefs`).
  describe('multi-questionnaire rows (spec 08 §3.1/§3.3)', () => {
    function publicModel(id: string, title: string): KnowledgeModelSummary {
      return {
        id,
        version: '1.0.0',
        status: 'published',
        visibility: 'public',
        license: 'CC0-1.0',
        title: { en: title },
        description: { en: '' },
        createdAt: '2026-01-01T00:00:00Z',
        updatedAt: '2026-01-01T00:00:00Z',
        ownerId: null,
        isSystem: true,
        questionCount: 3,
        forkedFrom: null,
      }
    }

    async function mountMultiView() {
      const pinia = createPinia()
      setActivePinia(pinia)
      listKnowledgeModelsMock.mockResolvedValue({
        items: [publicModel('area-a', 'Area A'), publicModel('area-b', 'Area B'), publicModel('area-c', 'Area C')],
        total: 3,
      })
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

    it('a single row posts exactly the legacy questionnaireRef body, no questionnaireRefs', async () => {
      createSessionMock.mockResolvedValue({ id: 'session-1' } as unknown as SessionOut)
      const wrapper = await mountMultiView()
      await wrapper.get('input[type="text"]').setValue('My session')
      await wrapper.get('select').setValue('area-a@1.0.0')
      await flushPromises()

      await wrapper.get('form').trigger('submit.prevent')
      await flushPromises()

      expect(createSessionMock).toHaveBeenCalledWith(
        expect.not.objectContaining({ questionnaireRefs: expect.anything() })
      )
      expect(createSessionMock).toHaveBeenCalledWith(
        expect.objectContaining({ questionnaireRef: { id: 'area-a', version: '1.0.0' } })
      )
    })

    it('adding rows up to the 12 cap, then posting three labelled refs in row order', async () => {
      createSessionMock.mockResolvedValue({ id: 'session-1' } as unknown as SessionOut)
      const wrapper = await mountMultiView()
      await wrapper.get('input[type="text"]').setValue('My session')

      const addButtons = () => wrapper.findAll('button').filter((b) => b.text() === en.sessionAdmin.addQuestionnaire)
      await addButtons()[0].trigger('click')
      await addButtons()[0].trigger('click')
      await flushPromises()

      const selects = wrapper.findAll('select').filter((s) => s.attributes('required') !== undefined)
      expect(selects).toHaveLength(3)
      await selects[0].setValue('area-a@1.0.0')
      await selects[1].setValue('area-b@1.0.0')
      await selects[2].setValue('area-c@1.0.0')
      await flushPromises()

      const labelInputs = wrapper.findAll('.questionnaire-row input[type="text"]')
      expect(labelInputs).toHaveLength(3)
      // Prefilled from the model title once picked.
      expect((labelInputs[0].element as HTMLInputElement).value).toBe('Area A')
      await labelInputs[2].setValue('Custom C')

      await wrapper.get('form').trigger('submit.prevent')
      await flushPromises()

      expect(createSessionMock).toHaveBeenCalledWith(
        expect.objectContaining({
          questionnaireRef: { id: 'area-a', version: '1.0.0' },
          questionnaireRefs: [
            { id: 'area-a', version: '1.0.0', label: { en: 'Area A' } },
            { id: 'area-b', version: '1.0.0', label: { en: 'Area B' } },
            { id: 'area-c', version: '1.0.0', label: { en: 'Custom C' } },
          ],
        })
      )
    })

    it('caps at 12 rows — the "add another" button disappears', async () => {
      const wrapper = await mountMultiView()
      const addBtn = () => wrapper.findAll('button').find((b) => b.text() === en.sessionAdmin.addQuestionnaire)
      for (let i = 0; i < 11; i += 1) {
        expect(addBtn()).toBeTruthy()
        await addBtn()!.trigger('click')
      }
      await flushPromises()
      expect(wrapper.findAll('.questionnaire-row')).toHaveLength(12)
      expect(addBtn()).toBeUndefined()
    })
  })
})
