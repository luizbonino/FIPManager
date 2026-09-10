import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/en.json'
import { useKmEditorStore } from '@/stores/kmEditor'
import { validateContent } from '@/lib/kmContent'
import KmSectionList from './KmSectionList.vue'
import type { KnowledgeModelContent } from '@/types/api'

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function makeContent(): KnowledgeModelContent {
  return {
    id: 'model-1',
    version: '1.0.0',
    status: 'draft',
    license: 'CC0-1.0',
    title: { en: 'Model' },
    description: { en: '' },
    changelog: [],
    sections: [
      {
        id: 'A',
        title: { en: 'Section A' },
        questions: [
          {
            id: 'Q1',
            principle: null,
            scope: null,
            text: { en: 'Question 1' },
            help: null,
            ferType: null,
            required: false,
            allowMultiple: true,
          },
        ],
      },
      { id: 'B', title: { en: 'Section B' }, questions: [] },
    ],
  }
}

function mountList(content: KnowledgeModelContent) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useKmEditorStore()
  store.content = content

  const wrapper = mount(KmSectionList, {
    props: { sections: content.sections, ferTypeOptions: [], readOnly: false },
    global: { plugins: [pinia, makeI18n()] },
  })
  return { wrapper, store }
}

// Bug: the section delete button/confirm reused the question's i18n keys
// (`km.deleteQuestion`/`km.deleteModelConfirm`) instead of dedicated
// `km.deleteSection`/`km.deleteSectionConfirm` copy.
describe('KmSectionList.vue', () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let confirmSpy: any

  beforeEach(() => {
    confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  afterEach(() => {
    confirmSpy.mockRestore()
  })

  it('the section delete button reads "Delete section", not "Delete question"', () => {
    const { wrapper } = mountList(makeContent())
    const deleteButtons = wrapper.findAll('.summary-actions .ghost-btn.danger')
    expect(deleteButtons).toHaveLength(2)
    expect(deleteButtons[0].text()).toBe(en.km.deleteSection)
    expect(deleteButtons[0].text()).not.toBe(en.km.deleteQuestion)
  })

  it('confirms with the section-specific message and removes the section from store.content on confirm', async () => {
    const { wrapper, store } = mountList(makeContent())
    const deleteButtons = wrapper.findAll('.summary-actions .ghost-btn.danger')

    await deleteButtons[0].trigger('click')

    expect(confirmSpy).toHaveBeenCalledWith(en.km.deleteSectionConfirm)
    expect(store.content?.sections.map((s) => s.id)).toEqual(['B'])
  })
})

// Bug fix: "Add phrase" used to call `addSuggestedPhrase(c, question.id, {})`
// -- an empty LangMap the backend rejects with 400 `missing_key`, so the
// autosave that followed always landed in `saveError`. A freshly added
// phrase must be immediately valid: seeded with the editor's current
// language (`km.newPhrase`), never an empty object.
describe('KmSectionList.vue — "Add phrase" (spec 10 §1/§2)', () => {
  it('seeds a new phrase with { [locale]: t("km.newPhrase") }, never an empty LangMap', async () => {
    const { wrapper, store } = mountList(makeContent())

    const addPhraseButton = wrapper.findAll('button').find((b) => b.text() === en.km.addPhrase)
    expect(addPhraseButton).toBeTruthy()
    await addPhraseButton!.trigger('click')

    const question = store.content?.sections[0].questions[0]
    expect(question?.suggestedPhrases).toEqual([{ text: { en: en.km.newPhrase } }])
  })

  it('a freshly added phrase validates cleanly (no missing_key / empty_string on suggestedPhrases)', async () => {
    const { wrapper, store } = mountList(makeContent())

    const addPhraseButton = wrapper.findAll('button').find((b) => b.text() === en.km.addPhrase)
    await addPhraseButton!.trigger('click')

    const errors = validateContent(store.content!, [])
    expect(errors.filter((e) => e.path.includes('suggestedPhrases'))).toEqual([])
  })
})
