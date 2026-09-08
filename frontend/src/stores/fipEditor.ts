import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { ApiResponseError } from '@/api/client'
import { listFers } from '@/api/fers'
import { claimFip, deleteFip as apiDeleteFip, getFip, patchFip } from '@/api/fips'
import { getKnowledgeModel } from '@/api/knowledgeModels'
import { answeredCount } from '@/lib/progress'
import { clearToken, getToken } from '@/lib/editTokens'
import { useAuthStore } from '@/stores/auth'
import type {
  Answer,
  Community,
  Declaration,
  FerOut,
  FipOut,
  FipPatchRequest,
  KnowledgeModelOut,
  Visibility,
} from '@/types/api'

/**
 * Debounce delay between the last mutation and the autosave PATCH
 * (spec 02 §2.3). A module constant, not inlined, so tests can drive it
 * with fake timers.
 */
export const AUTOSAVE_DEBOUNCE_MS = 800

/** Backoff schedule for a failed autosave before falling back to manual Retry (spec 02 §2.3). */
export const RETRY_DELAYS_MS = [2000, 5000, 15000]

export type SaveState = 'saved' | 'saving' | 'unsaved' | 'error'
export type SaveErrorKind = 'network' | 'forbidden' | 'session_closed' | null

export const useFipEditorStore = defineStore('fipEditor', () => {
  const fip = ref<FipOut | null>(null)
  const km = ref<KnowledgeModelOut | null>(null)
  const fers = ref<Record<string, FerOut>>({})

  const dirty = ref(false)
  const saving = ref(false)
  const lastSavedAt = ref<Date | null>(null)
  const lastError = ref<SaveErrorKind>(null)

  const loading = ref(false)
  const notFound = ref(false)
  /** Set on a 403 or 409 `session_closed` save response (spec 02 §2.3): forces read-only. */
  const forcedReadOnly = ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  /**
   * Minimal addition beyond spec 02 §6.4's listed store API: exposed (with
   * `retryExhausted` below) so `SaveIndicator` can distinguish the
   * auto-retrying "Not saved — retrying" message (§2.3) from the terminal
   * "Not saved" + manual Retry once the fixed backoff schedule is spent.
   */
  const retryAttempt = ref(0)
  let inFlight = false
  let pagehideCleanup: (() => void) | null = null

  /** `SaveIndicator` (spec 02 §2.3): always one of these four. */
  const saveState = computed<SaveState>(() => {
    if (lastError.value) return 'error'
    if (saving.value) return 'saving'
    if (dirty.value) return 'unsaved'
    return 'saved'
  })

  /**
   * `canEdit` (spec 02 §2.2): a stored edit token for this FIP, or
   * ownership. A device without either sees the read-only view even for a
   * `link`-visible FIP — "second device is read-only".
   */
  const canEdit = computed(() => {
    if (!fip.value || forcedReadOnly.value) return false
    const auth = useAuthStore()
    if (fip.value.ownerId && auth.user && fip.value.ownerId === auth.user.id) return true
    return !!getToken(fip.value.id)
  })

  const readOnly = computed(() => !canEdit.value)

  /** True once the fixed backoff schedule (§2.3) has been exhausted at least once. */
  const retryExhausted = computed(() => retryAttempt.value >= RETRY_DELAYS_MS.length)

  function clearTimers() {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    if (retryTimer) {
      clearTimeout(retryTimer)
      retryTimer = null
    }
  }

  function scheduleSave() {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      void performSave()
    }, AUTOSAVE_DEBOUNCE_MS)
  }

  function markDirty() {
    dirty.value = true
    scheduleSave()
  }

  async function performSave(): Promise<void> {
    if (!fip.value || inFlight || !dirty.value) return
    inFlight = true
    saving.value = true
    const current = fip.value
    const payload: FipPatchRequest = {
      answers: current.answers,
      community: current.community ?? undefined,
      language: current.language,
    }
    dirty.value = false

    try {
      const token = getToken(current.id) ?? undefined
      const updated = await patchFip(current.id, payload, token)
      fip.value = updated
      lastError.value = null
      lastSavedAt.value = new Date()
      retryAttempt.value = 0
      saving.value = false
      inFlight = false
      // Mutations that arrived while this request was in flight are
      // coalesced (spec 02 §2.3): fire once more, immediately, if still dirty.
      if (dirty.value) {
        void performSave()
      }
    } catch (err) {
      saving.value = false
      inFlight = false
      dirty.value = true
      if (err instanceof ApiResponseError && err.status === 403) {
        lastError.value = 'forbidden'
        forcedReadOnly.value = true
      } else if (err instanceof ApiResponseError && err.status === 409) {
        lastError.value = 'session_closed'
        forcedReadOnly.value = true
      } else {
        lastError.value = 'network'
        scheduleRetry()
      }
    }
  }

  function scheduleRetry() {
    const delay = RETRY_DELAYS_MS[Math.min(retryAttempt.value, RETRY_DELAYS_MS.length - 1)]
    retryAttempt.value += 1
    if (retryTimer) clearTimeout(retryTimer)
    retryTimer = setTimeout(() => {
      retryTimer = null
      void performSave()
    }, delay)
  }

  /** Manual "Retry" after the backoff schedule is exhausted (spec 02 §2.3). */
  function retry() {
    if (retryTimer) {
      clearTimeout(retryTimer)
      retryTimer = null
    }
    retryAttempt.value = 0
    lastError.value = null
    void performSave()
  }

  /**
   * Flush immediately, bypassing the debounce (spec 02 §2.3): section
   * collapse, text-field blur, the router leave guard.
   */
  async function flush(): Promise<void> {
    clearTimers()
    await performSave()
  }

  function attachPagehideFlush() {
    if (typeof window === 'undefined') return
    pagehideCleanup?.()
    const handler = () => {
      if (!dirty.value || !fip.value) return
      const token = getToken(fip.value.id)
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      if (token) headers['X-Edit-Token'] = token
      const body = JSON.stringify({
        answers: fip.value.answers,
        community: fip.value.community,
        language: fip.value.language,
      })
      // `sendBeacon` cannot carry the `X-Edit-Token` header, hence `fetch` with `keepalive`.
      void fetch(`/api/fips/${fip.value.id}`, {
        method: 'PATCH',
        headers,
        body,
        keepalive: true,
        credentials: 'include',
      })
    }
    window.addEventListener('pagehide', handler)
    pagehideCleanup = () => window.removeEventListener('pagehide', handler)
  }

  // ---------------------------------------------------------------------
  // Loading
  // ---------------------------------------------------------------------

  /** Load sequence per spec 02 §2.2: the FIP first, then its knowledge model and the FER catalogue. */
  async function load(id: string): Promise<void> {
    clearTimers()
    loading.value = true
    notFound.value = false
    forcedReadOnly.value = false
    lastError.value = null
    dirty.value = false
    fip.value = null
    km.value = null
    fers.value = {}

    const token = getToken(id) ?? undefined
    const fersPromise = listFers({ limit: 500 }).catch(() => ({ items: [], total: 0 }))

    try {
      const loaded = await getFip(id, token)
      fip.value = loaded
      const [kmResult, fersResult] = await Promise.all([
        getKnowledgeModel(loaded.questionnaireId, loaded.questionnaireVersion),
        fersPromise,
      ])
      km.value = kmResult
      fers.value = Object.fromEntries(fersResult.items.map((f) => [f.id, f]))
      attachPagehideFlush()
    } catch (err) {
      if (err instanceof ApiResponseError && err.status === 404) {
        notFound.value = true
      }
      throw err
    } finally {
      loading.value = false
    }
  }

  /** Hydrate directly with an already-fetched FIP (e.g. right after `POST /api/fips`), no network call. */
  function setFip(value: FipOut): void {
    fip.value = value
    dirty.value = false
    lastError.value = null
    forcedReadOnly.value = false
  }

  // ---------------------------------------------------------------------
  // Mutations (spec 02 §6.4): each marks the FIP dirty and schedules a save.
  // ---------------------------------------------------------------------

  function findAnswer(questionId: string): Answer | undefined {
    return fip.value?.answers.find((a) => a.questionId === questionId)
  }

  function ensureAnswer(questionId: string): Answer | null {
    if (!fip.value) return null
    let answer = findAnswer(questionId)
    if (!answer) {
      answer = { questionId, declarations: [], comment: null }
      fip.value.answers = [...fip.value.answers, answer]
    }
    return answer
  }

  function setDeclaration(questionId: string, index: number, patch: Partial<Declaration>): void {
    const answer = ensureAnswer(questionId)
    if (!answer) return
    const existing = answer.declarations[index]
    const base: Declaration = existing ?? { status: 'current' }
    const merged: Declaration = { ...base, ...patch }
    const declarations = [...answer.declarations]
    declarations[index] = merged
    answer.declarations = declarations
    markDirty()
  }

  function addDeclaration(questionId: string, declaration: Declaration): void {
    const answer = ensureAnswer(questionId)
    if (!answer) return
    answer.declarations = [...answer.declarations, declaration]
    markDirty()
  }

  function removeDeclaration(questionId: string, index: number): void {
    const answer = ensureAnswer(questionId)
    if (!answer) return
    answer.declarations = answer.declarations.filter((_, i) => i !== index)
    markDirty()
  }

  function setComment(questionId: string, comment: string | null): void {
    const answer = ensureAnswer(questionId)
    if (!answer) return
    answer.comment = comment
    markDirty()
  }

  function setCommunity(patch: Partial<Community>): void {
    if (!fip.value) return
    fip.value.community = { links: [], ...fip.value.community, ...patch }
    markDirty()
  }

  /** Switching the locale while `canEdit` also sets `fip.language` (spec 02 §2.3), so exports resolve correctly. */
  function setLanguage(language: string): void {
    if (!fip.value) return
    fip.value.language = language
    markDirty()
  }

  /** `VisibilitySelect` PATCHes immediately, not debounced (spec 02 §3). */
  async function updateVisibility(visibility: Visibility): Promise<void> {
    if (!fip.value) return
    const token = getToken(fip.value.id) ?? undefined
    const updated = await patchFip(fip.value.id, { visibility }, token)
    fip.value = updated
  }

  async function claim(): Promise<void> {
    if (!fip.value) return
    const token = getToken(fip.value.id)
    if (!token) return
    const updated = await claimFip(fip.value.id, token)
    fip.value = updated
    clearToken(updated.id)
  }

  async function remove(): Promise<void> {
    if (!fip.value) return
    const token = getToken(fip.value.id) ?? undefined
    await apiDeleteFip(fip.value.id, token)
  }

  return {
    fip,
    km,
    fers,
    dirty,
    saving,
    lastSavedAt,
    lastError,
    saveState,
    loading,
    notFound,
    forcedReadOnly,
    canEdit,
    readOnly,
    retryExhausted,
    load,
    setFip,
    setDeclaration,
    addDeclaration,
    removeDeclaration,
    setComment,
    setCommunity,
    setLanguage,
    updateVisibility,
    claim,
    remove,
    flush,
    scheduleSave,
    retry,
  }
})

// Re-exported so callers (e.g. SessionFipList, which never loads the full
// editor store) can compute progress from a bare `answers` array (spec 02 §6.4).
export { answeredCount }
