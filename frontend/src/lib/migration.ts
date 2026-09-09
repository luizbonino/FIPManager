/**
 * Pure diff + decision helpers for spec 07 §4.1/§4.2, mirroring
 * `backend/fipm/migration.py` so both implementations can be checked
 * against the same fixtures (§8 AC20). Nothing here performs I/O or holds
 * state — `FipMigrate.vue` gets the actual diff from
 * `GET /api/fips/{id}/migration-preview` (the server recomputes it anyway
 * at migrate time, spec §4.3); `computeMigrationDiff` exists so the two
 * implementations cannot silently drift, and so a future client-side
 * preview is possible without another round trip.
 */
import type {
  Answer,
  KnowledgeModelContent,
  MigrationCounts,
  MigrationDiff,
  MigrationDiffItem,
  MigrationItemStatus,
} from '@/types/api'

interface FlatQuestion {
  id: string
  text: Record<string, string>
  ferType: string | null
  hidden: boolean
}

function flatten(content: KnowledgeModelContent): FlatQuestion[] {
  const out: FlatQuestion[] = []
  for (const section of content.sections) {
    for (const q of section.questions) {
      out.push({ id: q.id, text: q.text ?? {}, ferType: q.ferType ?? null, hidden: !!q.hidden })
    }
  }
  return out
}

function normalizeWhitespace(s: string): string {
  return s.trim().replace(/\s+/g, ' ')
}

/** spec 04 §3.3: `en` is mandatory, so both sides of a diff always have it. */
function enText(q: FlatQuestion): string {
  return q.text.en ?? ''
}

/**
 * spec 07 §4.1: "a question id carrying at least one declaration or a
 * non-empty comment counts as answered". spec 08 §2.3: `notApplicable: true`
 * must also count as non-empty, or such answers are silently dropped on
 * migration instead of landing in `orphanedAnswers`.
 */
function buildAnsweredIndex(answers: Answer[]): Map<string, Answer> {
  const index = new Map<string, Answer>()
  for (const answer of answers) {
    const hasDeclarations = (answer.declarations?.length ?? 0) > 0
    const hasComment = !!(answer.comment && answer.comment.trim())
    const isNotApplicable = answer.notApplicable === true
    if (hasDeclarations || hasComment || isNotApplicable) index.set(answer.questionId, answer)
  }
  return index
}

/**
 * Computes the §4.2 diff document from the two `content` documents and the
 * FIP's `answers`. Never mutates any of its inputs.
 */
export function computeMigrationDiff(
  from: { content: KnowledgeModelContent },
  to: { content: KnowledgeModelContent },
  answers: Answer[]
): MigrationDiff {
  const oldQs = flatten(from.content)
  const newQs = flatten(to.content)
  const oldById = new Map(oldQs.map((q) => [q.id, q]))
  const newById = new Map(newQs.map((q) => [q.id, q]))
  const answeredById = buildAnsweredIndex(answers)
  const declCount = (id: string) => answeredById.get(id)?.declarations.length ?? 0

  // §4.1 `split`: an old id absent from the target while both
  // `<id>-metadata` and `<id>-data` are present in the target and absent
  // from the source. Those two target ids are then folded into one `split`
  // item instead of appearing as their own `added` rows.
  const splitTargetsByOldId = new Map<string, [string, string]>()
  const consumedNewIds = new Set<string>()
  for (const oq of oldQs) {
    if (newById.has(oq.id)) continue
    const metaId = `${oq.id}-metadata`
    const dataId = `${oq.id}-data`
    if (newById.has(metaId) && newById.has(dataId) && !oldById.has(metaId) && !oldById.has(dataId)) {
      splitTargetsByOldId.set(oq.id, [metaId, dataId])
      consumedNewIds.add(metaId)
      consumedNewIds.add(dataId)
    }
  }

  const items: MigrationDiffItem[] = []

  // Pass 1: target order (spec §4.1: "Iterate the target in section/question order…").
  for (const nq of newQs) {
    if (consumedNewIds.has(nq.id)) continue
    const oq = oldById.get(nq.id)
    if (oq) {
      const flags: string[] = []
      const oldText = enText(oq)
      const newText = enText(nq)
      if (normalizeWhitespace(oldText) !== normalizeWhitespace(newText)) flags.push('text-changed')
      if (oq.ferType !== nq.ferType) flags.push('fer-type-changed')
      const status: MigrationItemStatus = nq.hidden ? 'hidden' : 'unchanged'
      items.push({
        status,
        oldQuestionId: oq.id,
        newQuestionId: nq.id,
        oldText,
        newText,
        oldFerType: oq.ferType,
        newFerType: nq.ferType,
        flags,
        answered: answeredById.has(nq.id),
        declarationCount: declCount(nq.id),
        decision: null,
      })
    } else {
      items.push({
        status: 'added',
        oldQuestionId: null,
        newQuestionId: nq.id,
        newText: enText(nq),
        newFerType: nq.ferType,
        flags: [],
        answered: false,
        declarationCount: 0,
        decision: null,
      })
    }
  }

  // Pass 2: "…then the source's leftovers" — ids gone from the target.
  for (const oq of oldQs) {
    if (newById.has(oq.id)) continue
    const answered = answeredById.has(oq.id)
    const splitInto = splitTargetsByOldId.get(oq.id)
    if (splitInto) {
      items.push({
        status: 'split',
        oldQuestionId: oq.id,
        newQuestionId: null,
        oldText: enText(oq),
        flags: [],
        answered,
        declarationCount: declCount(oq.id),
        splitInto: [...splitInto],
        decision: answered
          ? { kind: 'splitCopies', options: [...splitInto], default: [...splitInto] }
          : null,
      })
      continue
    }
    if (!answered) continue // an unanswered, non-split leftover raises no item to review.
    const removedFerType = oq.ferType
    const unansweredNonHidden = newQs.filter((q) => !q.hidden && !answeredById.has(q.id))
    let options = removedFerType
      ? unansweredNonHidden.filter((q) => q.ferType === removedFerType).map((q) => q.id)
      : unansweredNonHidden.map((q) => q.id)
    if (options.length === 0 && removedFerType) {
      options = unansweredNonHidden.map((q) => q.id)
    }
    items.push({
      status: 'removed',
      oldQuestionId: oq.id,
      newQuestionId: null,
      oldText: enText(oq),
      flags: [],
      answered: true,
      declarationCount: declCount(oq.id),
      decision: { kind: 'orphanReassign', options, default: null },
    })
  }

  return {
    diffVersion: 1,
    generatedAt: new Date().toISOString(),
    from: { id: from.content.id, version: from.content.version },
    to: { id: to.content.id, version: to.content.version, changelog: to.content.changelog ?? [] },
    counts: computeCounts(items),
    items,
  }
}

function computeCounts(items: MigrationDiffItem[]): MigrationCounts {
  const counts: MigrationCounts = {
    unchanged: 0,
    added: 0,
    removed: 0,
    hidden: 0,
    split: 0,
    textChanged: 0,
    ferTypeChanged: 0,
    answersKept: 0,
    answersOrphaned: 0,
    decisionsRequired: 0,
  }
  for (const item of items) {
    counts[item.status] += 1
    if (item.flags.includes('text-changed')) counts.textChanged += 1
    if (item.flags.includes('fer-type-changed')) counts.ferTypeChanged += 1
    if (item.decision) counts.decisionsRequired += 1
    if (item.status === 'removed') {
      counts.answersOrphaned += 1
    } else if (item.answered && (item.status === 'unchanged' || item.status === 'hidden' || item.status === 'split')) {
      // Defaults keep the answer: `unchanged`/`hidden` verbatim, `split`
      // copied to both targets (spec §4.1's default effect).
      counts.answersKept += 1
    }
  }
  return counts
}

// ---------------------------------------------------------------------------
// Decisions (spec §4.2/§4.3): `FipMigrate.vue`'s local state as the reviewer
// changes a split/removed row away from its default.
// ---------------------------------------------------------------------------

/** Per-item decision state the migrate view edits: `oldQuestionId -> chosen targets/target`. */
export interface MigrationDecisionsState {
  splitCopies: Record<string, string[]>
  orphanReassign: Record<string, string | null>
}

/** The §4.2 defaults: split -> both targets, removed -> orphaned (`null`, no reassignment). */
export function defaultDecisions(diff: MigrationDiff): MigrationDecisionsState {
  const state: MigrationDecisionsState = { splitCopies: {}, orphanReassign: {} }
  for (const item of diff.items) {
    if (!item.decision || !item.oldQuestionId) continue
    if (item.decision.kind === 'splitCopies') {
      state.splitCopies[item.oldQuestionId] = [...item.decision.default]
    } else {
      state.orphanReassign[item.oldQuestionId] = item.decision.default
    }
  }
  return state
}

/** `POST …/migrate`'s `decisions` body (spec §4.3), built from the current state. */
export function buildMigrateDecisions(
  diff: MigrationDiff,
  state: MigrationDecisionsState
): { splitCopies?: Record<string, string[]>; orphanReassign?: Record<string, string> } {
  const splitCopies: Record<string, string[]> = {}
  const orphanReassign: Record<string, string> = {}
  for (const item of diff.items) {
    if (!item.decision || !item.oldQuestionId) continue
    if (item.decision.kind === 'splitCopies') {
      splitCopies[item.oldQuestionId] = state.splitCopies[item.oldQuestionId] ?? item.decision.default
    } else {
      const chosen = state.orphanReassign[item.oldQuestionId]
      if (chosen) orphanReassign[item.oldQuestionId] = chosen
    }
  }
  const body: { splitCopies?: Record<string, string[]>; orphanReassign?: Record<string, string> } = {}
  if (Object.keys(splitCopies).length > 0) body.splitCopies = splitCopies
  if (Object.keys(orphanReassign).length > 0) body.orphanReassign = orphanReassign
  return body
}

/** The review page's summary line ("17 answers kept, 1 orphaned, 2 decisions"), live as decisions change. */
export function summarizeDecisions(
  diff: MigrationDiff,
  state: MigrationDecisionsState
): { kept: number; orphaned: number; decisions: number } {
  let kept = 0
  let orphaned = 0
  let decisions = 0
  for (const item of diff.items) {
    if (!item.decision || !item.oldQuestionId) {
      if (item.answered && (item.status === 'unchanged' || item.status === 'hidden')) kept += 1
      continue
    }
    decisions += 1
    if (item.decision.kind === 'splitCopies') {
      const chosen = state.splitCopies[item.oldQuestionId] ?? item.decision.default
      if (chosen.length > 0) kept += 1
      else orphaned += 1
    } else {
      const chosen = state.orphanReassign[item.oldQuestionId]
      if (chosen) kept += 1
      else orphaned += 1
    }
  }
  return { kept, orphaned, decisions }
}
