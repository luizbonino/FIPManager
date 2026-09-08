import { get } from './client'
import type { FerOut, ListOut } from '@/types/api'

export interface ListFersParams {
  type?: string
  q?: string
  source?: string
  limit?: number
  offset?: number
}

/**
 * `GET /api/fers`. Spec 02 §2.2: the editor fetches `limit=500` once (the
 * whole seed catalogue) and filters client-side; only when `total > 500`
 * does the picker fall back to a per-keystroke, debounced call with `type`/`q`.
 */
export function listFers(params?: ListFersParams) {
  const qs = new URLSearchParams()
  if (params?.type) qs.set('type', params.type)
  if (params?.q) qs.set('q', params.q)
  if (params?.source) qs.set('source', params.source)
  if (params?.limit !== undefined) qs.set('limit', String(params.limit))
  if (params?.offset !== undefined) qs.set('offset', String(params.offset))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return get<ListOut<FerOut>>(`/fers${suffix}`)
}
