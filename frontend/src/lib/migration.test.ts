import { describe, expect, it } from 'vitest'
import {
  buildMigrateDecisions,
  computeMigrationDiff,
  defaultDecisions,
  summarizeDecisions,
} from './migration'
import { answers, newContent, oldContent } from './__fixtures__/migrationDiff'

function deepFreeze<T>(value: T): T {
  if (value && typeof value === 'object') {
    Object.values(value as object).forEach(deepFreeze)
    Object.freeze(value)
  }
  return value
}

function itemFor(diff: ReturnType<typeof computeMigrationDiff>, id: string) {
  return diff.items.find((i) => i.oldQuestionId === id || i.newQuestionId === id)
}

// Criterion 20: `lib/migration.ts` computes the same statuses, flags and
// counts as the backend on a shared fixture pair, never mutates its
// inputs, and yields an all-`unchanged` diff for identical documents.
describe('computeMigrationDiff (spec 07 §4.1/§4.2)', () => {
  it('assigns unchanged/text-changed to F1, split to F2, hidden to F3, removed to A2, added to R1.3-data', () => {
    const diff = computeMigrationDiff({ content: oldContent }, { content: newContent }, answers)

    const f1 = itemFor(diff, 'F1')!
    expect(f1.status).toBe('unchanged')
    expect(f1.flags).toEqual(['text-changed'])
    expect(f1.answered).toBe(true)

    const f2 = diff.items.find((i) => i.oldQuestionId === 'F2')!
    expect(f2.status).toBe('split')
    expect(f2.splitInto).toEqual(['F2-metadata', 'F2-data'])
    expect(f2.answered).toBe(true)
    expect(f2.decision).toEqual({ kind: 'splitCopies', options: ['F2-metadata', 'F2-data'], default: ['F2-metadata', 'F2-data'] })

    const f3 = itemFor(diff, 'F3')!
    expect(f3.status).toBe('hidden')
    expect(f3.flags).toEqual([])
    expect(f3.answered).toBe(true)

    const a2 = diff.items.find((i) => i.oldQuestionId === 'A2')!
    expect(a2.status).toBe('removed')
    expect(a2.answered).toBe(true)
    expect(a2.decision).toEqual({
      kind: 'orphanReassign',
      // No target question shares A2's `repository` ferType, so the picker
      // falls back to every unanswered, non-hidden target id (spec §4.2).
      options: ['F2-metadata', 'F2-data', 'R1.3-data'],
      default: null,
    })

    const r13 = diff.items.find((i) => i.newQuestionId === 'R1.3-data')!
    expect(r13.status).toBe('added')
    expect(r13.answered).toBe(false)
  })

  it('computes counts matching the item statuses/flags, with decisionsRequired counting only decidable items', () => {
    const diff = computeMigrationDiff({ content: oldContent }, { content: newContent }, answers)

    expect(diff.counts).toEqual({
      unchanged: 1,
      added: 1,
      removed: 1,
      hidden: 1,
      split: 1,
      textChanged: 1,
      ferTypeChanged: 0,
      answersKept: 3, // F1 (unchanged), F3 (hidden), F2 (split, default keeps both)
      answersOrphaned: 1, // A2 (removed, default orphans)
      decisionsRequired: 2, // F2 (split) + A2 (removed)
    })
  })

  it('never mutates its inputs', () => {
    const frozenOld = deepFreeze(structuredClone(oldContent))
    const frozenNew = deepFreeze(structuredClone(newContent))
    const frozenAnswers = deepFreeze(structuredClone(answers))

    expect(() =>
      computeMigrationDiff({ content: frozenOld }, { content: frozenNew }, frozenAnswers)
    ).not.toThrow()
  })

  it('yields an all-unchanged diff for identical documents', () => {
    const diff = computeMigrationDiff({ content: oldContent }, { content: oldContent }, answers)

    expect(diff.items.every((i) => i.status === 'unchanged')).toBe(true)
    expect(diff.items.every((i) => i.flags.length === 0)).toBe(true)
    expect(diff.counts.unchanged).toBe(diff.items.length)
    expect(diff.counts.added + diff.counts.removed + diff.counts.hidden + diff.counts.split).toBe(0)
  })
})

describe('decision helpers', () => {
  it('defaultDecisions applies split -> both, removed -> null (orphaned)', () => {
    const diff = computeMigrationDiff({ content: oldContent }, { content: newContent }, answers)
    const state = defaultDecisions(diff)

    expect(state.splitCopies.F2).toEqual(['F2-metadata', 'F2-data'])
    expect(state.orphanReassign.A2).toBeNull()
  })

  it('buildMigrateDecisions reflects a narrowed split choice and a chosen reassignment', () => {
    const diff = computeMigrationDiff({ content: oldContent }, { content: newContent }, answers)
    const state = defaultDecisions(diff)
    state.splitCopies.F2 = ['F2-metadata']
    state.orphanReassign.A2 = 'F2-data'

    expect(buildMigrateDecisions(diff, state)).toEqual({
      splitCopies: { F2: ['F2-metadata'] },
      orphanReassign: { A2: 'F2-data' },
    })
  })

  it('buildMigrateDecisions omits an orphanReassign key left at the default (kept orphaned)', () => {
    const diff = computeMigrationDiff({ content: oldContent }, { content: newContent }, answers)
    const state = defaultDecisions(diff)

    const body = buildMigrateDecisions(diff, state)
    expect(body.orphanReassign).toBeUndefined()
    expect(body.splitCopies).toEqual({ F2: ['F2-metadata', 'F2-data'] })
  })

  it('summarizeDecisions updates kept/orphaned as a split choice narrows to none', () => {
    const diff = computeMigrationDiff({ content: oldContent }, { content: newContent }, answers)
    const state = defaultDecisions(diff)

    expect(summarizeDecisions(diff, state)).toEqual({ kept: 3, orphaned: 1, decisions: 2 })

    state.splitCopies.F2 = []
    expect(summarizeDecisions(diff, state)).toEqual({ kept: 2, orphaned: 2, decisions: 2 })
  })
})
