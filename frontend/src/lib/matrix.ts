/**
 * Pure, unit-tested derivation of the session comparison matrix (spec 03
 * §1.2, extended by spec 08 §3.3 for a multi-questionnaire session) from
 * data the app already fetches: `GET /api/sessions/{id}/fips`, the
 * knowledge model(s), the FER catalogue and the FER-type taxonomy. No
 * network call lives here — `SessionMatrix.vue` is the only caller.
 */
import { resolveLang } from './lang'
import { allQuestions } from './kmContent'
import type {
  Declaration,
  DeclarationStatus,
  FerOut,
  FerType,
  FipOut,
  KnowledgeModelOut,
  LangMap,
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
  /**
   * spec 05 §5: the resolved successor label, exactly like `label` — a
   * catalogued `successorFerId`'s FER label, else `successorFreeText`, else
   * `null`. Always `null` unless `status === 'planned-replacement'`.
   */
  successorLabel: string | null
}

export interface MatrixCell {
  fipId: string
  chips: MatrixChip[]
  comment: string | null
  unanswered: boolean
  /** spec 08 §2.2: the answer is marked "not applicable" — `chips` is always `[]`; `unanswered` stays `false` (it *is* answered). */
  notApplicable: boolean
  /**
   * spec 08 §3.3: the column's own questionnaire model does not have this
   * row's question at all (a multi-ref session where forks diverge).
   * Rendered as a hatched placeholder distinct from both `unanswered` and
   * `notApplicable`; `unanswered` is kept `true` alongside it so the
   * existing "row has no data"/`hideUnanswered` aggregates stay correct.
   */
  absent: boolean
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
  /** spec 08 §2.2: FIPs whose cell on this row is `notApplicable` — never a `current` declaration, so untouched above. */
  notApplicableFips: number
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
  /**
   * `principle?.[0] ?? 'Other'` (spec 04 §4): the FAIR-letter group derived
   * from the row's own `principle` code (independent of which section it
   * lives in), for a future per-principle convergence view; every row with
   * `principle === null` collects under `'Other'`.
   */
  principleGroup: string
  /** spec 08 §3.3: refKeys (`id@version`) of the models that actually have this question id. */
  presentIn: string[]
}

/** One per knowledge-model section — not necessarily F/A/I/R once custom models exist (spec 04). */
export interface MatrixGroup {
  sectionId: string
  /**
   * The section's resolved title, or `null` when its `title` LangMap
   * resolves to nothing (spec 04 §4) — the renderer falls back to the
   * `matrix.otherGroup` ("Other") label in that case.
   */
  title: string | null
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
  /** spec 08 §3.3: `id@version` of this FIP's own questionnaire ref — which column group it belongs to. */
  refKey: string
  /** spec 08 §3.3: the ref's resolved area label, or `null` on a single-ref session. */
  areaLabel: string | null
}

/** One `<th colspan>` group header per questionnaire ref (spec 08 §3.3). */
export interface MatrixColumnGroup {
  refKey: string
  label: string | null
  columnCount: number
}

export interface Matrix {
  columns: MatrixColumn[]
  columnGroups: MatrixColumnGroup[]
  groups: MatrixGroup[]
  questionCount: number
}

/** A session's labelled questionnaire ref (spec 08 §3.1's `QuestionnaireRefLabelled`), the caller's `refs` argument. */
export interface MatrixRef {
  id: string
  version: string
  label: LangMap
}

const LABEL_MAX_LENGTH = 24

/** `id@version` — the key both `kms` and `MatrixColumn.refKey`/`MatrixColumnGroup.refKey` use. */
export function refKey(id: string, version: string): string {
  return `${id}@${version}`
}

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

function buildSuccessorLabel(declaration: Declaration, fers: Map<string, FerOut>, locale: string): string | null {
  if (declaration.status !== 'planned-replacement') return null
  if (declaration.successorFerId) {
    const fer = fers.get(declaration.successorFerId)
    return (fer && resolveLang(fer.label, locale)) || declaration.successorFerId
  }
  if (declaration.successorFreeText) return declaration.successorFreeText
  return null
}

function buildChip(declaration: Declaration, fers: Map<string, FerOut>, locale: string): MatrixChip {
  const note = resolveLang(declaration.note, locale)
  const successorLabel = buildSuccessorLabel(declaration, fers, locale)
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
      successorLabel,
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
      successorLabel,
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
    successorLabel,
  }
}

function buildCell(
  fip: FipOut,
  questionId: string,
  fers: Map<string, FerOut>,
  locale: string,
  absent: boolean
): MatrixCell {
  if (absent) {
    return { fipId: fip.id, chips: [], comment: null, unanswered: true, notApplicable: false, absent: true }
  }
  const answer = fip.answers.find((a) => a.questionId === questionId)
  const notApplicable = answer?.notApplicable === true
  const declarations = answer?.declarations ?? []
  return {
    fipId: fip.id,
    chips: declarations.map((d) => buildChip(d, fers, locale)),
    comment: resolveLang(answer?.comment ? { [fip.language]: answer.comment } : null, locale),
    // spec 08 §2.2: N/A *is* answered — never `unanswered`, even though it carries no chips.
    unanswered: !notApplicable && declarations.length === 0,
    notApplicable,
    absent: false,
  }
}

function buildConvergence(cells: MatrixCell[]): Convergence {
  const counts = new Map<string, { count: number; label: string }>()
  let declaringFips = 0
  let notApplicableFips = 0
  for (const cell of cells) {
    if (cell.notApplicable) notApplicableFips += 1
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
    notApplicableFips,
  }
}

/**
 * `buildMatrix(fips, kms, fers, ferTypes, locale, refs)` (spec 08 §3.3):
 * `kms` is keyed by `refKey(id, version)`; `refs` is the session's ordered,
 * labelled questionnaire-ref list (a single-entry array for an ordinary
 * one-questionnaire session — the multi-ref case is additive, not a
 * separate code path). A ref whose model hasn't loaded (yet) into `kms` is
 * skipped rather than crashing the render.
 */
export function buildMatrix(
  fips: FipOut[],
  kms: Map<string, KnowledgeModelOut>,
  fers: Map<string, FerOut>,
  ferTypes: Map<string, FerType>,
  locale: string,
  refs: MatrixRef[]
): Matrix {
  const fipsById = new Map(fips.map((f) => [f.id, f]))

  const refEntries = refs
    .map((ref) => ({ ref, key: refKey(ref.id, ref.version), km: kms.get(refKey(ref.id, ref.version)) }))
    .filter((e): e is { ref: MatrixRef; key: string; km: KnowledgeModelOut } => !!e.km)

  // Columns follow `createdAt` within each ref's group, groups in `refs`
  // order (spec 08 §3.3); never re-sorted across groups.
  const columnsByRef = refEntries.map(({ ref, key }) => {
    const refFips = fips
      .filter((f) => f.questionnaireId === ref.id && f.questionnaireVersion === ref.version)
      .slice()
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
    return { ref, key, fips: refFips }
  })

  const areaLabelByRefKey = new Map(columnsByRef.map(({ key, ref }) => [key, resolveLang(ref.label, locale)]))

  const columns: MatrixColumn[] = columnsByRef.flatMap(({ key, fips: refFips }) =>
    refFips.map((fip) => {
      const fullLabel = fip.community?.name || fip.id
      return {
        fipId: fip.id,
        label: truncateLabel(fullLabel),
        fullLabel,
        url: `/fips/${fip.id}`,
        answeredCount: fip.answers.filter((a) => (a.declarations?.length ?? 0) > 0 || a.notApplicable === true).length,
        updatedAt: fip.updatedAt,
        refKey: key,
        areaLabel: areaLabelByRefKey.get(key) ?? null,
      }
    })
  )

  const columnGroups: MatrixColumnGroup[] = columnsByRef.map(({ key, fips: refFips }) => ({
    refKey: key,
    label: areaLabelByRefKey.get(key) ?? null,
    columnCount: refFips.length,
  }))

  // Which question ids each ref's model actually has, for `presentIn`/`absent`.
  const questionIdsByRef = new Map<string, Set<string>>(
    refEntries.map(({ key, km }) => [key, new Set(allQuestions(km.content).map((q) => q.id))])
  )

  // Merge sections and rows across refs: first ref to introduce a section
  // or question id owns its title/text/principle/scope/ferType (spec 08
  // §3.3 — "in practice the base order" since the forks share the 21 ids).
  const sectionOrder: string[] = []
  const sectionTitleById = new Map<string, string | null>()
  const questionIdsBySection = new Map<string, string[]>()
  const seenQuestionIds = new Set<string>()
  interface RowMeta {
    principle: string | null
    scope: 'metadata' | 'data' | null
    ferType: string | null
    ferTypeLabel: string | null
    text: string
    principleGroup: string
  }
  const rowMetaById = new Map<string, RowMeta>()

  for (const { km } of refEntries) {
    for (const section of km.content.sections) {
      if (!sectionTitleById.has(section.id)) {
        sectionOrder.push(section.id)
        sectionTitleById.set(section.id, resolveLang(section.title, locale))
        questionIdsBySection.set(section.id, [])
      }
      for (const question of section.questions) {
        if (seenQuestionIds.has(question.id)) continue
        seenQuestionIds.add(question.id)
        questionIdsBySection.get(section.id)!.push(question.id)
        const ferType = question.ferType
        rowMetaById.set(question.id, {
          principle: question.principle,
          scope: question.scope,
          ferType,
          ferTypeLabel: ferType ? (resolveLang(ferTypes.get(ferType)?.label, locale) ?? ferType) : null,
          text: resolveLang(question.text, locale) ?? question.id,
          principleGroup: question.principle?.[0] ?? 'Other',
        })
      }
    }
  }

  let questionCount = 0
  const groups: MatrixGroup[] = sectionOrder.map((sectionId) => {
    const questionIds = questionIdsBySection.get(sectionId) ?? []
    const rows: MatrixRow[] = questionIds.map((questionId) => {
      questionCount += 1
      const meta = rowMetaById.get(questionId)!
      const presentIn = columnsByRef.filter(({ key }) => questionIdsByRef.get(key)?.has(questionId)).map(({ key }) => key)
      const presentSet = new Set(presentIn)
      const cells = columns.map((column) =>
        buildCell(fipsById.get(column.fipId)!, questionId, fers, locale, !presentSet.has(column.refKey))
      )
      return {
        questionId,
        principle: meta.principle,
        scope: meta.scope,
        ferType: meta.ferType,
        ferTypeLabel: meta.ferTypeLabel,
        text: meta.text,
        cells,
        convergence: buildConvergence(cells),
        principleGroup: meta.principleGroup,
        presentIn,
      }
    })
    return {
      sectionId,
      title: sectionTitleById.get(sectionId) ?? null,
      rows,
      rowsWithData: rows.filter((r) => r.cells.some((c) => !c.unanswered)).length,
      rowsAgreed: rows.filter((r) => r.convergence.agreed).length,
    }
  })

  return { columns, columnGroups, groups, questionCount }
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
        // spec 08 §2.2/§3.3: neither an absent nor a notApplicable cell has
        // "current" chips to filter — leave both exactly as they are so
        // onlyCurrent never turns either into a plain "unanswered" cell.
        if (cell.unanswered || cell.notApplicable) return cell
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
