import { describe, expect, it } from 'vitest'
import { buildMatrix } from './matrix'
import type { FerOut, FerType, FipOut, KnowledgeModelContent, KnowledgeModelOut } from '@/types/api'
// The real content of `data/knowledge-models/gofair-fip-mini-1.0.0.json`
// (spec 03 §4 criterion 10 requires "a fixture of the real ... model"),
// read directly rather than duplicated by hand so this test cannot drift
// from the questionnaire the app actually serves.
import kmFixtureJson from '../../../data/knowledge-models/gofair-fip-mini-1.0.0.json'

const kmContent = kmFixtureJson as unknown as KnowledgeModelContent

const km: KnowledgeModelOut = {
  id: kmContent.id,
  version: kmContent.version,
  status: kmContent.status,
  visibility: 'public',
  license: kmContent.license,
  source: 'GO FAIR FIP mini-questionnaire',
  title: kmContent.title,
  description: kmContent.description,
  changelog: kmContent.changelog,
  content: kmContent,
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
}

const fers = new Map<string, FerOut>([
  ['doi-service', { id: 'doi-service', label: { en: 'DOI', 'pt-BR': 'DOI', 'pt-PT': 'DOI' }, type: 'identifier-service', homepage: null, source: 'seed' }],
  ['handle-service', { id: 'handle-service', label: { en: 'Handle', 'pt-BR': 'Handle' }, type: 'identifier-service', homepage: null, source: 'seed' }],
])

const ferTypes = new Map<string, FerType>([
  [
    'identifier-service',
    { key: 'identifier-service', iri: 'fip:Identifier-service', principle: 'F1', label: { en: 'Identifier service', 'pt-BR': 'Serviço de identificador' }, description: {} },
  ],
])

function makeFip(overrides: Partial<FipOut> & Pick<FipOut, 'id' | 'createdAt' | 'answers'>): FipOut {
  return {
    ownerId: null,
    sessionId: 'session-1',
    visibility: 'link',
    questionnaireId: 'gofair-fip-mini',
    questionnaireVersion: '1.0.0',
    title: null,
    community: { name: 'Community', links: [] },
    relatedDmps: [],
    language: 'en',
    license: 'CC0-1.0',
    updatedAt: overrides.createdAt,
    ...overrides,
  }
}

const fip1 = makeFip({
  id: 'fip-1',
  createdAt: '2026-09-01T00:00:00Z',
  community: { name: 'Alpha Community', links: [] },
  language: 'en',
  answers: [
    {
      questionId: 'F1-metadata',
      declarations: [
        { ferId: 'doi-service', status: 'current', note: { en: 'English note', 'pt-BR': 'Nota em português' } },
      ],
      comment: 'fip1 comment (en)',
    },
    { questionId: 'F1-data', declarations: [{ ferId: 'doi-service', status: 'current' }] },
    { questionId: 'F2', declarations: [{ ferFreeText: 'My Repo', status: 'current' }] },
    { questionId: 'F3', declarations: [{ status: 'planned', ferId: 'x' }] },
  ],
})

const fip2 = makeFip({
  id: 'fip-2',
  createdAt: '2026-09-02T00:00:00Z',
  community: { name: 'Beta Community', links: [] },
  language: 'pt-BR',
  answers: [
    {
      questionId: 'F1-metadata',
      declarations: [{ ferId: 'doi-service', status: 'current' }],
      comment: 'fip2 comentário (pt-BR)',
    },
    { questionId: 'F1-data', declarations: [{ ferId: 'doi-service', status: 'current' }] },
    { questionId: 'F2', declarations: [{ ferFreeText: 'my repo ', status: 'current' }] },
    { questionId: 'F3', declarations: [{ status: 'none' }] },
  ],
})

const fip3 = makeFip({
  id: 'fip-3',
  createdAt: '2026-09-03T00:00:00Z',
  community: { name: 'Gamma Research Community Group', links: [] },
  language: 'pt-PT',
  answers: [
    { questionId: 'F1-metadata', declarations: [{ ferId: 'handle-service', status: 'current' }] },
    { questionId: 'F1-data', declarations: [{ ferId: 'doi-service', status: 'current' }] },
    // F2 and F3 intentionally left unanswered for this FIP.
  ],
})

const fips: FipOut[] = [fip1, fip2, fip3]

// Criterion 10.
describe('buildMatrix — shape', () => {
  it('returns 4 groups totalling 21 rows in knowledge-model order', () => {
    const matrix = buildMatrix(fips, km, fers, ferTypes, 'en')
    expect(matrix.groups.map((g) => g.sectionId)).toEqual(['F', 'A', 'I', 'R'])
    expect(matrix.groups.map((g) => g.rows.length)).toEqual([6, 5, 6, 4])
    expect(matrix.questionCount).toBe(21)
    const totalRows = matrix.groups.reduce((n, g) => n + g.rows.length, 0)
    expect(totalRows).toBe(21)
  })

  it('returns 3 columns in createdAt order with labels truncated to 24 chars', () => {
    const matrix = buildMatrix(fips, km, fers, ferTypes, 'en')
    expect(matrix.columns.map((c) => c.fipId)).toEqual(['fip-1', 'fip-2', 'fip-3'])
    expect(matrix.columns[0].label).toBe('Alpha Community')
    expect(matrix.columns[2].fullLabel).toBe('Gamma Research Community Group')
    expect(matrix.columns[2].label).toBe(`${matrix.columns[2].fullLabel.slice(0, 24)}…`)
    expect(matrix.columns[2].label.length).toBeLessThanOrEqual(25)
  })

  it('has one cell per (row, column) and unanswered exactly where there are no declarations', () => {
    const matrix = buildMatrix(fips, km, fers, ferTypes, 'en')
    const f1metadata = matrix.groups[0].rows.find((r) => r.questionId === 'F1-metadata')!
    expect(f1metadata.cells).toHaveLength(3)
    expect(f1metadata.cells.every((c) => !c.unanswered)).toBe(true)

    const f4metadata = matrix.groups[0].rows.find((r) => r.questionId === 'F4-metadata')!
    expect(f4metadata.cells).toHaveLength(3)
    expect(f4metadata.cells.every((c) => c.unanswered)).toBe(true)

    const f2row = matrix.groups[0].rows.find((r) => r.questionId === 'F2')!
    // fip1 and fip2 answered F2, fip3 did not.
    expect(f2row.cells.map((c) => c.unanswered)).toEqual([false, false, true])
  })

  it('resolves notes and comments by resolveLang for the switched locale', () => {
    const en = buildMatrix(fips, km, fers, ferTypes, 'en')
    const ptBR = buildMatrix(fips, km, fers, ferTypes, 'pt-BR')

    const noteEn = en.groups[0].rows.find((r) => r.questionId === 'F1-metadata')!.cells[0].chips[0].note
    const notePtBR = ptBR.groups[0].rows.find((r) => r.questionId === 'F1-metadata')!.cells[0].chips[0].note
    expect(noteEn).toBe('English note')
    expect(notePtBR).toBe('Nota em português')

    const commentEn = en.groups[0].rows.find((r) => r.questionId === 'F1-metadata')!.cells[0].comment
    const commentPtBR = ptBR.groups[0].rows.find((r) => r.questionId === 'F1-metadata')!.cells[0].comment
    expect(commentEn).toBe('fip1 comment (en)')
    // The comment is stored only in the FIP's own language; resolveLang
    // still resolves it (the only key present) rather than dropping it.
    expect(commentPtBR).toBe('fip1 comment (en)')
  })
})

// Criterion 11.
describe('buildMatrix — convergence', () => {
  const matrix = buildMatrix(fips, km, fers, ferTypes, 'en')
  const rowsById = new Map(matrix.groups.flatMap((g) => g.rows.map((r) => [r.questionId, r])))

  it('two FIPs on DOI (current) and one on Handle (current)', () => {
    const row = rowsById.get('F1-metadata')!
    expect(row.convergence.declaringFips).toBe(3)
    expect(row.convergence.distinctCurrent).toBe(2)
    expect(row.convergence.topLabel).toBe('DOI')
    expect(row.convergence.topCount).toBe(2)
    expect(row.convergence.agreed).toBe(false)
  })

  it('all three FIPs on DOI (current) agree', () => {
    const row = rowsById.get('F1-data')!
    expect(row.convergence.declaringFips).toBe(3)
    expect(row.convergence.distinctCurrent).toBe(1)
    expect(row.convergence.agreed).toBe(true)
  })

  it('free-text currents differing only in case and a trailing space count as one', () => {
    const row = rowsById.get('F2')!
    expect(row.convergence.declaringFips).toBe(2)
    expect(row.convergence.distinctCurrent).toBe(1)
    expect(row.convergence.agreed).toBe(true)
  })

  it('planned and none declarations never count towards convergence', () => {
    const row = rowsById.get('F3')!
    expect(row.convergence.declaringFips).toBe(0)
    expect(row.convergence.distinctCurrent).toBe(0)
    expect(row.convergence.topKey).toBeNull()
    expect(row.convergence.agreed).toBe(false)
  })

  it('group rowsAgreed equals the number of rows with agreed convergence', () => {
    const groupF = matrix.groups[0]
    const expected = groupF.rows.filter((r) => r.convergence.agreed).length
    expect(groupF.rowsAgreed).toBe(expected)
    expect(groupF.rowsAgreed).toBe(2) // F1-data and F2
  })
})
