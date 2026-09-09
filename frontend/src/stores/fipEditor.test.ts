import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiResponseError } from '@/api/client'
import type { Answer, FipOut } from '@/types/api'

vi.mock('@/api/fips', () => ({
  patchFip: vi.fn(),
  getFip: vi.fn(),
  claimFip: vi.fn(),
  deleteFip: vi.fn(),
}))

import { patchFip } from '@/api/fips'
import { AUTOSAVE_DEBOUNCE_MS, RETRY_DELAYS_MS, answeredCount, useFipEditorStore } from './fipEditor'

const patchFipMock = vi.mocked(patchFip)

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

beforeEach(() => {
  setActivePinia(createPinia())
  vi.useFakeTimers()
  patchFipMock.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

// Criterion 10 (docs/specs/02-core-flows.md §8).
describe('fipEditor store — autosave', () => {
  it('one mutation sets dirty and issues no request before 800ms and exactly one after', async () => {
    patchFipMock.mockResolvedValue(makeFip())
    const store = useFipEditorStore()
    store.setFip(makeFip())

    store.setDeclaration('F1-metadata', 0, { status: 'current' })
    expect(store.dirty).toBe(true)
    expect(patchFipMock).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS - 1)
    expect(patchFipMock).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1)
    expect(patchFipMock).toHaveBeenCalledTimes(1)
  })

  it('three mutations 200ms apart issue exactly one request', async () => {
    patchFipMock.mockResolvedValue(makeFip())
    const store = useFipEditorStore()
    store.setFip(makeFip())

    store.setDeclaration('F1-metadata', 0, { status: 'current' })
    await vi.advanceTimersByTimeAsync(200)
    store.setDeclaration('F1-metadata', 0, { status: 'planned' })
    await vi.advanceTimersByTimeAsync(200)
    store.setDeclaration('F1-metadata', 0, { status: 'none' })

    await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS)
    expect(patchFipMock).toHaveBeenCalledTimes(1)
  })

  it('a mutation during an in-flight request issues exactly one follow-up request after it resolves', async () => {
    const fip = makeFip()
    let resolveFirst!: (value: FipOut) => void
    const pending = new Promise<FipOut>((resolve) => {
      resolveFirst = resolve
    })
    patchFipMock.mockReturnValueOnce(pending)
    patchFipMock.mockResolvedValue(fip)

    const store = useFipEditorStore()
    store.setFip(fip)

    store.setDeclaration('F1-metadata', 0, { status: 'current' })
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS)
    expect(patchFipMock).toHaveBeenCalledTimes(1)
    expect(store.saving).toBe(true)

    // A second mutation while the first request is still in flight.
    store.setDeclaration('F1-metadata', 0, { status: 'planned' })
    expect(store.dirty).toBe(true)

    resolveFirst(fip)
    await vi.advanceTimersByTimeAsync(0)
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()

    expect(patchFipMock).toHaveBeenCalledTimes(2)
  })

  it('flush() sends immediately and clears dirty', async () => {
    patchFipMock.mockResolvedValue(makeFip())
    const store = useFipEditorStore()
    store.setFip(makeFip())

    store.setDeclaration('F1-metadata', 0, { status: 'current' })
    expect(patchFipMock).not.toHaveBeenCalled()

    await store.flush()
    expect(patchFipMock).toHaveBeenCalledTimes(1)
    expect(store.dirty).toBe(false)
  })

  it('a rejected request leaves dirty true, sets lastError, and retries at 2s', async () => {
    patchFipMock.mockRejectedValueOnce(new Error('network error'))
    patchFipMock.mockResolvedValue(makeFip())

    const store = useFipEditorStore()
    store.setFip(makeFip())
    store.setDeclaration('F1-metadata', 0, { status: 'current' })

    await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS)
    expect(patchFipMock).toHaveBeenCalledTimes(1)
    expect(store.dirty).toBe(true)
    expect(store.lastError).toBe('network')

    await vi.advanceTimersByTimeAsync(RETRY_DELAYS_MS[0])
    expect(patchFipMock).toHaveBeenCalledTimes(2)
  })

  // Finding 1: removing a linked DMP must remap every
  // `declaration.dmpEvidence.dmpIndex` that pointed past it, or null the
  // evidence whose plan was dropped — otherwise a stale index either
  // silently points at the wrong plan or 422s on save.
  it('a rejected request with a non-403/409/network 4xx becomes a terminal "invalid" error, stays dirty, and never retries', async () => {
    patchFipMock.mockRejectedValueOnce(
      new ApiResponseError(422, { detail: 'dmp_evidence_invalid_index' })
    )
    patchFipMock.mockResolvedValue(makeFip())

    const store = useFipEditorStore()
    store.setFip(makeFip())
    store.setDeclaration('F1-metadata', 0, { status: 'current' })

    await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS)
    expect(patchFipMock).toHaveBeenCalledTimes(1)
    expect(store.dirty).toBe(true)
    expect(store.lastError).toBe('invalid')
    expect(store.lastErrorDetail).toBe('dmp_evidence_invalid_index')
    expect(store.saveState).toBe('error')

    // No auto-retry schedule for a terminal 4xx (spec 02 §2.3's backoff is
    // for transient/network failures only) — advancing past every backoff
    // delay must not issue a second request on its own.
    await vi.advanceTimersByTimeAsync(RETRY_DELAYS_MS[RETRY_DELAYS_MS.length - 1] + 1000)
    expect(patchFipMock).toHaveBeenCalledTimes(1)

    // The next edit still autosaves normally once the user has changed something.
    store.setDeclaration('F1-metadata', 0, { status: 'planned' })
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS)
    expect(patchFipMock).toHaveBeenCalledTimes(2)
    expect(store.lastError).toBeNull()
  })
})

// Bug: "Add declaration" (QuestionCard.onAdd) creates a bare
// `{ status }` row with neither ferId nor ferFreeText — the backend's
// `Declaration._fer_xor` 422s on that unconditionally. Autosaving it every
// debounce tick until a FER is picked was the reported bug.
describe('fipEditor store — incomplete declarations (neither ferId nor ferFreeText)', () => {
  it('addDeclaration with no ferId/ferFreeText does not mark the FIP dirty or schedule an autosave', async () => {
    const store = useFipEditorStore()
    store.setFip(makeFip())

    store.addDeclaration('F1-metadata', { status: 'current' })
    expect(store.dirty).toBe(false)

    await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS)
    expect(patchFipMock).not.toHaveBeenCalled()
    // The row itself is still there for the participant to fill in.
    expect(store.fip!.answers[0].declarations).toEqual([{ status: 'current' }])
  })

  it('addDeclaration with a ferId does mark dirty and autosaves normally', async () => {
    patchFipMock.mockResolvedValue(makeFip())
    const store = useFipEditorStore()
    store.setFip(makeFip())

    store.addDeclaration('F1-metadata', { ferId: 'https://example.org/fer/a', status: 'current' })
    expect(store.dirty).toBe(true)

    await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS)
    expect(patchFipMock).toHaveBeenCalledTimes(1)
  })

  it('strips an incomplete declaration from the PATCH payload but keeps it in local state', async () => {
    const fip = makeFip({
      answers: [
        {
          questionId: 'F1-metadata',
          comment: null,
          declarations: [{ status: 'current' }],
        },
      ],
    })
    // The server never received the incomplete declaration, so its
    // response naturally omits it from that answer.
    patchFipMock.mockResolvedValue(
      makeFip({ answers: [{ questionId: 'F1-metadata', comment: 'updated', declarations: [] }] })
    )

    const store = useFipEditorStore()
    store.setFip(fip)

    // A second, unrelated edit on the same question marks the FIP dirty and
    // triggers the autosave that used to also ship the incomplete row.
    store.setComment('F1-metadata', 'updated')
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS)

    expect(patchFipMock).toHaveBeenCalledTimes(1)
    const sentAnswers = patchFipMock.mock.calls[0][1].answers as Answer[]
    expect(sentAnswers[0].declarations).toEqual([])

    // Local state still shows the incomplete declaration after the save resolves.
    expect(store.fip!.answers[0].declarations).toEqual([{ status: 'current' }])
    expect(store.dirty).toBe(false)
  })
})

describe('fipEditor store — setRelatedDmps dmpIndex remap', () => {
  function fipWithEvidence(): FipOut {
    const answers: Answer[] = [
      {
        questionId: 'F1-metadata',
        comment: null,
        declarations: [
          { status: 'current', dmpEvidence: { dmpIndex: 1, section: 'Storage' } },
          { status: 'current', dmpEvidence: null },
        ],
      },
    ]
    return makeFip({
      relatedDmps: [
        { url: 'https://example.org/plan-a', system: 'other' },
        { url: 'https://example.org/plan-b', system: 'other' },
        { url: 'https://example.org/plan-c', system: 'other' },
      ],
      answers,
    })
  }

  it('remaps dmpIndex by URL identity when an earlier plan is removed', () => {
    const store = useFipEditorStore()
    store.setFip(fipWithEvidence())

    // Drop plan-a (index 0): plan-b (the evidence's plan) shifts from index 1 to 0.
    store.setRelatedDmps([
      { url: 'https://example.org/plan-b', system: 'other' },
      { url: 'https://example.org/plan-c', system: 'other' },
    ])

    const decl = store.fip!.answers[0].declarations[0]
    expect(decl.dmpEvidence).toEqual({ dmpIndex: 0, section: 'Storage' })
  })

  it('nulls the dmpEvidence whose own plan was removed', () => {
    const store = useFipEditorStore()
    store.setFip(fipWithEvidence())

    // Drop plan-b (index 1): the referencing declaration's evidence is orphaned.
    store.setRelatedDmps([
      { url: 'https://example.org/plan-a', system: 'other' },
      { url: 'https://example.org/plan-c', system: 'other' },
    ])

    const decl = store.fip!.answers[0].declarations[0]
    expect(decl.dmpEvidence).toBeNull()
  })

  it('leaves an untouched declaration (dmpEvidence: null) alone', () => {
    const store = useFipEditorStore()
    store.setFip(fipWithEvidence())

    store.setRelatedDmps([{ url: 'https://example.org/plan-a', system: 'other' }])

    expect(store.fip!.answers[0].declarations[1].dmpEvidence).toBeNull()
  })
})

describe('answeredCount', () => {
  it('returns 0 for []', () => {
    expect(answeredCount([])).toBe(0)
  })

  it('counts an answer whose only declaration has status: "none"', () => {
    expect(
      answeredCount([{ questionId: 'F1-metadata', declarations: [{ status: 'none' }] }])
    ).toBe(1)
  })

  it('ignores an answer with declarations: []', () => {
    expect(answeredCount([{ questionId: 'F1-metadata', declarations: [] }])).toBe(0)
  })
})
