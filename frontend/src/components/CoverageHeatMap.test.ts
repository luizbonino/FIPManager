import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/en.json'
import CoverageHeatMap from './CoverageHeatMap.vue'
import type { CoverageRow } from '@/types/dashboard'

function makeRow(key: string): CoverageRow {
  return {
    key,
    level: 'subPrinciple',
    subPrinciple: key,
    principle: key,
    principleGroup: key[0],
    questions: [`${key}-metadata`],
    ferTypes: [],
    counts: { current: 7102, planned: 812, none: 240, notApplicable: 95, unanswered: 1163, absent: 0 },
    shares: { current: 0.7545, planned: 0.086, none: 0.0254, notApplicable: 0.0101, unanswered: 0.1233, absent: 0 },
  }
}

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

describe('CoverageHeatMap.vue (spec 13 §6.2/AC-2/AC-7)', () => {
  it('renders exactly rows x 6 states cells for the GO FAIR 12-principle rollup', () => {
    const rows = ['F1', 'F2', 'F3', 'F4', 'A1.1', 'A1.2', 'A2', 'I1', 'I2', 'I3', 'R1.1', 'R1.2'].map(makeRow)
    const wrapper = mount(CoverageHeatMap, { props: { rows }, global: { plugins: [makeI18n()] } })
    expect(wrapper.findAll('.hm-value')).toHaveLength(12 * 6)
  })

  it('stays at 126 cells even for a 21-question rollup (no per-FIP column, fipCount-independent)', () => {
    const rows = Array.from({ length: 21 }, (_, i) => makeRow(`Q${i}`))
    const wrapper = mount(CoverageHeatMap, { props: { rows }, global: { plugins: [makeI18n()] } })
    expect(wrapper.findAll('.hm-value')).toHaveLength(21 * 6)
  })

  it('every cell carries its number and an aria-label — colour is never the only signal', () => {
    const wrapper = mount(CoverageHeatMap, { props: { rows: [makeRow('F1')] }, global: { plugins: [makeI18n()] } })
    const cells = wrapper.findAll('.hm-value')
    expect(cells).toHaveLength(6)
    for (const cell of cells) {
      expect(cell.find('.hm-number').text().length).toBeGreaterThan(0)
      expect(cell.attributes('aria-label')).toBeTruthy()
    }
    const currentCell = cells[0]
    expect(currentCell.find('.hm-number').text()).toBe('7,102')
  })

  it('shows a placeholder when there are no rows', () => {
    const wrapper = mount(CoverageHeatMap, { props: { rows: [] }, global: { plugins: [makeI18n()] } })
    expect(wrapper.find('.hm-empty').exists()).toBe(true)
  })
})
