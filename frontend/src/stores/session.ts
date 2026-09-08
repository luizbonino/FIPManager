import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  createSession as apiCreateSession,
  getSession,
  getSessionByCode,
  listSessionFips,
  patchSession,
} from '@/api/sessions'
import type { FipOut, SessionCreateRequest, SessionOut, SessionPublicOut } from '@/types/api'

/** Live-refresh interval for `SessionFipList` (spec 02 §4.2): no websockets in v1. */
export const POLL_INTERVAL_MS = 10_000

export const useSessionStore = defineStore('session', () => {
  /** The owner-only, full session (`GET /api/sessions/{id}`). */
  const session = ref<SessionOut | null>(null)
  /** The pre-join, public metadata (`GET /api/sessions/by-code/{joinCode}`). */
  const publicSession = ref<SessionPublicOut | null>(null)
  const fips = ref<FipOut[]>([])

  const loading = ref(false)
  const error = ref<string | null>(null)
  /** A failed poll shows a "reconnecting" dot and does not clear the list (spec 02 §4.2). */
  const reconnecting = ref(false)

  let pollTimer: ReturnType<typeof setInterval> | null = null
  let pollInFlight = false

  async function create(body: SessionCreateRequest): Promise<SessionOut> {
    const created = await apiCreateSession(body)
    session.value = created
    return created
  }

  async function load(id: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      session.value = await getSession(id)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'load_failed'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function loadByCode(joinCode: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      publicSession.value = await getSessionByCode(joinCode)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'load_failed'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function loadFips(): Promise<void> {
    if (!session.value) return
    try {
      const result = await listSessionFips(session.value.id)
      fips.value = result.items
      reconnecting.value = false
    } catch {
      reconnecting.value = true
    }
  }

  async function close(): Promise<void> {
    if (!session.value) return
    session.value = await patchSession(session.value.id, { status: 'closed' })
  }

  /** `setInterval` 10s, started `onMounted`; paused while `document.hidden`, skipped while a poll is in flight. */
  function startPolling(intervalMs = POLL_INTERVAL_MS): void {
    stopPolling()
    pollTimer = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return
      if (pollInFlight) return
      pollInFlight = true
      void loadFips().finally(() => {
        pollInFlight = false
      })
    }, intervalMs)
  }

  function stopPolling(): void {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  return {
    session,
    publicSession,
    fips,
    loading,
    error,
    reconnecting,
    create,
    load,
    loadByCode,
    loadFips,
    startPolling,
    stopPolling,
    close,
  }
})
