/**
 * Pure, unit-tested derivation of the session comparison matrix (spec 03
 * §1.2) from data the app already fetches: `GET /api/sessions/{id}/fips`,
 * the knowledge model, the FER catalogue and the FER-type taxonomy. No
 * network call lives here — `SessionMatrix.vue` is the only caller.
 */
import { resolveLang } from './lang'
import type {
  Declaration,
  DeclarationStatus,
  FerOut,
  FerType,
  FipOut,
  KnowledgeModelOut,
} from '@/types/api'

export type CellStatus = DeclarationStatus | 'unanswered'

/** One stored declaration, rendered as one chip in `MatrixCell.vue`. */
export interface MatrixChip {
  /** `ferId` when catalogued, else `'text:' + normaliseFreeText(text)` — the convergence identity. */
  key: string
  /** Resolved FER label, or the free text, or the bare `ferId` when unrecognised. */
  label: string
  iri: string | null
  freeText: boolean
  status: DeclarationStatus
  note: string | null
}

export interface MatrixCell {
  fipId: string
  chips: MatrixChip[]
  comment: string | null
  unanswered: boolean
}

/** `agreed` = `declaringFips >= 2 && distinctCurrent === 1` (spec 03 §1.2). */
export interface Convergence {
  /** FIPs with >= 1 `current` declaration on this row. */
  declaringFips: number
  distinctCurrent: number
  topKey: string | null
  topLabel: string | null
  topCount: number
  agreed: boolean
}

export interface MatrixRow {
  questionId: string
  principle: string | null
  scope: 'metadata' | 'data' | null
  ferType: string | null
  ferTypeLabel: string | null
  text: string
  cells: MatrixCell[]
  convergence: Convergence
}

/** One per knowledge-model section: F, A, I, R. */
export interface MatrixGroup {
  sectionId: string
  title: string
  rows: MatrixRow[]
  rowsWithData: number
  rowsAgreed: number
}

export interface MatrixColumn {
  fipId: string
  /** `community.name` truncated to 24 chars + '…'. */
  label: string
  fullLabel: string
  url: string
  answeredCount: number
  updatedAt: string
}

export interface Matrix {
  columns: MatrixColumn[]
  groups: MatrixGroup[]
  questionCount: number
}

const LABEL_MAX_LENGTH = 24

/**
 * NFC-normalise, trim, collapse internal whitespace and casefold — the
 * *same* normalisation the backend's RDF export applies to free text
 * (spec 03 §2.4), so the matrix and the Turtle export agree on what "the
 * same resource" is.
 */
export function normaliseFreeText(text: string): string {
  return text.normalize('NFC').trim().replace(/\s+/g, ' ').toLowerCase()
}

function truncateLabel(name: string): string {
  if (name.length <= LABEL_MAX_LENGTH) return name
  return `${name.slice(0, LABEL_MAX_LENGTH)}…`
}

function buildChip(declaration: Declaration, fers: Map<string, FerOut>, locale: string): MatrixChip {
  const note = resolveLang(declaration.note, locale)
  if (declaration.ferId) {
    const fer = fers.get(declaration.ferId)
    const label = (fer && resolveLang(fer.label, locale)) || declaration.ferId
    return {
      key: declaration.ferId,
      label,
      iri: declaration.ferId,
      freeText: false,
      status: declaration.status,
      note,
    }
  }
  if (declaration.ferFreeText) {
    return {
      key: `text:${normaliseFreeText(declaration.ferFreeText)}`,
      label: declaration.ferFreeText,
      iri: null,
      freeText: false,
      status: declaration.status,
      note,
    }
  }
  // No resource on record at all (e.g. a bare `none` declaration).
  return {
    key: `none:${declaration.status}`,
    label: '',
    iri: null,
    freeText: false,
    status: declaration.status,
    note,
  }
}

function buildCell(fip: FipOut, questionId: string, fers: Map<string, FerOut>, locale: string): MatrixCell {
  const answer = fip.answers.find((a) => a.questionId === questionId)
  const declarations = answer?.declarations ?? []
  return {
    fipId: fip.id,
    chips: declarations.map((d) => buildChip(d, fers, locale)),
    comment: resolveLang(
      answer?.comment ? { [fip.language]: answer.comment } : null,
      locale
    ),
    unanswered: declarations.length === 0,
  }
}

function buildConvergence(cells: MatrixCell[]): Convergence {
  const counts = new Map<string, { count: number; label: string }>()
  let declaringFips = 0
  for (const cell of cells) {
    const currentChips = cell.chips.filter((c) => c.status === 'current')
    if (currentChips.length > 0) declaringFips += 1
    for (const chip of currentChips) {
      const existing = counts.get(chip.key)
      if (existing) {
        existing.count += 1
      } else {
        counts.set(chip.key, { count: 1, label: chip.label })
      }
    }
  }
  const distinctCurrent = counts.size
  let topKey: string | null = null
  let topLabel: string | null = null
  let topCount = 0
  for (const [key, { count, label }] of counts) {
    if (count > topCount || (count === topCount && topKey !== null && key < topKey)) {
      topKey = key
      topLabel = label
      topCount = count
    }
  }
  return {
    declaringFips,
    distinctCurrent,
    topKey,
    topLabel,
    topCount,
    agreed: declaringFips >= 2 && distinctCurrent === 1,
  }
}

export function buildMatrix(
  fips: FipOut[],
  km: KnowledgeModelOut,
  fers: Map<string, FerOut>,
  ferTypes: Map<string, FerType>,
  locale: string
): Matrix {
  // Columns follow `createdAt`, the order `GET /api/sessions/{id}/fips`
  // returns — never re-sorted here (spec 03 §1.2).
  const columns: MatrixColumn[] = fips.map((fip) => {
    const fullLabel = fip.community?.name || fip.id
    return {
      fipId: fip.id,
      label: truncateLabel(fullLabel),
      fullLabel,
      url: `/fips/${fip.id}`,
      answeredCount: fip.answers.filter((a) => (a.declarations?.length ?? 0) > 0).length,
      updatedAt: fip.updatedAt,
    }
  })

  let questionCount = 0
  const groups: MatrixGroup[] = km.content.sections.map((section) => {
    const rows: MatrixRow[] = section.questions.map((question) => {
      questionCount += 1
      const cells = fips.map((fip) => buildCell(fip, question.id, fers, locale))
      const ferType = question.ferType
      const ferTypeLabel = ferType ? (resolveLang(ferTypes.get(ferType)?.label, locale) ?? ferType) : null
      return {
        questionId: question.id,
        principle: question.principle,
        scope: question.scope,
        ferType,
        ferTypeLabel,
        text: resolveLang(question.text, locale) ?? question.id,
        cells,
        convergence: buildConvergence(cells),
      }
    })
    return {
      sectionId: section.id,
      title: resolveLang(section.title, locale) ?? section.id,
      rows,
      rowsWithData: rows.filter((r) => r.cells.some((c) => !c.unanswered)).length,
      rowsAgreed: rows.filter((r) => r.convergence.agreed).length,
    }
  })

  return { columns, groups, questionCount }
}

export interface MatrixOptions {
  /** Hide chips whose status is not `current`; a cell emptied that way renders as unanswered. */
  onlyCurrent: boolean
  /** Drop rows where *every* cell is unanswered — never rows that merely have gaps. */
  hideUnanswered: boolean
}

/**
 * Applies the `onlyCurrent`/`hideUnanswered` toggles (spec 03 §1.4) to an
 * already-built `Matrix`, pure and side-effect-free so `SessionMatrix.vue`
 * can recompute it on every toggle without refetching anything.
 */
export function applyMatrixOptions(matrix: Matrix, opts: MatrixOptions): Matrix {
  const groups = matrix.groups.map((group) => {
    let rows = group.rows.map((row) => {
      if (!opts.onlyCurrent) return row
      const cells = row.cells.map((cell) => {
        if (cell.unanswered) return cell
        const chips = cell.chips.filter((c) => c.status === 'current')
        return { ...cell, chips, unanswered: chips.length === 0 }
      })
      return { ...row, cells }
    })
    if (opts.hideUnanswered) {
      rows = rows.filter((row) => row.cells.some((c) => !c.unanswered))
    }
    return {
      ...group,
      rows,
      rowsWithData: rows.filter((r) => r.cells.some((c) => !c.unanswered)).length,
      rowsAgreed: rows.filter((r) => r.convergence.agreed).length,
    }
  })
  return { ...matrix, groups }
}
