import { get, patch, post } from './client'
import type {
  FipOut,
  ListOut,
  SessionCreateRequest,
  SessionOut,
  SessionPatchRequest,
  SessionPublicOut,
} from '@/types/api'

export function createSession(body: SessionCreateRequest) {
  return post<SessionOut>('/sessions', body)
}

export function getSession(id: string) {
  return get<SessionOut>(`/sessions/${id}`)
}

export function getSessionByCode(joinCode: string) {
  return get<SessionPublicOut>(`/sessions/by-code/${joinCode}`)
}

export function patchSession(id: string, body: SessionPatchRequest) {
  return patch<SessionOut>(`/sessions/${id}`, body)
}

export function listSessionFips(id: string) {
  return get<ListOut<FipOut>>(`/sessions/${id}/fips`)
}

/** Plain `<a href>` targets (spec 02 §5.3) — `Content-Disposition: attachment` already set server-side. */
export function sessionExportJsonUrl(id: string): string {
  return `/api/sessions/${id}/export.json`
}

export function sessionExportCsvUrl(id: string): string {
  return `/api/sessions/${id}/export.csv`
}
