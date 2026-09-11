import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/en.json'
import DegradedBanner from './DegradedBanner.vue'

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

describe('DegradedBanner.vue (spec 13 §1.8/§2.4/§7.3/AC-5)', () => {
  it('names the degraded reason and the stale count', () => {
    const wrapper = mount(DegradedBanner, {
      props: { reason: 'projection_stale', variant: 'degraded', staleFips: 3, totalFips: 40 },
      global: { plugins: [makeI18n()] },
    })
    expect(wrapper.text()).toContain(en.dashboard.errors.projection_stale)
    expect(wrapper.text()).toContain('3')
    expect(wrapper.text()).toContain('40')
  })

  it('renders dashboard_disabled distinctly, with no retry affordance', () => {
    const wrapper = mount(DegradedBanner, { props: { reason: 'dashboard_disabled', variant: 'error' }, global: { plugins: [makeI18n()] } })
    expect(wrapper.text()).toContain(en.dashboard.errors.dashboard_disabled)
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('interpolates the minimum into population_too_small', () => {
    const wrapper = mount(DegradedBanner, { props: { reason: 'population_too_small', variant: 'error', minimum: 5 }, global: { plugins: [makeI18n()] } })
    expect(wrapper.text()).toContain('5')
  })

  it('shows the CLI hint only for an admin viewer', () => {
    const hint = 'python -m fipm backfill-declarations --only-stale'
    const nonAdmin = mount(DegradedBanner, {
      props: { reason: 'projection_stale', variant: 'error', hint, isAdmin: false },
      global: { plugins: [makeI18n()] },
    })
    expect(nonAdmin.text()).not.toContain(hint)

    const admin = mount(DegradedBanner, {
      props: { reason: 'projection_stale', variant: 'error', hint, isAdmin: true },
      global: { plugins: [makeI18n()] },
    })
    expect(admin.text()).toContain(hint)
  })

  it('falls back to a generic message for an unrecognised reason code', () => {
    const wrapper = mount(DegradedBanner, { props: { reason: 'some_future_code', variant: 'error' }, global: { plugins: [makeI18n()] } })
    expect(wrapper.text()).toContain(en.dashboard.errors.unknown)
  })

  it('applies the error variant class distinctly from degraded', () => {
    const degraded = mount(DegradedBanner, { props: { reason: 'projection_stale', variant: 'degraded' }, global: { plugins: [makeI18n()] } })
    const error = mount(DegradedBanner, { props: { reason: 'projection_stale', variant: 'error' }, global: { plugins: [makeI18n()] } })
    expect(degraded.find('.degraded-banner.error').exists()).toBe(false)
    expect(error.find('.degraded-banner.error').exists()).toBe(true)
  })
})
