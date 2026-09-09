import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/en.json'
import FerPicker from './FerPicker.vue'
import type { FerOut } from '@/types/api'

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

const suggested: FerOut[] = [
  { id: 'https://www.doi.org/', label: { en: 'DOI' }, type: 'identifier-service', homepage: 'https://www.doi.org', source: 'seed' },
  { id: 'https://www.handle.net/', label: { en: 'Handle' }, type: 'identifier-service', homepage: null, source: 'seed' },
]

function mountPicker(props: Partial<InstanceType<typeof FerPicker>['$props']> = {}) {
  return mount(FerPicker, {
    props: {
      options: [],
      ferId: null,
      ferFreeText: null,
      ...props,
    },
    global: { plugins: [makeI18n()] },
  })
}

// Criterion 16 (docs/specs/08-workshop-picklists.md §6): FerPicker renders a
// checkbox per suggestion above the search box, emits toggleSuggested, and
// hides the free-text toggle when allowFreeText: false.
describe('FerPicker.vue — suggested quick-pick (spec 08 §1.5)', () => {
  it('renders no fieldset when showSuggested is false, even with suggestions present', () => {
    const wrapper = mountPicker({ suggested, showSuggested: false })
    expect(wrapper.find('.suggested-fieldset').exists()).toBe(false)
  })

  it('renders no fieldset when suggested is empty, even with showSuggested true', () => {
    const wrapper = mountPicker({ suggested: [], showSuggested: true })
    expect(wrapper.find('.suggested-fieldset').exists()).toBe(false)
  })

  it('renders one checkbox per suggestion, above the search box, with legend editor.suggestedOptions', () => {
    const wrapper = mountPicker({ suggested, showSuggested: true })
    const fieldset = wrapper.get('.suggested-fieldset')
    expect(fieldset.get('legend').text()).toBe(en.editor.suggestedOptions)
    const checkboxes = fieldset.findAll('input[type="checkbox"]')
    expect(checkboxes).toHaveLength(2)
    expect(fieldset.text()).toContain('DOI')
    expect(fieldset.text()).toContain('Handle')
    expect(fieldset.text()).toContain('https://www.doi.org') // homepage on a second line

    const allElements = wrapper.element.querySelectorAll('*')
    const fieldsetIndex = Array.from(allElements).indexOf(fieldset.element)
    const searchInput = wrapper.find('.fer-input')
    const searchIndex = Array.from(allElements).indexOf(searchInput.element)
    expect(fieldsetIndex).toBeLessThan(searchIndex)
  })

  it('emits toggleSuggested(ferId, checked) when a checkbox is ticked, and reflects checkedFerIds', () => {
    const wrapper = mountPicker({ suggested, showSuggested: true, checkedFerIds: ['https://www.handle.net/'] })
    const checkboxes = wrapper.findAll('.suggested-fieldset input[type="checkbox"]')
    expect((checkboxes[0].element as HTMLInputElement).checked).toBe(false)
    expect((checkboxes[1].element as HTMLInputElement).checked).toBe(true)
  })

  it('emits toggleSuggested true on check and false on uncheck', async () => {
    const wrapper = mountPicker({ suggested, showSuggested: true })
    const checkboxes = wrapper.findAll('.suggested-fieldset input[type="checkbox"]')
    await checkboxes[0].setValue(true)
    expect(wrapper.emitted('toggleSuggested')?.[0]).toEqual(['https://www.doi.org/', true])

    await checkboxes[0].setValue(false)
    expect(wrapper.emitted('toggleSuggested')?.[1]).toEqual(['https://www.doi.org/', false])
  })

  it('hides the "Use my own wording" toggle when allowFreeText is false', () => {
    const shown = mountPicker({ allowFreeText: true })
    expect(shown.find('.toggle-mode').exists()).toBe(true)

    const hidden = mountPicker({ allowFreeText: false })
    expect(hidden.find('.toggle-mode').exists()).toBe(false)
    // Pinned to catalogue mode — never silently in free-text mode with no way back.
    expect(hidden.find('.catalogue-mode').exists()).toBe(true)
  })

  it('disables the checkboxes when disabled is true', () => {
    const wrapper = mountPicker({ suggested, showSuggested: true, disabled: true })
    const checkboxes = wrapper.findAll('.suggested-fieldset input[type="checkbox"]')
    checkboxes.forEach((cb) => expect((cb.element as HTMLInputElement).disabled).toBe(true))
  })
})
