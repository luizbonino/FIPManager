import { get, post } from './client'
import type { AdminFerOut, AdminMergeResult, AdminUserOut, ListOut } from '@/types/api'

// spec 05 §1 — `/api/admin/*`, `require_admin_404` (404 for anonymous and
// signed-in non-admins alike, so the prefix never confirms its own existence).

export function listAdminUsers(params?: { q?: string; limit?: number; offset?: number }) {
  const qs = new URLSearchParams()
  if (params?.q) qs.set('q', params.q)
  if (params?.limit !== undefined) qs.set('limit', String(params.limit))
  if (params?.offset !== undefined) qs.set('offset', String(params.offset))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return get<ListOut<AdminUserOut>>(`/admin/users${suffix}`)
}

/** Returned **once** — the plaintext appears in no log line (spec 05 §1). */
export function resetUserPassword(userId: string) {
  return post<{ temporaryPassword: string }>(`/admin/users/${userId}/reset-password`)
}

export function listAdminFers(params?: { pending?: boolean; q?: string; limit?: number; offset?: number }) {
  const qs = new URLSearchParams()
  if (params?.pending) qs.set('pending', '1')
  if (params?.q) qs.set('q', params.q)
  if (params?.limit !== undefined) qs.set('limit', String(params.limit))
  if (params?.offset !== undefined) qs.set('offset', String(params.offset))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return get<ListOut<AdminFerOut>>(`/admin/fers${suffix}`)
}

export function promoteFer(ferId: string) {
  return post<AdminFerOut>(`/admin/fers/${ferId}/promote`)
}

export function mergeFer(ferId: string, targetFerId: string) {
  return post<AdminMergeResult>(`/admin/fers/${ferId}/merge`, { targetFerId })
}
