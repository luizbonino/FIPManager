import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/en.json'
import KmSuggestedPhrases from './KmSuggestedPhrases.vue'
import type { SuggestedPhrase } from '@/types/api'

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function mountPhrases(phrases: SuggestedPhrase[], readOnly = false) {
  return mount(KmSuggestedPhrases, {
    props: { phrases, readOnly },
    global: { plugins: [makeI18n()] },
  })
}

// spec 08 §1.4/§1.5 extension: mirrors KmSuggestedFers.vue's add/remove/move
// UX for the model editor's "Suggested phrases" block.
describe('KmSuggestedPhrases.vue', () => {
  it('shows the counter against the 12 cap and disables "Add phrase" once reached', () => {
    const wrapper = mountPhrases(Array.from({ length: 12 }, (_, i) => ({ text: { en: `Phrase ${i}` } })))
    expect(wrapper.get('.suggested-count').text()).toBe('12/12')
    expect((wrapper.get('.btn-secondary').element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.find('.hint').exists()).toBe(true)
  })

  it('emits "add" when the button is clicked below the cap', async () => {
    const wrapper = mountPhrases([{ text: { en: 'A community wiki' } }])
    await wrapper.get('.btn-secondary').trigger('click')
    expect(wrapper.emitted('add')).toHaveLength(1)
  })

  it('emits "remove" with the phrase index', async () => {
    const wrapper = mountPhrases([{ text: { en: 'First' } }, { text: { en: 'Second' } }])
    const removeButtons = wrapper.findAll('.chip-remove')
    await removeButtons[1].trigger('click')
    expect(wrapper.emitted('remove')).toEqual([[1]])
  })

  it('emits "move" with the phrase index and direction', async () => {
    const wrapper = mountPhrases([{ text: { en: 'First' } }, { text: { en: 'Second' } }])
    const items = wrapper.findAll('.phrase-item')
    const upButtons = items[1].findAll('.move-btn')
    await upButtons[0].trigger('click') // the "up" button of the second row
    expect(wrapper.emitted('move')).toEqual([[1, 'up']])
  })

  it('emits "updateText" with the phrase index, language and value from KmLangTabs', async () => {
    const wrapper = mountPhrases([{ text: { en: 'A community wiki' } }])
    const input = wrapper.get('.phrase-item .lang-input')
    await input.setValue('An updated wiki') // setValue itself triggers `change`, which KmLangTabs listens on
    expect(wrapper.emitted('updateText')).toEqual([[0, 'en', 'An updated wiki']])
  })

  it('disables move/remove controls when readOnly', () => {
    const wrapper = mountPhrases([{ text: { en: 'First' } }], true)
    const upButton = wrapper.get('.move-btn')
    expect((upButton.element as HTMLButtonElement).disabled).toBe(true)
    expect((wrapper.get('.chip-remove').element as HTMLButtonElement).disabled).toBe(true)
    expect((wrapper.get('.btn-secondary').element as HTMLButtonElement).disabled).toBe(true)
  })
})
