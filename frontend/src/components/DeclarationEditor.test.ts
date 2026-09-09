import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/en.json'
import { useFipEditorStore } from '@/stores/fipEditor'
import { setToken } from '@/lib/editTokens'
import DeclarationEditor from './DeclarationEditor.vue'
import type { Declaration, FipOut } from '@/types/api'

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function makeFip(overrides: Partial<FipOut> = {}): FipOut {
  return {
    id: 'fip-1',
    ownerId: null,
    sessionId: null,
    visibility: 'link',
    questionnaireId: 'gofair-fip-mini',
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

function mountEditor(fip: FipOut, declaration: Declaration = { status: 'current' }) {
  const pinia = createPinia()
  setActivePinia(pinia)
  setToken(fip.id, 'test-edit-token')
  const store = useFipEditorStore()
  // In real usage the `declaration` prop always comes from the store itself
  // (QuestionCard iterates `store.fip.answers[...].declarations`), so the
  // store is seeded with the same declaration here too — otherwise
  // `store.setDeclaration` would merge onto a freshly-defaulted `{status:
  // 'current'}` base instead of the one the component was mounted with.
  const seeded: FipOut = {
    ...fip,
    answers: fip.answers.length > 0 ? fip.answers : [{ questionId: 'F1-metadata', declarations: [declaration], comment: null }],
  }
  store.setFip(seeded)

  const wrapper = mount(DeclarationEditor, {
    props: { questionId: 'F1-metadata', index: 0, declaration, options: [] },
    global: { plugins: [pinia, makeI18n()] },
  })
  return { wrapper, store }
}

// Criterion 11 (docs/specs/06-dmp-linkage.md §5): the evidence panel exists
// only once >= 1 DMP is linked to the FIP.
describe('DeclarationEditor.vue — DMP evidence', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('renders no dmp.evidence block when relatedDmps is empty', () => {
    const { wrapper } = mountEditor(makeFip({ relatedDmps: [] }))
    expect(wrapper.find('.evidence').exists()).toBe(false)
    expect(wrapper.text()).not.toContain(en.dmp.evidence)
  })

  it('renders the dmp.evidence panel with a plan <select> holding one option once a plan is linked', () => {
    const { wrapper } = mountEditor(
      makeFip({
        relatedDmps: [{ url: 'https://fiodmp.fiocruz.br/KQU5N0C', version: '13', system: 'FioDMP', dmpId: 'KQU5N0C' }],
      })
    )
    const evidence = wrapper.get('.evidence')
    expect(evidence.get('summary').text()).toBe(en.dmp.evidence)

    const select = evidence.get('.evidence-field select')
    // One blank placeholder option + one plan option.
    expect(select.findAll('option')).toHaveLength(2)
    expect(select.findAll('option')[1].text()).toBe('KQU5N0C v13')
  })

  it('selecting a plan writes dmpEvidence via the store and reveals section/questionRef fields', async () => {
    const { wrapper, store } = mountEditor(
      makeFip({ relatedDmps: [{ url: 'https://example.org/plan', system: 'other' }] })
    )
    const planSelect = wrapper.get('.evidence-field select')
    await planSelect.setValue('0')

    expect(store.fip?.answers[0]?.declarations[0]?.dmpEvidence).toEqual({
      dmpIndex: 0,
      section: null,
      questionRef: null,
    })
  })
})

// Criterion 17 (docs/specs/05-v1-completion.md §8): the second FerPicker
// exists only while status is planned-replacement, and both successor
// fields are cleared the moment the status changes away from it.
describe('DeclarationEditor.vue — successor FER', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('renders no second picker for a current declaration', () => {
    const { wrapper } = mountEditor(makeFip(), { status: 'current' })
    expect(wrapper.find('.successor-row').exists()).toBe(false)
    expect(wrapper.text()).not.toContain(en.editor.successor)
  })

  it('renders the second picker, labelled editor.successor, only for planned-replacement', () => {
    const { wrapper } = mountEditor(makeFip(), { status: 'planned-replacement' })
    const successorRow = wrapper.get('.successor-row')
    expect(successorRow.text()).toContain(en.editor.successor)
    expect(successorRow.text()).toContain(en.editor.successorHint)
  })

  it('writes successorFerId/successorFreeText via the store when the second picker changes', async () => {
    const { wrapper, store } = mountEditor(makeFip(), { status: 'planned-replacement' })
    const successorRow = wrapper.get('.successor-row')
    // No catalogue options in this fixture — switch the picker to free text first.
    await successorRow.get('.toggle-mode').trigger('click')
    await successorRow.get('.fer-input').setValue('Our own registry')

    expect(store.fip?.answers[0]?.declarations[0]?.successorFreeText).toBe('Our own registry')
    expect(store.fip?.answers[0]?.declarations[0]?.successorFerId).toBeNull()
  })

  // The `declaration` prop always comes from the store in real usage
  // (QuestionCard re-renders it from `store.fip.answers`), so this checks
  // the picker's own reactive show/hide the same way a parent update would
  // drive it — a fresh `declaration` prop with a different status.
  it('hides the second picker once the declaration prop is no longer planned-replacement', async () => {
    const { wrapper } = mountEditor(makeFip(), { status: 'planned-replacement' })
    expect(wrapper.find('.successor-row').exists()).toBe(true)

    await wrapper.setProps({ declaration: { status: 'current' } })
    expect(wrapper.find('.successor-row').exists()).toBe(false)
  })

  it('store.setDeclaration clears both successor fields once a status change moves the merged declaration away from planned-replacement', async () => {
    const { wrapper, store } = mountEditor(makeFip(), {
      status: 'planned-replacement',
      successorFreeText: 'Our own registry',
    })

    const statusSelect = wrapper.get('select')
    await statusSelect.setValue('current')

    const declaration = store.fip?.answers[0]?.declarations[0]
    expect(declaration?.status).toBe('current')
    expect(declaration?.successorFerId ?? null).toBeNull()
    expect(declaration?.successorFreeText ?? null).toBeNull()
  })
})
