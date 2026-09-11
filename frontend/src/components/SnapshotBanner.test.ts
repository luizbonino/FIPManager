import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/en.json'
import SnapshotBanner from './SnapshotBanner.vue'

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

describe('SnapshotBanner.vue (spec 13 §5.3/§6.1/AC-5)', () => {
  it('renders nothing for tier "live"', () => {
    const wrapper = mount(SnapshotBanner, { props: { status: 'live' }, global: { plugins: [makeI18n()] } })
    expect(wrapper.find('.snapshot-banner').exists()).toBe(false)
  })

  it('renders "computed X ago" and a Refresh button for tier "snapshot"', () => {
    const wrapper = mount(SnapshotBanner, {
      props: { status: 'snapshot', computedAt: new Date(Date.now() - 5 * 60000).toISOString() },
      global: { plugins: [makeI18n()] },
    })
    expect(wrapper.find('.snapshot-banner.snapshot').exists()).toBe(true)
    expect(wrapper.text()).toContain('5 minute(s)')
    expect(wrapper.find('button').text()).toBe(en.dashboard.snapshot.refresh)
  })

  it('emits "refresh" exactly once per click', async () => {
    const wrapper = mount(SnapshotBanner, {
      props: { status: 'snapshot', computedAt: new Date().toISOString() },
      global: { plugins: [makeI18n()] },
    })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })

  it('disables the Refresh button immediately after a click, so a fast double-click still POSTs once', async () => {
    const wrapper = mount(SnapshotBanner, {
      props: { status: 'snapshot', computedAt: new Date().toISOString() },
      global: { plugins: [makeI18n()] },
    })
    const button = wrapper.find('button')
    await button.trigger('click')
    await button.trigger('click')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })

  it('renders a computing message and no Refresh button while pending', () => {
    const wrapper = mount(SnapshotBanner, {
      props: { status: 'pending', attempt: 3, maxAttempts: 20 },
      global: { plugins: [makeI18n()] },
    })
    expect(wrapper.find('.snapshot-banner.pending').exists()).toBe(true)
    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.text()).toContain('3')
    expect(wrapper.text()).toContain('20')
  })
})
