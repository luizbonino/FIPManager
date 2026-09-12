import { describe, expect, it } from 'vitest'
import normalisationFixture from '../../../backend/tests/fixtures/dashboard/normalisation-cases.json'
import {
  CELL_STATE_ORDER,
  canonicalisePopulationSpec,
  decodePopulationParam,
  encodePopulationParam,
  formatConvergenceKey,
  formatCount,
  formatShare,
  iriTail,
  isSavedPopulationHash,
  normaliseFreeText,
  orderCellStates,
  rollupCoverage,
  type PopulationSpec,
} from './dashboard'
import type { CoverageData, CoverageRow } from '@/types/dashboard'

// spec 13 builder brief C: "assert normaliseFreeText against it, so the
// frontend and backend keys are proven identical (brief A's test 2 is the
// other half)". Consumes the shared fixture verbatim — brief A landed it
// at backend/tests/fixtures/dashboard/normalisation-cases.json while this
// brief was in progress.
interface NormalisationCase {
  id: string
  group: string
  text: string
  normalised: string
}
const normalisationCases = normalisationFixture.cases as NormalisationCase[]

describe('normaliseFreeText (shared fixture, spec 13 §1.5)', () => {
  it.each(normalisationCases)('$id: normalises to the expected value', ({ text, normalised }) => {
    expect(normaliseFreeText(text)).toBe(normalised)
  })

  it('cases in the same group normalise identically (same declared resource, different byte representation)', () => {
    const byGroup = new Map<string, string[]>()
    for (const c of normalisationCases) {
      const list = byGroup.get(c.group) ?? []
      list.push(normaliseFreeText(c.text))
      byGroup.set(c.group, list)
    }
    for (const [group, values] of byGroup) {
      expect(new Set(values).size, `group "${group}" should normalise to one value`).toBe(1)
    }
  })
})

describe('population spec <-> query string (spec 13 §2.1)', () => {
  it('encodes a bare public term as the "public" shorthand', () => {
    const spec: PopulationSpec = { version: 1, include: [{ kind: 'public' }], exclude: [], updatedAfter: null, updatedBefore: null }
    expect(encodePopulationParam(spec)).toBe('public')
  })

  it('encodes a bare network term as the "network" shorthand', () => {
    const spec: PopulationSpec = { version: 1, include: [{ kind: 'network' }], exclude: [], updatedAfter: null, updatedBefore: null }
    expect(encodePopulationParam(spec)).toBe('network')
  })

  it('encodes a bare session term as "session:<id>"', () => {
    const spec: PopulationSpec = { version: 1, include: [{ kind: 'session', id: 's_abc' }], exclude: [], updatedAfter: null, updatedBefore: null }
    expect(encodePopulationParam(spec)).toBe('session:s_abc')
  })

  it('round-trips the three shorthands through decode', () => {
    expect(decodePopulationParam('public')?.include).toEqual([{ kind: 'public' }])
    expect(decodePopulationParam('network')?.include).toEqual([{ kind: 'network' }])
    expect(decodePopulationParam('session:s_abc')?.include).toEqual([{ kind: 'session', id: 's_abc' }])
  })

  it('falls back to inline base64 JSON for a multi-term spec, and round-trips it', () => {
    const spec: PopulationSpec = {
      version: 1,
      include: [
        { kind: 'questionnaire', id: 'gofair-fip-mini', version: '2.0.0' },
        { kind: 'mine' },
      ],
      exclude: [{ kind: 'session', id: 's_test' }],
      updatedAfter: '2026-01-01T00:00:00Z',
      updatedBefore: null,
    }
    const encoded = encodePopulationParam(spec)
    expect(encoded).not.toBe('public')
    expect(encoded).not.toMatch(/^session:/)
    const decoded = decodePopulationParam(encoded)
    expect(decoded).toEqual(canonicalisePopulationSpec(spec))
  })

  it('canonicalisation sorts and de-duplicates include/exclude terms', () => {
    const spec: PopulationSpec = {
      version: 1,
      include: [
        { kind: 'mine' },
        { kind: 'public' },
        { kind: 'public' },
      ],
      exclude: [],
      updatedAfter: null,
      updatedBefore: null,
    }
    const canon = canonicalisePopulationSpec(spec)
    expect(canon.include).toEqual([{ kind: 'mine' }, { kind: 'public' }])
  })

  it('treats an opaque saved-population hash as non-decodable', () => {
    const hash = 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4'
    expect(decodePopulationParam(hash)).toBeNull()
    expect(isSavedPopulationHash(hash)).toBe(true)
    expect(isSavedPopulationHash('public')).toBe(false)
  })
})

describe('cell_state ordering (spec 13 §1.3)', () => {
  it('orders the six states by precedence', () => {
    expect(CELL_STATE_ORDER).toEqual(['current', 'planned', 'none', 'notApplicable', 'unanswered', 'absent'])
  })

  it('sorts an arbitrary subset into precedence order', () => {
    expect(orderCellStates(['absent', 'current', 'none'])).toEqual(['current', 'none', 'absent'])
  })
})

describe('formatShare / formatCount', () => {
  it('formats a share as a one-decimal percentage', () => {
    // 0.7545 has no exact binary representation (~0.754499999999999993…),
    // so a correct decimal formatter rounds it down, not to a "nicer" 75.5.
    expect(formatShare(0.7545)).toBe('75.4%')
    expect(formatShare(0.755)).toBe('75.5%')
    expect(formatShare(0)).toBe('0.0%')
    expect(formatShare(1)).toBe('100.0%')
  })

  it('formats a non-finite share as an em dash', () => {
    expect(formatShare(NaN)).toBe('—')
  })

  it('groups large counts', () => {
    expect(formatCount(9412)).toMatch(/9[,.\s]?412/)
  })
})

describe('rollupCoverage (spec 13 §3.1 / §6.2)', () => {
  function makeRow(overrides: Partial<CoverageRow>): CoverageRow {
    return {
      key: 'F1-metadata',
      level: 'question',
      subPrinciple: 'F1',
      principle: 'F1',
      principleGroup: 'F',
      questions: ['F1-metadata'],
      ferTypes: ['identifier-service'],
      counts: { current: 7, planned: 1, none: 0, notApplicable: 0, unanswered: 2, absent: 0 },
      shares: { current: 0.7, planned: 0.1, none: 0, notApplicable: 0, unanswered: 0.2, absent: 0 },
      ...overrides,
    }
  }

  function makeData(rows: CoverageRow[]): CoverageData {
    return { rows, totals: { fips: 10, cells: rows.length * 10 }, order: ['F1', 'F2', 'A1.1'] }
  }

  it('returns the finest rows unchanged for groupBy=question', () => {
    const data = makeData([makeRow({})])
    expect(rollupCoverage(data, 'question')).toBe(data.rows)
  })

  it('sums counts across questions under the same sub-principle', () => {
    const data = makeData([
      makeRow({ key: 'F1-metadata', questions: ['F1-metadata'], counts: { current: 5, planned: 0, none: 0, notApplicable: 0, unanswered: 5, absent: 0 } }),
      makeRow({ key: 'F1-data', questions: ['F1-data'], counts: { current: 3, planned: 0, none: 0, notApplicable: 0, unanswered: 7, absent: 0 } }),
    ])
    const rolled = rollupCoverage(data, 'subPrinciple')
    expect(rolled).toHaveLength(1)
    expect(rolled[0].key).toBe('F1')
    expect(rolled[0].counts.current).toBe(8)
    expect(rolled[0].counts.unanswered).toBe(12)
    expect(rolled[0].questions.sort()).toEqual(['F1-data', 'F1-metadata'])
  })

  it('recomputes shares from the summed counts, not an average of shares', () => {
    const data = makeData([
      makeRow({ key: 'F1-metadata', questions: ['F1-metadata'], counts: { current: 5, planned: 0, none: 0, notApplicable: 0, unanswered: 5, absent: 0 } }),
      makeRow({ key: 'F1-data', questions: ['F1-data'], counts: { current: 3, planned: 0, none: 0, notApplicable: 0, unanswered: 7, absent: 0 } }),
    ])
    const rolled = rollupCoverage(data, 'subPrinciple')
    expect(rolled[0].shares.current).toBeCloseTo(0.4)
    expect(rolled[0].shares.unanswered).toBeCloseTo(0.6)
  })

  it('rolls sub-principles up to principle level (A1.1/A1.2 -> A1)', () => {
    const data = makeData([
      makeRow({ key: 'A1.1', subPrinciple: 'A1.1', principle: 'A1', principleGroup: 'A', questions: ['A1.1'], counts: { current: 2, planned: 0, none: 0, notApplicable: 0, unanswered: 8, absent: 0 } }),
      makeRow({ key: 'A1.2', subPrinciple: 'A1.2', principle: 'A1', principleGroup: 'A', questions: ['A1.2'], counts: { current: 4, planned: 0, none: 0, notApplicable: 0, unanswered: 6, absent: 0 } }),
    ])
    const rolled = rollupCoverage(data, 'principle')
    expect(rolled).toHaveLength(1)
    expect(rolled[0].key).toBe('A1')
    expect(rolled[0].counts.current).toBe(6)
  })

  it('rolls everything up to the FAIR-letter group level', () => {
    const data = makeData([
      makeRow({ key: 'F1', subPrinciple: 'F1', principle: 'F1', principleGroup: 'F', questions: ['F1-metadata'] }),
      makeRow({ key: 'F2', subPrinciple: 'F2', principle: 'F2', principleGroup: 'F', questions: ['F2-metadata'] }),
      makeRow({ key: 'A1.1', subPrinciple: 'A1.1', principle: 'A1', principleGroup: 'A', questions: ['A1.1'] }),
    ])
    const rolled = rollupCoverage(data, 'group')
    expect(rolled.map((r) => r.key).sort()).toEqual(['A', 'F'])
  })

  // Regression: a `groupBy=question` response with `subPrinciple` missing
  // (or `undefined`/empty on every row -- e.g. a backend contract drift like
  // spec 13's coverage endpoint once shipped, which never emitted the field
  // at all) makes `rollupKeyFor`'s `subPrinciple` case key every row
  // identically, merging the whole heat map into one unlabelled bucket. A
  // realistic multi-sub-principle, multi-question payload must roll up to
  // one distinctly-keyed row per sub-principle, and every row's own default
  // grouping level ('subPrinciple') must render, not collapse.
  it('keeps rows from different sub-principles distinctly keyed under the default grouping (regression: missing subPrinciple collapses the heat map)', () => {
    const data = makeData([
      makeRow({ key: 'F1-metadata', subPrinciple: 'F1', principle: 'F1', principleGroup: 'F', questions: ['F1-metadata'] }),
      makeRow({ key: 'F1-data', subPrinciple: 'F1', principle: 'F1', principleGroup: 'F', questions: ['F1-data'] }),
      makeRow({ key: 'F2-metadata', subPrinciple: 'F2', principle: 'F2', principleGroup: 'F', questions: ['F2-metadata'] }),
      makeRow({ key: 'A1.1-data', subPrinciple: 'A1.1', principle: 'A1', principleGroup: 'A', questions: ['A1.1-data'] }),
    ])
    const rolled = rollupCoverage(data, 'subPrinciple')
    const keys = rolled.map((r) => r.key).sort()
    expect(keys).toEqual(['A1.1', 'F1', 'F2'])
    // Distinct rows, not one bucket keyed by a stringified `undefined`.
    expect(new Set(keys).size).toBe(3)
    expect(keys).not.toContain('undefined')
  })
})

// spec 13 §11.3 amendment: `NeighbourRow.topShared[].label` and
// `ConvergenceRow.topLabel` carry the raw convergence key, not a resolved
// name — never render either raw.
describe('formatConvergenceKey / iriTail (spec 13 §11.3 amendment)', () => {
  it('shows the tail of a resource IRI, ignoring a trailing slash', () => {
    expect(iriTail('https://w3id.org/fair/fip/terms/DataCite')).toBe('DataCite')
    expect(iriTail('https://example.org/vocab#DataCite')).toBe('DataCite')
    expect(iriTail('https://example.org/vocab/DataCite/')).toBe('DataCite')
  })

  it('formats a resource IRI key as its tail, not flagged as free text', () => {
    const formatted = formatConvergenceKey('https://w3id.org/fair/fip/terms/DataCite')
    expect(formatted).toEqual({ text: 'DataCite', isFreeText: false })
  })

  it('strips the "text:" prefix and flags a free-text key', () => {
    const formatted = formatConvergenceKey('text:institutional repository')
    expect(formatted).toEqual({ text: 'institutional repository', isFreeText: true })
  })

  it('never leaves the raw "text:" prefix in the rendered text', () => {
    const formatted = formatConvergenceKey('text:some free text value')
    expect(formatted.text.startsWith('text:')).toBe(false)
  })
})
