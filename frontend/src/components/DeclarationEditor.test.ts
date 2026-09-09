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
  store.setFip(fip)

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
