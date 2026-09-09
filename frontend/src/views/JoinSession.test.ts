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

async function mountJoin() {
  const pinia = createPinia()
  setActivePinia(pinia)
  getSessionByCodeMock.mockResolvedValue(makeSession())

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
})
