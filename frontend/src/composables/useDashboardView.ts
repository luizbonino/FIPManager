/**
 * Shared fetch/poll/error orchestration for the six dashboard views (spec
 * 13 §5.3/§7, AC-5): a `304` reuses the held envelope, a `202
 * snapshot_pending` polls at `Retry-After` up to 20 attempts rendering the
 * `stalePayload` underneath, and any thrown `ApiResponseError` is captured
 * as a typed error state instead of an unhandled rejection. Not part of
 * the spec's own file list — an internal helper so the poll/etag/error
 * logic exists once instead of six times.
 */
import { onBeforeUnmount, ref, shallowRef } from 'vue'
import { ApiResponseError } from '@/api/client'
import type { DashboardEnvelope } from '@/types/dashboard'
import type { DashboardResult } from '@/api/dashboard'

const MAX_POLL_ATTEMPTS = 20

export function useDashboardView<T>() {
  const envelope = shallowRef<DashboardEnvelope<T> | null>(null)
  const loading = ref(true)
  const pending = ref(false)
  const pendingAttempt = ref(0)
  const stalePayload = shallowRef<T | null>(null)
  const stalePayloadDegraded = ref(false)
  const errorCode = ref<string | null>(null)
  const errorBody = ref<Record<string, unknown> | null>(null)

  let etag: string | null = null
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let requestSeq = 0

  function clearPoll() {
    if (pollTimer) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  async function step(fetcher: (ifNoneMatch?: string | null) => Promise<DashboardResult<T>>, seq: number) {
    try {
      const result = await fetcher(etag)
      if (seq !== requestSeq) return
      if (result.status === 'notModified') {
        loading.value = false
        pending.value = false
        return
      }
      if (result.status === 'pending') {
        loading.value = false
        pending.value = true
        stalePayload.value = result.stalePayload
        stalePayloadDegraded.value = result.degraded
        pendingAttempt.value += 1
        if (pendingAttempt.value < MAX_POLL_ATTEMPTS) {
          pollTimer = setTimeout(() => step(fetcher, seq), Math.max(1, result.retryAfter) * 1000)
        }
        return
      }
      envelope.value = result.envelope
      etag = result.envelope.etag
      pending.value = false
      loading.value = false
    } catch (err) {
      if (seq !== requestSeq) return
      loading.value = false
      pending.value = false
      if (err instanceof ApiResponseError) {
        errorCode.value = err.data.detail
        errorBody.value = err.data as unknown as Record<string, unknown>
      } else {
        errorCode.value = 'network_error'
      }
    }
  }

  async function run(fetcher: (ifNoneMatch?: string | null) => Promise<DashboardResult<T>>) {
    const seq = ++requestSeq
    clearPoll()
    loading.value = true
    pending.value = false
    pendingAttempt.value = 0
    errorCode.value = null
    errorBody.value = null
    etag = null
    await step(fetcher, seq)
  }

  onBeforeUnmount(clearPoll)

  return {
    envelope,
    loading,
    pending,
    pendingAttempt,
    maxPollAttempts: MAX_POLL_ATTEMPTS,
    stalePayload,
    stalePayloadDegraded,
    errorCode,
    errorBody,
    run,
  }
}
