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
    // spec 08 §1.5 extension: a built-in "Other" checkbox always sits after
    // the suggestion checkboxes, so scope this count to the FER suggestions.
    const checkboxes = fieldset.findAll('input[type="checkbox"]')
    expect(checkboxes).toHaveLength(3)
    const ferCheckboxes = fieldset.findAll('.suggested-option:not(.other-option) input[type="checkbox"]')
    expect(ferCheckboxes).toHaveLength(2)
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

// spec 08 §1.5 extension: suggestedPhrases quick-pick and the built-in
// "Other" free-text checkbox, siblings of the FER quick-pick above.
describe('FerPicker.vue — suggested phrases and "Other" (spec 08 §1.5 extension)', () => {
  const phrases = [{ text: { en: 'A community wiki' } }, { text: { en: 'An institutional repository' } }]

  it('renders no fieldset when suggested and suggestedPhrases are both empty, even with showSuggested true', () => {
    const wrapper = mountPicker({ showSuggested: true })
    expect(wrapper.find('.suggested-fieldset').exists()).toBe(false)
  })

  it('renders the fieldset (and the "Other" checkbox) from suggestedPhrases alone, with no FER suggestions', () => {
    const wrapper = mountPicker({ suggestedPhrases: phrases, showSuggested: true })
    const fieldset = wrapper.get('.suggested-fieldset')
    expect(fieldset.text()).toContain('A community wiki')
    expect(fieldset.text()).toContain('An institutional repository')
    expect(fieldset.text()).toContain(en.fip.otherOption)
  })

  it('emits togglePhrase(index, checked) and reflects checkedPhraseIndexes', () => {
    const wrapper = mountPicker({ suggestedPhrases: phrases, showSuggested: true, checkedPhraseIndexes: [1] })
    const phraseCheckboxes = wrapper.findAll('.suggested-option:not(.other-option) input[type="checkbox"]')
    expect((phraseCheckboxes[0].element as HTMLInputElement).checked).toBe(false)
    expect((phraseCheckboxes[1].element as HTMLInputElement).checked).toBe(true)
  })

  it('ticking the "Other" checkbox reveals an input; the add button emits addOther and both re-hide', async () => {
    const wrapper = mountPicker({ suggestedPhrases: phrases, showSuggested: true })
    expect(wrapper.find('.other-input-row').exists()).toBe(false)

    const otherCheckbox = wrapper.get('.other-option input[type="checkbox"]')
    await otherCheckbox.setValue(true)
    expect(wrapper.find('.other-input-row').exists()).toBe(true)

    await wrapper.get('.other-input-row input[type="text"]').setValue('A custom vocabulary')
    await wrapper.get('.other-add-btn').trigger('click')

    expect(wrapper.emitted('addOther')).toEqual([['A custom vocabulary']])
    expect(wrapper.find('.other-input-row').exists()).toBe(false)
    expect((otherCheckbox.element as HTMLInputElement).checked).toBe(false)
  })

  it('the "Other" add button is disabled while the input is empty', async () => {
    const wrapper = mountPicker({ suggestedPhrases: phrases, showSuggested: true })
    await wrapper.get('.other-option input[type="checkbox"]').setValue(true)
    expect((wrapper.get('.other-add-btn').element as HTMLButtonElement).disabled).toBe(true)
  })

  // Bug fix: `let uid = 0` used to live inside `<script setup>`, which
  // re-runs on every component instance, so every mounted FerPicker handed
  // out `#fer-picker-1` again -- two pickers on screen at once (a question
  // with both a FER type and suggested phrases renders more than one, spec
  // 10 §2) collided on the same input id, breaking the <label for>
  // association for both. `uid` now lives in a module-scope `<script>`
  // block, incrementing once per instance across the whole module.
  it('gives two mounted pickers distinct ids for the search input', () => {
    const wrapper1 = mountPicker({})
    const wrapper2 = mountPicker({})
    const id1 = wrapper1.get('.fer-input').attributes('id')
    const id2 = wrapper2.get('.fer-input').attributes('id')
    expect(id1).toBeTruthy()
    expect(id2).toBeTruthy()
    expect(id1).not.toBe(id2)
  })

  it('gives two mounted pickers distinct ids for the "Other" free-text input', async () => {
    const wrapper1 = mountPicker({ suggestedPhrases: phrases, showSuggested: true })
    const wrapper2 = mountPicker({ suggestedPhrases: phrases, showSuggested: true })

    await wrapper1.get('.other-option input[type="checkbox"]').setValue(true)
    await wrapper2.get('.other-option input[type="checkbox"]').setValue(true)

    const otherId1 = wrapper1.get('.other-input-row input[type="text"]').attributes('id')
    const otherId2 = wrapper2.get('.other-input-row input[type="text"]').attributes('id')
    expect(otherId1).toBeTruthy()
    expect(otherId2).toBeTruthy()
    expect(otherId1).not.toBe(otherId2)
  })
})
