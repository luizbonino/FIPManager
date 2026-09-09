import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/en.json'

vi.mock('@/api/auth', () => ({
  requestPasswordReset: vi.fn(),
}))

import { requestPasswordReset } from '@/api/auth'
import ForgotPassword from './ForgotPassword.vue'

const requestPasswordResetMock = vi.mocked(requestPasswordReset)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function mountForgotPassword() {
  return mount(ForgotPassword, {
    global: {
      plugins: [makeI18n()],
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
    },
  })
}

// Criterion 10: ForgotPassword.vue renders the same panel for any submitted
// address (spec 07 §3: the backend is always 202, whatever the address).
describe('ForgotPassword.vue', () => {
  beforeEach(() => {
    requestPasswordResetMock.mockReset()
  })

  it('shows the "check your inbox" panel after submitting a real-looking address', async () => {
    requestPasswordResetMock.mockResolvedValue(undefined)
    const wrapper = mountForgotPassword()

    await wrapper.get('#email').setValue('alice@example.org')
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(requestPasswordResetMock).toHaveBeenCalledWith('alice@example.org')
    expect(wrapper.find('[data-testid="forgot-sent"]').exists()).toBe(true)
    expect(wrapper.text()).toContain(en.auth.forgotSent)
  })

  it('shows the exact same panel for a malformed / unknown address, even on a request failure', async () => {
    requestPasswordResetMock.mockRejectedValue(new Error('network error'))
    const wrapper = mountForgotPassword()

    await wrapper.get('#email').setValue('not-an-address')
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.find('[data-testid="forgot-sent"]').exists()).toBe(true)
    expect(wrapper.text()).toContain(en.auth.forgotSent)
  })
})
