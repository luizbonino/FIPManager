import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/en.json'
import DmpLinkList from './DmpLinkList.vue'
import type { RelatedDmp } from '@/types/api'

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function mountList(entries: RelatedDmp[], readOnly = false) {
  return mount(DmpLinkList, {
    props: { entries, readOnly },
    global: { plugins: [makeI18n()] },
  })
}

// Criterion 11 (docs/specs/06-dmp-linkage.md §5): filled FioDMP badge vs.
// outline "other" badge, and "Add" disabled once 10 entries are linked.
describe('DmpLinkList.vue', () => {
  it('renders a filled FioDMP badge for a FioDMP plan and an outline badge otherwise', () => {
    const entries: RelatedDmp[] = [
      { url: 'https://fiodmp.fiocruz.br/KQU5N0C', version: '13', system: 'FioDMP', dmpId: 'KQU5N0C' },
      { url: 'https://example.org/plan', version: null, system: 'other' },
    ]
    const wrapper = mountList(entries)
    const badges = wrapper.findAll('.dmp-system-badge')
    expect(badges).toHaveLength(2)

    expect(badges[0].classes()).toContain('badge-filled')
    expect(badges[0].classes()).not.toContain('badge-outline')
    expect(badges[0].text()).toBe(en.dmp.fiodmp)

    expect(badges[1].classes()).toContain('badge-outline')
    expect(badges[1].classes()).not.toContain('badge-filled')
    expect(badges[1].text()).toBe(en.dmp.other)
  })

  it('disables "Add a DMP link" once 10 plans are linked, and shows the max-reached hint', () => {
    const entries: RelatedDmp[] = Array.from({ length: 10 }, (_, i) => ({
      url: `https://example.org/plan-${i}`,
      system: 'other',
    }))
    const wrapper = mountList(entries)
    const addButton = wrapper.get('.dmp-add-btn')
    expect(addButton.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain(en.dmp.maxReached)
  })

  it('leaves "Add a DMP link" enabled under 10 plans', () => {
    const wrapper = mountList([{ url: 'https://example.org/plan', system: 'other' }])
    expect(wrapper.get('.dmp-add-btn').attributes('disabled')).toBeUndefined()
  })

  it('shows dmp.urlInvalid on blur for a non-https URL, without emitting an update', async () => {
    const wrapper = mountList([{ url: 'https://example.org/plan', system: 'other' }])
    const urlInput = wrapper.get('.dmp-field-url input')
    await urlInput.setValue('http://example.org/plan')
    await urlInput.trigger('blur')
    expect(wrapper.text()).toContain(en.dmp.urlInvalid)
    expect(wrapper.emitted('update')).toBeUndefined()
  })

  it('does not re-emit an invalid row when its version field changes, and excludes it from the emitted list', async () => {
    const wrapper = mountList([{ url: 'https://example.org/plan-a', version: null, system: 'other' }])
    const urlInput = wrapper.get('.dmp-field-url input')
    await urlInput.setValue('not-a-url')
    await urlInput.trigger('blur')
    expect(wrapper.text()).toContain(en.dmp.urlInvalid)
    expect(wrapper.emitted('update')).toBeUndefined()

    await wrapper.get('.dmp-field-version input').setValue('2')
    await wrapper.get('.dmp-field-version input').trigger('change')

    const emitted = wrapper.emitted('update')
    expect(emitted).toBeTruthy()
    const lastEmit = emitted![emitted!.length - 1][0] as RelatedDmp[]
    expect(lastEmit).toEqual([])
    // The invalid text and its error stay visible locally — nothing was reset.
    expect((urlInput.element as HTMLInputElement).value).toBe('not-a-url')
    expect(wrapper.text()).toContain(en.dmp.urlInvalid)
  })

  it('emits only the valid rows when a version field changes elsewhere in the list', async () => {
    const wrapper = mountList([
      { url: 'https://example.org/plan-a', version: null, system: 'other' },
      { url: 'https://example.org/plan-b', version: null, system: 'other' },
    ])
    const rows = wrapper.findAll('.dmp-row')
    await rows[0].get('.dmp-field-url input').setValue('not-a-url')
    await rows[0].get('.dmp-field-url input').trigger('blur')
    expect(wrapper.text()).toContain(en.dmp.urlInvalid)

    await rows[1].get('.dmp-field-version input').setValue('3')
    await rows[1].get('.dmp-field-version input').trigger('change')

    const emitted = wrapper.emitted('update')
    expect(emitted).toBeTruthy()
    const lastEmit = emitted![emitted!.length - 1][0] as RelatedDmp[]
    expect(lastEmit).toHaveLength(1)
    expect(lastEmit[0].url).toBe('https://example.org/plan-b')
    expect(lastEmit[0].version).toBe('3')
  })

  it('renders no rows and the "no plans" hint when entries is empty', () => {
    const wrapper = mountList([])
    expect(wrapper.findAll('.dmp-row')).toHaveLength(0)
    expect(wrapper.text()).toContain(en.dmp.none)
  })

  it('hides Add/Remove buttons when readOnly', () => {
    const wrapper = mountList([{ url: 'https://example.org/plan', system: 'other' }], true)
    expect(wrapper.find('.dmp-add-btn').exists()).toBe(false)
    expect(wrapper.find('.dmp-remove-btn').exists()).toBe(false)
  })
})
