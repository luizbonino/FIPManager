import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'

vi.mock('@/api/privacy', () => ({
  getPrivacyNotice: vi.fn(),
}))
vi.mock('@/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/api/client')>('@/api/client')
  return { ...actual, get: vi.fn(), post: vi.fn() }
})

import { getPrivacyNotice } from '@/api/privacy'
import { get, post } from '@/api/client'
import Register from './Register.vue'

const getPrivacyNoticeMock = vi.mocked(getPrivacyNotice)
const getMock = vi.mocked(get)
const postMock = vi.mocked(post)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

async function mountRegister() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/register', name: 'Register', component: Register },
      { path: '/login', name: 'Login', component: { template: '<div/>' } },
      { path: '/privacy', name: 'Privacy', component: { template: '<div/>' } },
      { path: '/workspace', name: 'Workspace', component: { template: '<div/>' } },
    ],
  })
  await router.push('/register')
  await router.isReady()

  const wrapper = mount(Register, { global: { plugins: [pinia, makeI18n(), router] } })
  await flushPromises()
  return wrapper
}

async function fillRequiredFields(wrapper: Awaited<ReturnType<typeof mountRegister>>) {
  await wrapper.get('#displayName').setValue('Alice')
  await wrapper.get('#email').setValue('alice@example.org')
  await wrapper.get('#password').setValue('correcthorsebattery')
  await wrapper.get('#confirmPassword').setValue('correcthorsebattery')
}

// Criterion 15 (docs/specs/05-v1-completion.md §8): submit stays disabled
// until the privacy checkbox is ticked, and the POST body carries the
// version fetched from GET /api/privacy.
describe('Register.vue — privacy notice acceptance', () => {
  beforeEach(() => {
    getPrivacyNoticeMock.mockReset()
    getMock.mockReset()
    postMock.mockReset()
    getMock.mockRejectedValue(new Error('not signed in'))
  })

  it('keeps submit disabled until the privacy checkbox is ticked, even with every other field valid', async () => {
    getPrivacyNoticeMock.mockResolvedValue({ version: '1.0', date: '2026-09-12', lang: 'en', markdown: '# Privacy' })
    const wrapper = await mountRegister()
    await fillRequiredFields(wrapper)

    const submitBtn = wrapper.get('button[type="submit"]')
    expect(submitBtn.attributes('disabled')).toBeDefined()

    await wrapper.get('input[type="checkbox"]').setValue(true)
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
  })

  it('keeps submit disabled while the privacy notice has not loaded yet, even once ticked', async () => {
    getPrivacyNoticeMock.mockRejectedValue(new Error('network error'))
    const wrapper = await mountRegister()
    await fillRequiredFields(wrapper)
    await wrapper.get('input[type="checkbox"]').setValue(true)

    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
  })

  it('sends the version fetched from GET /api/privacy as privacyAcceptedVersion on submit', async () => {
    getPrivacyNoticeMock.mockResolvedValue({ version: '1.0', date: '2026-09-12', lang: 'en', markdown: '# Privacy' })
    postMock.mockResolvedValue({
      id: 'u1',
      email: 'alice@example.org',
      displayName: 'Alice',
      role: 'user',
      language: 'en',
      createdAt: '',
      updatedAt: '',
      mustChangePassword: false,
      privacyAcceptedVersion: '1.0',
    })

    const wrapper = await mountRegister()
    await fillRequiredFields(wrapper)
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(postMock).toHaveBeenCalledWith(
      '/auth/register',
      expect.objectContaining({ privacyAcceptedVersion: '1.0' })
    )
  })
})
