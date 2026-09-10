import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/en.json'
import { useFipEditorStore } from '@/stores/fipEditor'
import { setToken } from '@/lib/editTokens'
import QuestionCard from './QuestionCard.vue'
import type { FipOut, KnowledgeModelOut, KnowledgeModelQuestion } from '@/types/api'

function makeI18n(locale = 'en') {
  return createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { en, 'pt-BR': en } })
}

function makeFip(overrides: Partial<FipOut> = {}): FipOut {
  return {
    id: 'fip-1',
    ownerId: null,
    sessionId: null,
    visibility: 'link',
    questionnaireId: 'confoa-2026-area',
    questionnaireVersion: '1.0.0',
    title: 'Test community',
    community: { name: 'Test community', links: [] },
    relatedDmps: [],
    answers: [],
    language: 'en',
    license: 'CC0-1.0',
    createdAt: '2026-09-08T00:00:00Z',
    updatedAt: '2026-09-08T00:00:00Z',
    ...overrides,
  }
}

function makeQuestion(overrides: Partial<KnowledgeModelQuestion> = {}): KnowledgeModelQuestion {
  return {
    id: 'F1-metadata',
    principle: 'F1',
    scope: 'metadata',
    text: { en: 'How do you make your metadata findable?' },
    help: null,
    ferType: 'identifier-service',
    required: false,
    allowMultiple: true,
    suggestedFerIds: ['https://www.doi.org/', 'https://www.handle.net/'],
    ...overrides,
  }
}

function makeKm(question: KnowledgeModelQuestion, opts: { defaultDeclarationStatus?: string } = {}): KnowledgeModelOut {
  return {
    id: 'confoa-2026-area',
    version: '1.0.0',
    status: 'published',
    visibility: 'public',
    license: 'CC0-1.0',
    source: 'test',
    title: { en: 'Area' },
    description: { en: '' },
    changelog: [],
    content: {
      id: 'confoa-2026-area',
      version: '1.0.0',
      status: 'published',
      license: 'CC0-1.0',
      title: { en: 'Area' },
      description: { en: '' },
      changelog: [],
      sections: [{ id: 'F', title: { en: 'Findable' }, questions: [question] }],
      defaultDeclarationStatus: opts.defaultDeclarationStatus as never,
    },
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
  }
}

function mountCard(
  question: KnowledgeModelQuestion,
  fip: FipOut,
  kmOpts: { defaultDeclarationStatus?: string } = {},
  locale = 'en'
) {
  const pinia = createPinia()
  setActivePinia(pinia)
  setToken(fip.id, 'test-edit-token')
  const store = useFipEditorStore()
  store.setFip(fip)
  store.km = makeKm(question, kmOpts)
  store.fers = {
    'https://www.doi.org/': { id: 'https://www.doi.org/', label: { en: 'DOI' }, type: 'identifier-service', homepage: null, source: 'seed' },
    'https://www.handle.net/': { id: 'https://www.handle.net/', label: { en: 'Handle' }, type: 'identifier-service', homepage: null, source: 'seed' },
  }

  const wrapper = mount(QuestionCard, {
    props: { question, ferTypeLabel: null },
    global: { plugins: [pinia, makeI18n(locale)] },
  })
  return { wrapper, store }
}

// Criterion 16 (docs/specs/08-workshop-picklists.md §6): QuestionCard.vue
// adds a declaration with the model's defaultDeclarationStatus on check and
// confirms before dropping an annotated one; the N/A toggle clears
// declarations and hides the declaration rows while it is on.
describe('QuestionCard.vue — suggested quick-pick and Not applicable (spec 08 §1.5/§2.2)', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders a virtual first declaration row with the quick-pick when there are no declarations yet', () => {
    const { wrapper } = mountCard(makeQuestion(), makeFip())
    expect(wrapper.find('.suggested-fieldset').exists()).toBe(true)
    // spec 08 §1.5 extension: a built-in "Other" checkbox always sits after
    // the two FER suggestions.
    expect(wrapper.findAll('.suggested-option:not(.other-option) input[type="checkbox"]')).toHaveLength(2)
  })

  it('ticking a suggestion adds a declaration with the model default status', async () => {
    const { wrapper, store } = mountCard(makeQuestion(), makeFip(), { defaultDeclarationStatus: 'planned' })
    const checkbox = wrapper.get('.suggested-fieldset input[type="checkbox"]')
    await checkbox.setValue(true)

    const declarations = store.fip?.answers.find((a) => a.questionId === 'F1-metadata')?.declarations ?? []
    expect(declarations).toHaveLength(1)
    expect(declarations[0]).toMatchObject({ ferId: 'https://www.doi.org/', status: 'planned' })
  })

  it('a redundant checked=true change event does not duplicate the declaration', async () => {
    const { wrapper, store } = mountCard(makeQuestion(), makeFip())
    const checkbox = wrapper.get('.suggested-fieldset input[type="checkbox"]')
    await checkbox.setValue(true)
    await checkbox.setValue(true) // e.g. a stray second change event for the already-checked box
    const declarations = store.fip?.answers.find((a) => a.questionId === 'F1-metadata')?.declarations ?? []
    expect(declarations).toHaveLength(1)
  })

  it('unticking an unannotated, default-status declaration removes it without confirming', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm')
    const fip = makeFip({
      answers: [{ questionId: 'F1-metadata', declarations: [{ ferId: 'https://www.doi.org/', status: 'current' }] }],
    })
    const { wrapper, store } = mountCard(makeQuestion(), fip)
    const checkbox = wrapper.get('.suggested-fieldset input[type="checkbox"]')
    expect((checkbox.element as HTMLInputElement).checked).toBe(true)

    await checkbox.setValue(false)

    expect(confirmSpy).not.toHaveBeenCalled()
    const declarations = store.fip?.answers.find((a) => a.questionId === 'F1-metadata')?.declarations ?? []
    expect(declarations).toHaveLength(0)
  })

  it('unticking an annotated declaration (a note) confirms first; cancelling keeps it', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const fip = makeFip({
      answers: [
        {
          questionId: 'F1-metadata',
          declarations: [{ ferId: 'https://www.doi.org/', status: 'current', note: { en: 'Because it is standard' } }],
        },
      ],
    })
    const { wrapper, store } = mountCard(makeQuestion(), fip)
    const checkbox = wrapper.get('.suggested-fieldset input[type="checkbox"]')

    await checkbox.setValue(false)

    expect(confirmSpy).toHaveBeenCalledWith(en.editor.dropAnnotatedDeclaration)
    const declarations = store.fip?.answers.find((a) => a.questionId === 'F1-metadata')?.declarations ?? []
    expect(declarations).toHaveLength(1) // not removed
  })

  it('unticking an annotated declaration removes it once confirmed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const fip = makeFip({
      answers: [
        {
          questionId: 'F1-metadata',
          declarations: [{ ferId: 'https://www.doi.org/', status: 'planned-development' }], // non-default status
        },
      ],
    })
    const { wrapper, store } = mountCard(makeQuestion(), fip)
    const checkbox = wrapper.get('.suggested-fieldset input[type="checkbox"]')

    await checkbox.setValue(false)

    const declarations = store.fip?.answers.find((a) => a.questionId === 'F1-metadata')?.declarations ?? []
    expect(declarations).toHaveLength(0)
  })

  it('turning Not applicable on with declarations present confirms, then clears them and hides the rows', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const fip = makeFip({
      answers: [{ questionId: 'F1-metadata', declarations: [{ ferId: 'https://www.doi.org/', status: 'current' }] }],
    })
    const { wrapper, store } = mountCard(makeQuestion(), fip)
    const naToggle = wrapper.get('.na-toggle input')
    await naToggle.setValue(true)

    expect(window.confirm).toHaveBeenCalledWith(en.editor.notApplicableConfirm)
    const answer = store.fip?.answers.find((a) => a.questionId === 'F1-metadata')
    expect(answer?.notApplicable).toBe(true)
    expect(answer?.declarations).toEqual([])
    expect(wrapper.find('.declarations').exists()).toBe(false)
    expect(wrapper.find('.add-declaration-btn').exists()).toBe(false)
  })

  it('cancelling the confirm leaves Not applicable off and declarations untouched', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const fip = makeFip({
      answers: [{ questionId: 'F1-metadata', declarations: [{ ferId: 'https://www.doi.org/', status: 'current' }] }],
    })
    const { wrapper, store } = mountCard(makeQuestion(), fip)
    const naToggle = wrapper.get('.na-toggle input')
    await naToggle.setValue(true)

    const answer = store.fip?.answers.find((a) => a.questionId === 'F1-metadata')
    expect(answer?.notApplicable ?? false).toBe(false)
    expect(answer?.declarations).toHaveLength(1)
  })

  it('turning Not applicable on with no declarations needs no confirm', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm')
    const { wrapper, store } = mountCard(makeQuestion(), makeFip())
    const naToggle = wrapper.get('.na-toggle input')
    await naToggle.setValue(true)

    expect(confirmSpy).not.toHaveBeenCalled()
    const answer = store.fip?.answers.find((a) => a.questionId === 'F1-metadata')
    expect(answer?.notApplicable).toBe(true)
  })

  it('hides the free-text toggle on the quick-pick picker when allowFreeText is false', () => {
    const { wrapper } = mountCard(makeQuestion({ allowFreeText: false }), makeFip())
    expect(wrapper.find('.toggle-mode').exists()).toBe(false)
  })
})

// spec 08 §1.5 extension: suggestedPhrases quick-pick and the built-in
// "Other" free-text checkbox, siblings of the suggested-FER quick-pick.
describe('QuestionCard.vue — suggested phrases and "Other" (spec 10)', () => {
  function makePhraseQuestion(overrides: Partial<KnowledgeModelQuestion> = {}) {
    return makeQuestion({
      suggestedFerIds: [],
      suggestedPhrases: [{ text: { en: 'A community wiki' } }, { text: { en: 'An institutional repository' } }],
      ...overrides,
    })
  }

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders one checkbox per suggested phrase inside the quick-pick fieldset', () => {
    const { wrapper } = mountCard(makePhraseQuestion(), makeFip())
    const labels = wrapper.findAll('.suggested-fieldset .suggested-option-label').map((l) => l.text())
    expect(labels).toContain('A community wiki')
    expect(labels).toContain('An institutional repository')
  })

  it('ticking a phrase adds a free-text declaration with the model default status', async () => {
    const { wrapper, store } = mountCard(makePhraseQuestion(), makeFip(), { defaultDeclarationStatus: 'planned' })
    const checkboxes = wrapper.findAll('.suggested-fieldset input[type="checkbox"]')
    // First phrase checkbox (after any FER checkboxes, of which there are none here).
    await checkboxes[0].setValue(true)

    const declarations = store.fip?.answers.find((a) => a.questionId === 'F1-metadata')?.declarations ?? []
    expect(declarations).toHaveLength(1)
    expect(declarations[0]).toMatchObject({ ferId: null, ferFreeText: 'A community wiki', status: 'planned' })
  })

  it('unticking a phrase removes the matching declaration', async () => {
    const fip = makeFip({
      answers: [{ questionId: 'F1-metadata', declarations: [{ ferFreeText: 'A community wiki', status: 'current' }] }],
    })
    const { wrapper, store } = mountCard(makePhraseQuestion(), fip)
    const checkbox = wrapper.findAll('.suggested-fieldset input[type="checkbox"]')[0]
    expect((checkbox.element as HTMLInputElement).checked).toBe(true)

    await checkbox.setValue(false)

    const declarations = store.fip?.answers.find((a) => a.questionId === 'F1-metadata')?.declarations ?? []
    expect(declarations).toHaveLength(0)
  })

  it('checked state recognises a pt-PT-only phrase variant when the editor locale is pt-BR', () => {
    const fip = makeFip({
      answers: [{ questionId: 'F1-metadata', declarations: [{ ferFreeText: 'Um wiki comunitário', status: 'current' }] }],
    })
    const question = makePhraseQuestion({ suggestedPhrases: [{ text: { 'pt-PT': 'Um wiki comunitário' } }] })
    const { wrapper } = mountCard(question, fip, {}, 'pt-BR')
    const checkbox = wrapper.get('.suggested-fieldset input[type="checkbox"]')
    expect((checkbox.element as HTMLInputElement).checked).toBe(true)
  })

  // spec 10 §2: the stored declaration text follows the FIP's own
  // `language`, not whatever the editor's UI is currently displaying —
  // a participant may browse in one language while the FIP is recorded in
  // another.
  it('ticking a phrase resolves text in the FIP\'s own language, not the editor UI locale', async () => {
    const question = makePhraseQuestion({
      suggestedPhrases: [{ text: { en: 'A community wiki', 'pt-BR': 'Um wiki comunitário' } }],
    })
    const { wrapper, store } = mountCard(question, makeFip({ language: 'pt-BR' }), {}, 'en')
    const checkbox = wrapper.get('.suggested-fieldset input[type="checkbox"]')
    await checkbox.setValue(true)

    const declarations = store.fip?.answers.find((a) => a.questionId === 'F1-metadata')?.declarations ?? []
    expect(declarations[0]).toMatchObject({ ferFreeText: 'Um wiki comunitário' })
  })

  it('unticking an annotated phrase declaration (a note) confirms first; cancelling keeps it', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const fip = makeFip({
      answers: [
        {
          questionId: 'F1-metadata',
          declarations: [{ ferFreeText: 'A community wiki', status: 'current', note: { en: 'We maintain this' } }],
        },
      ],
    })
    const { wrapper, store } = mountCard(makePhraseQuestion(), fip)
    const checkbox = wrapper.findAll('.suggested-fieldset input[type="checkbox"]')[0]

    await checkbox.setValue(false)

    expect(confirmSpy).toHaveBeenCalledWith(en.editor.dropAnnotatedDeclaration)
    const declarations = store.fip?.answers.find((a) => a.questionId === 'F1-metadata')?.declarations ?? []
    expect(declarations).toHaveLength(1) // not removed
  })

  it('unticking an annotated phrase declaration removes it once confirmed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const fip = makeFip({
      answers: [
        { questionId: 'F1-metadata', declarations: [{ ferFreeText: 'A community wiki', status: 'planned-development' }] },
      ],
    })
    const { wrapper, store } = mountCard(makePhraseQuestion(), fip)
    const checkbox = wrapper.findAll('.suggested-fieldset input[type="checkbox"]')[0]

    await checkbox.setValue(false)

    const declarations = store.fip?.answers.find((a) => a.questionId === 'F1-metadata')?.declarations ?? []
    expect(declarations).toHaveLength(0)
  })

  it('the "Other" checkbox reveals an input; typing text and pressing Enter adds a declaration and clears/unticks the box', async () => {
    const { wrapper, store } = mountCard(makePhraseQuestion(), makeFip())
    const otherCheckbox = wrapper.get('.other-option input[type="checkbox"]')
    await otherCheckbox.setValue(true)

    const input = wrapper.get('.other-input-row input[type="text"]')
    await input.setValue('A custom vocabulary we use')
    await input.trigger('keydown.enter')

    const declarations = store.fip?.answers.find((a) => a.questionId === 'F1-metadata')?.declarations ?? []
    expect(declarations).toHaveLength(1)
    expect(declarations[0]).toMatchObject({ ferId: null, ferFreeText: 'A custom vocabulary we use', status: 'current' })
    expect(wrapper.find('.other-input-row').exists()).toBe(false)
    expect((otherCheckbox.element as HTMLInputElement).checked).toBe(false)
  })

  it('blurring the "Other" input while empty just unticks the box, with no declaration added', async () => {
    const { wrapper, store } = mountCard(makePhraseQuestion(), makeFip())
    const otherCheckbox = wrapper.get('.other-option input[type="checkbox"]')
    await otherCheckbox.setValue(true)
    const input = wrapper.get('.other-input-row input[type="text"]')
    await input.trigger('blur')

    const declarations = store.fip?.answers.find((a) => a.questionId === 'F1-metadata')?.declarations ?? []
    expect(declarations).toHaveLength(0)
    expect(wrapper.find('.other-input-row').exists()).toBe(false)
  })

  // Bug fix (browser report): the PATCH succeeded and the declaration
  // persisted (visible after a reload), but the row didn't visibly update
  // in place -- the picker fell back to the empty catalogue-search view
  // with nothing ticked, because it reused the *same* FerPicker instance
  // that was mounted for the virtual empty placeholder row (index 0,
  // spec 08 §1.5's `displayRows`) and never re-derived its local
  // catalogue/free-text `mode` from the now-populated `ferFreeText` prop.
  // This asserts the declaration is visible *without* remounting the
  // wrapper (a `mount()`-per-case bug wouldn't have caught the original
  // report, which was specifically about an in-place update).
  it('adding "Other" text makes the declaration visible in place, without remounting', async () => {
    const { wrapper, store } = mountCard(makePhraseQuestion(), makeFip())

    // Starts as the virtual placeholder: no declarations yet, and the
    // picker mounted in catalogue mode (no free-text value to show).
    expect(store.fip?.answers.find((a) => a.questionId === 'F1-metadata')?.declarations ?? []).toHaveLength(0)
    expect(wrapper.find('.free-text-mode').exists()).toBe(false)

    const otherCheckbox = wrapper.get('.other-option input[type="checkbox"]')
    await otherCheckbox.setValue(true)
    const input = wrapper.get('.other-input-row input[type="text"]')
    await input.setValue('Planilha compartilhada no Drive')
    await input.trigger('keydown.enter')

    // The store did update...
    const declarations = store.fip?.answers.find((a) => a.questionId === 'F1-metadata')?.declarations ?? []
    expect(declarations).toHaveLength(1)
    expect(declarations[0]).toMatchObject({ ferId: null, ferFreeText: 'Planilha compartilhada no Drive' })

    // ...and, without remounting, the same picker now renders that text in
    // its free-text input rather than an empty catalogue search box.
    expect(wrapper.find('.catalogue-mode').exists()).toBe(false)
    const freeTextInput = wrapper.get('.free-text-mode input')
    expect((freeTextInput.element as HTMLInputElement).value).toBe('Planilha compartilhada no Drive')
  })
})
