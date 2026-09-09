import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/en.json'
import { useFipEditorStore } from '@/stores/fipEditor'
import { setToken } from '@/lib/editTokens'
import QuestionCard from './QuestionCard.vue'
import type { FipOut, KnowledgeModelOut, KnowledgeModelQuestion } from '@/types/api'

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
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

function mountCard(question: KnowledgeModelQuestion, fip: FipOut, kmOpts: { defaultDeclarationStatus?: string } = {}) {
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
    global: { plugins: [pinia, makeI18n()] },
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
    expect(wrapper.findAll('.suggested-fieldset input[type="checkbox"]')).toHaveLength(2)
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
