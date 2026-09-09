import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'

vi.mock('@/api/auth', () => ({
  confirmPasswordReset: vi.fn(),
}))

import { confirmPasswordReset } from '@/api/auth'
import { ApiResponseError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import ResetPassword from './ResetPassword.vue'

const confirmPasswordResetMock = vi.mocked(confirmPasswordReset)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

async function mountResetPassword(token = 'tok123') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/reset-password', name: 'ResetPassword', component: ResetPassword },
      { path: '/login', name: 'Login', component: { template: '<div/>' } },
      { path: '/forgot-password', name: 'ForgotPassword', component: { template: '<div/>' } },
    ],
  })
  await router.push(`/reset-password?token=${token}`)
  await router.isReady()

  const wrapper = mount(ResetPassword, { global: { plugins: [pinia, makeI18n(), router] } })
  await flushPromises()
  return { wrapper, router, pinia }
}

// Criterion 10: Submit disabled until both fields match at >= 10 chars;
// renders auth.resetExpired with a /forgot-password link on 410.
describe('ResetPassword.vue', () => {
  beforeEach(() => {
    confirmPasswordResetMock.mockReset()
  })

  it('keeps Submit disabled until both password fields match at >= 10 characters', async () => {
    const { wrapper } = await mountResetPassword()
    const submitBtn = wrapper.get('button[type="submit"]')
    expect(submitBtn.attributes('disabled')).toBeDefined()

    await wrapper.get('#newPassword').setValue('short')
    await wrapper.get('#confirmPassword').setValue('short')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()

    await wrapper.get('#newPassword').setValue('correcthorsebattery')
    await wrapper.get('#confirmPassword').setValue('correcthorsebattery-different')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()

    await wrapper.get('#newPassword').setValue('correcthorsebattery')
    await wrapper.get('#confirmPassword').setValue('correcthorsebattery')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
  })

  it('submits {token, newPassword} and redirects to /login?resetOk=1 on success', async () => {
    confirmPasswordResetMock.mockResolvedValue(undefined)
    const { wrapper, router } = await mountResetPassword('the-token')

    await wrapper.get('#newPassword').setValue('correcthorsebattery')
    await wrapper.get('#confirmPassword').setValue('correcthorsebattery')
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(confirmPasswordResetMock).toHaveBeenCalledWith('the-token', 'correcthorsebattery')
    expect(router.currentRoute.value.name).toBe('Login')
    expect(router.currentRoute.value.query.resetOk).toBe('1')
  })

  // Finding: a signed-in browser resetting its own password must not still
  // read as authenticated on `/login`, or the router's
  // `(to.name === 'Login') && isAuthenticated` guard bounces it straight
  // back to /workspace with a cookie the reset just invalidated.
  it('clears the auth store\'s `me` on a successful reset, before navigating to /login', async () => {
    confirmPasswordResetMock.mockResolvedValue(undefined)
    const { wrapper, pinia } = await mountResetPassword('the-token')
    setActivePinia(pinia)
    const authStore = useAuthStore()
    authStore.state.me = {
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
    }

    await wrapper.get('#newPassword').setValue('correcthorsebattery')
    await wrapper.get('#confirmPassword').setValue('correcthorsebattery')
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(authStore.state.me).toBeNull()
  })

  it('renders auth.resetExpired with a /forgot-password link on a 410 token_expired', async () => {
    confirmPasswordResetMock.mockRejectedValue(new ApiResponseError(410, { detail: 'token_expired' }))
    const { wrapper } = await mountResetPassword()

    await wrapper.get('#newPassword').setValue('correcthorsebattery')
    await wrapper.get('#confirmPassword').setValue('correcthorsebattery')
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain(en.auth.resetExpired)
    const link = wrapper.findComponent({ name: 'RouterLink' })
    expect(link.props('to')).toBe('/forgot-password')
  })
})
