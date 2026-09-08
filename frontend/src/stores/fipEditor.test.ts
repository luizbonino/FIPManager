import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { FipOut } from '@/types/api'

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
