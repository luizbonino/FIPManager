import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
import { ApiResponseError } from '@/api/client'
import type { SessionPublicOut } from '@/types/api'

// Bug: `POST /api/fips` failures other than 409/403 (e.g. 404
// `questionnaire_not_found` when the session's model went private again,
// or 404 `session_not_found`) fell through to the generic
// `errors.serverError` message instead of a specific one.
vi.mock('@/api/sessions', () => ({
  getSessionByCode: vi.fn(),
}))
vi.mock('@/api/fips', () => ({
  createFip: vi.fn(),
}))

import { getSessionByCode } from '@/api/sessions'
import { createFip } from '@/api/fips'
import JoinSession from './JoinSession.vue'

const getSessionByCodeMock = vi.mocked(getSessionByCode)
const createFipMock = vi.mocked(createFip)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function makeSession(): SessionPublicOut {
  return {
    id: 'session-1',
    title: 'My session',
    status: 'open',
    questionnaireRef: { id: 'km-1', version: '1.0.0' },
    defaultLanguage: 'en',
    facilitatorName: 'Alice',
    questionnaireTitle: { en: 'Model' },
  }
}

async function mountJoin(session: SessionPublicOut = makeSession()) {
  const pinia = createPinia()
  setActivePinia(pinia)
  getSessionByCodeMock.mockResolvedValue(session)

  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/join/:joinCode', name: 'JoinSession', component: JoinSession, props: true },
      { path: '/fips/:id/edit', name: 'FipEditor', component: { template: '<div/>' } },
      { path: '/privacy', name: 'Privacy', component: { template: '<div/>' } },
    ],
  })
  await router.push('/join/ABC123')
  await router.isReady()

  const wrapper = mount(JoinSession, { global: { plugins: [pinia, makeI18n(), router] } })
  await flushPromises()
  return wrapper
}

async function submitCommunityForm(wrapper: Awaited<ReturnType<typeof mountJoin>>) {
  await wrapper.get('input[type="text"]').setValue('My community')
  await wrapper.get('form').trigger('submit.prevent')
  await flushPromises()
}

describe('JoinSession.vue', () => {
  beforeEach(() => {
    getSessionByCodeMock.mockReset()
    createFipMock.mockReset()
  })

  it('maps a 404 questionnaire_not_found from POST /fips to a specific message, not the generic server error', async () => {
    createFipMock.mockRejectedValue(
      new ApiResponseError(404, { detail: 'questionnaire_not_found' })
    )
    const wrapper = await mountJoin()
    await submitCommunityForm(wrapper)

    expect(wrapper.text()).toContain(en.join.questionnaireUnavailable)
    expect(wrapper.text()).not.toContain(en.errors.serverError)
  })

  it('maps a 404 session_not_found from POST /fips to the invalid-code message, not the generic server error', async () => {
    createFipMock.mockRejectedValue(new ApiResponseError(404, { detail: 'session_not_found' }))
    const wrapper = await mountJoin()
    await submitCommunityForm(wrapper)

    expect(wrapper.text()).toContain(en.join.invalidCode)
    expect(wrapper.text()).not.toContain(en.errors.serverError)
  })

  it('maps a 409 session_closed from POST /fips to the closed-session message', async () => {
    createFipMock.mockRejectedValue(new ApiResponseError(409, { detail: 'session_closed' }))
    const wrapper = await mountJoin()
    await submitCommunityForm(wrapper)

    expect(wrapper.text()).toContain(en.join.closed)
  })

  it('a one-ref session (questionnaireRefs absent) shows no area radio group', async () => {
    const wrapper = await mountJoin()
    expect(wrapper.text()).not.toContain(en.join.chooseArea)
    expect(wrapper.find('input[type="radio"]').exists()).toBe(false)
  })

  // Spec 08 §3.2/criterion 17: a multi-ref session shows the required area
  // radio group, remembers the choice, and the created FIP conforms to the
  // chosen model.
  describe('multi-ref session (spec 08 §3.2)', () => {
    function multiRefSession(): SessionPublicOut {
      return {
        ...makeSession(),
        questionnaireRefs: [
          { id: 'area-a', version: '1.0.0', label: { en: 'Area A' }, title: { en: 'Area A model' } },
          { id: 'area-b', version: '1.0.0', label: { en: 'Area B' }, title: { en: 'Area B model' } },
        ],
      }
    }

    beforeEach(() => {
      localStorage.clear()
    })

    it('shows the required radio group with one label per ref, defaulting to the first', async () => {
      const wrapper = await mountJoin(multiRefSession())

      expect(wrapper.text()).toContain(en.join.chooseArea)
      const radios = wrapper.findAll('input[type="radio"]')
      expect(radios).toHaveLength(2)
      expect(wrapper.text()).toContain('Area A')
      expect(wrapper.text()).toContain('Area B')
      expect((radios[0].element as HTMLInputElement).checked).toBe(true)
    })

    it('the created FIP conforms to the chosen area, and the choice is remembered in localStorage', async () => {
      createFipMock.mockResolvedValue({ id: 'fip-1', editToken: 'tok' } as never)

      const wrapper = await mountJoin(multiRefSession())
      const radios = wrapper.findAll('input[type="radio"]')
      await radios[1].setValue()
      await submitCommunityForm(wrapper)

      expect(createFipMock).toHaveBeenCalledWith(
        expect.objectContaining({ questionnaireRef: { id: 'area-b', version: '1.0.0' } })
      )
      expect(localStorage.getItem('fipm.join.session-1.area')).toBe('area-b@1.0.0')
    })
  })
})
