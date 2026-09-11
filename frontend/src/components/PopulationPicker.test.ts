import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/en.json'
import { emptyPopulationSpec } from '@/lib/dashboard'
import PopulationPicker from './PopulationPicker.vue'

vi.mock('@/api/dashboard', () => ({
  savePopulation: vi.fn(),
}))

import { savePopulation } from '@/api/dashboard'

const savePopulationMock = vi.mocked(savePopulation)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

describe('PopulationPicker.vue (spec 13 §2.1/§6.1/§6.3)', () => {
  beforeEach(() => {
    savePopulationMock.mockReset()
  })

  it('adds a "public" term to include on Add', async () => {
    const wrapper = mount(PopulationPicker, {
      props: { modelValue: emptyPopulationSpec() },
      global: { plugins: [makeI18n()] },
    })
    await wrapper.find('select').setValue('public')
    await wrapper.find('button.btn-secondary').trigger('click')
    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    const last = emitted![emitted!.length - 1][0] as ReturnType<typeof emptyPopulationSpec>
    expect(last.include).toEqual([{ kind: 'public' }])
  })

  it('requires an id before adding a session term', async () => {
    const wrapper = mount(PopulationPicker, {
      props: { modelValue: emptyPopulationSpec() },
      global: { plugins: [makeI18n()] },
    })
    await wrapper.find('select').setValue('session')
    // No id typed — Add should not emit.
    await wrapper.find('button.btn-secondary').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeFalsy()
  })

  it('adds a session term with the typed id', async () => {
    const wrapper = mount(PopulationPicker, {
      props: { modelValue: emptyPopulationSpec() },
      global: { plugins: [makeI18n()] },
    })
    await wrapper.find('select').setValue('session')
    const idInput = wrapper.findAll('input').find((i) => i.attributes('type') === 'text')!
    await idInput.setValue('s_abc')
    await wrapper.find('button.btn-secondary').trigger('click')
    const emitted = wrapper.emitted('update:modelValue')!
    const last = emitted[emitted.length - 1][0] as ReturnType<typeof emptyPopulationSpec>
    expect(last.include).toEqual([{ kind: 'session', id: 's_abc' }])
  })

  it('removes a term when its chip button is clicked', async () => {
    const spec = { ...emptyPopulationSpec(), include: [{ kind: 'public' as const }, { kind: 'network' as const }] }
    const wrapper = mount(PopulationPicker, { props: { modelValue: spec }, global: { plugins: [makeI18n()] } })
    await wrapper.find('.term-chip .remove-btn').trigger('click')
    const emitted = wrapper.emitted('update:modelValue')!
    const last = emitted[emitted.length - 1][0] as ReturnType<typeof emptyPopulationSpec>
    expect(last.include).toEqual([{ kind: 'network' }])
  })

  it('renders the saved population label, fipCount and computedAt (spec 13 AC-4)', () => {
    const wrapper = mount(PopulationPicker, {
      props: {
        modelValue: emptyPopulationSpec(),
        savedLabel: 'All public FIPs',
        savedFipCount: 9412,
        savedComputedAt: '2026-09-11T10:00:00Z',
      },
      global: { plugins: [makeI18n()] },
    })
    expect(wrapper.text()).toContain('All public FIPs')
    expect(wrapper.text()).toContain('9412')
  })

  it('renders the withheld text, not "0", when the saved fipCount is null (k-anonymity, spec 13 §2.4)', () => {
    const wrapper = mount(PopulationPicker, {
      props: {
        modelValue: emptyPopulationSpec(),
        savedLabel: 'A small population',
        savedFipCount: null,
        savedComputedAt: '2026-09-11T10:00:00Z',
      },
      global: { plugins: [makeI18n()] },
    })
    expect(wrapper.text()).toContain(en.dashboard.home.fipCountWithheld)
    expect(wrapper.text()).not.toContain('0 FIPs')
  })

  it('calls savePopulation and emits "saved" on Save', async () => {
    savePopulationMock.mockResolvedValue({
      hash: 'abc123',
      label: 'My population',
      authScope: 'pub',
      fipCount: 40,
      createdAt: '2026-09-11T10:00:00Z',
      lastUsedAt: '2026-09-11T10:00:00Z',
    })
    const spec = { ...emptyPopulationSpec(), include: [{ kind: 'public' as const }] }
    const wrapper = mount(PopulationPicker, { props: { modelValue: spec }, global: { plugins: [makeI18n()] } })
    await wrapper.find('button.btn-primary').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(savePopulationMock).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('saved')).toBeTruthy()
  })
})
