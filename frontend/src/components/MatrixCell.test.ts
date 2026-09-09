import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import MatrixCell from './MatrixCell.vue'
import en from '@/i18n/en.json'
import type { MatrixCell as MatrixCellType } from '@/lib/matrix'

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function mountCell(cell: MatrixCellType, compact = false) {
  return mount(MatrixCell, {
    props: { cell, compact },
    global: { plugins: [makeI18n()] },
  })
}

// Criterion 12 (docs/specs/03-matrix-and-rdf.md §4): one chip per
// declaration, each carrying its `status-*` class and the status text.
describe('MatrixCell', () => {
  it('renders one chip per declaration, each with its status class and status text', () => {
    const cell: MatrixCellType = {
      fipId: 'fip-1',
      notApplicable: false,
      absent: false,
      unanswered: false,
      comment: null,
      chips: [
        { key: 'a', label: 'DOI', iri: 'a', freeText: false, status: 'current', note: null, successorLabel: null },
        { key: 'b', label: 'Handle', iri: 'b', freeText: false, status: 'planned', note: null, successorLabel: null },
        { key: 'c', label: 'Custom vocab', iri: null, freeText: true, status: 'planned-development', note: null, successorLabel: null },
        { key: 'd', label: 'Old system', iri: 'd', freeText: false, status: 'planned-replacement', note: null, successorLabel: 'New system' },
        { key: 'e', label: '', iri: null, freeText: false, status: 'none', note: null, successorLabel: null },
      ],
    }
    const wrapper = mountCell(cell)
    const buttons = wrapper.findAll('button.chip')
    expect(buttons).toHaveLength(5)

    expect(buttons[0].classes()).toContain('status-current')
    expect(buttons[0].text()).toContain('DOI')
    expect(buttons[0].text()).toContain(en.declarationStatus.current)

    expect(buttons[1].classes()).toContain('status-planned')
    expect(buttons[1].text()).toContain(en.declarationStatus.planned)

    expect(buttons[2].classes()).toContain('status-planned-development')
    expect(buttons[2].text()).toContain(en.declarationStatus.plannedDevelopment)

    expect(buttons[3].classes()).toContain('status-planned-replacement')
    expect(buttons[3].text()).toContain(en.declarationStatus.plannedReplacement)

    expect(buttons[4].classes()).toContain('status-none')
    expect(buttons[4].text()).toContain(en.declarationStatus.none)
  })

  it('renders the status-unanswered placeholder for an empty cell, no chip buttons', () => {
    const cell: MatrixCellType = {
      fipId: 'fip-1',
      notApplicable: false,
      absent: false,
      unanswered: true,
      comment: null,
      chips: [],
    }
    const wrapper = mountCell(cell)
    expect(wrapper.findAll('button.chip')).toHaveLength(0)
    const placeholder = wrapper.get('.status-unanswered')
    expect(placeholder.text()).toBe('–')
    expect(placeholder.attributes('aria-label')).toBe(en.matrix.unanswered)
  })

  // Spec 08 §2.2: a notApplicable cell renders its own distinct chip, never
  // the plain "unanswered" placeholder, even though it carries no chips.
  it('renders the not-applicable chip, not the unanswered placeholder, for a notApplicable cell', () => {
    const cell: MatrixCellType = { fipId: 'fip-1', notApplicable: true, absent: false, unanswered: false, comment: null, chips: [] }
    const wrapper = mountCell(cell)
    expect(wrapper.find('.status-unanswered').exists()).toBe(false)
    expect(wrapper.findAll('button.chip')).toHaveLength(0)
    const naChip = wrapper.get('.status-not-applicable')
    expect(naChip.text()).toBe(en.matrix.notApplicableShort)
    expect(naChip.attributes('title')).toBe(en.matrix.notApplicableFull)
    expect(naChip.attributes('aria-label')).toBe(en.matrix.notApplicableFull)
  })

  // Spec 08 §3.3: an absent cell (the column's model lacks this row) is
  // distinct from both unanswered and notApplicable.
  it('renders the absent placeholder, distinct from unanswered and notApplicable', () => {
    const cell: MatrixCellType = { fipId: 'fip-1', notApplicable: false, absent: true, unanswered: true, comment: null, chips: [] }
    const wrapper = mountCell(cell)
    expect(wrapper.find('.status-unanswered').exists()).toBe(false)
    expect(wrapper.find('.status-not-applicable').exists()).toBe(false)
    const absentEl = wrapper.get('.status-absent')
    expect(absentEl.attributes('aria-label')).toBe(en.matrix.absent)
  })

  it('compact mode abbreviates the status text to three letters but keeps it in full in the title', () => {
    const cell: MatrixCellType = {
      fipId: 'fip-1',
      notApplicable: false,
      absent: false,
      unanswered: false,
      comment: null,
      chips: [{ key: 'a', label: 'DOI', iri: 'a', freeText: false, status: 'current', note: null, successorLabel: null }],
    }
    const wrapper = mountCell(cell, true)
    const button = wrapper.get('button.chip')
    expect(button.text()).toContain('CUR')
    expect(button.text()).not.toContain(en.declarationStatus.current)
    expect(button.attributes('title')).toContain(en.declarationStatus.current)
  })

  it('a chip with a note toggles the note text under the chips on click', async () => {
    const cell: MatrixCellType = {
      fipId: 'fip-1',
      notApplicable: false,
      absent: false,
      unanswered: false,
      comment: null,
      chips: [
        {
          key: 'a',
          label: 'DOI',
          iri: 'a',
          freeText: false,
          status: 'current',
          note: 'Because it is standard',
          successorLabel: null,
        },
      ],
    }
    const wrapper = mountCell(cell)
    expect(wrapper.find('.chip-note').exists()).toBe(false)
    await wrapper.get('button.chip').trigger('click')
    expect(wrapper.find('.chip-note').exists()).toBe(true)
    expect(wrapper.get('.chip-note').text()).toContain('Because it is standard')
    await wrapper.get('button.chip').trigger('click')
    expect(wrapper.find('.chip-note').exists()).toBe(false)
  })

  // Criterion 17 (docs/specs/05-v1-completion.md §8): the successor label
  // lands in the chip's title/aria-label and, on click, under the chip.
  it('puts a successor label in the chip title and reveals it on click', async () => {
    const cell: MatrixCellType = {
      fipId: 'fip-1',
      notApplicable: false,
      absent: false,
      unanswered: false,
      comment: null,
      chips: [
        {
          key: 'a',
          label: 'Old system',
          iri: 'a',
          freeText: false,
          status: 'planned-replacement',
          note: null,
          successorLabel: 'New system',
        },
      ],
    }
    const wrapper = mountCell(cell)
    const button = wrapper.get('button.chip')
    expect(button.attributes('title')).toContain('New system')
    expect(wrapper.find('.chip-successor').exists()).toBe(false)
    await button.trigger('click')
    expect(wrapper.get('.chip-successor').text()).toContain('New system')
  })

  it('a chip with neither note nor successor label is not clickable to expand anything', async () => {
    const cell: MatrixCellType = {
      fipId: 'fip-1',
      notApplicable: false,
      absent: false,
      unanswered: false,
      comment: null,
      chips: [{ key: 'a', label: 'DOI', iri: 'a', freeText: false, status: 'current', note: null, successorLabel: null }],
    }
    const wrapper = mountCell(cell)
    await wrapper.get('button.chip').trigger('click')
    expect(wrapper.find('.chip-note').exists()).toBe(false)
    expect(wrapper.find('.chip-successor').exists()).toBe(false)
  })
})
