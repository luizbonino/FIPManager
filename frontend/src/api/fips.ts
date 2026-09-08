import { del, get, patch, post } from './client'
import type { FipCreateRequest, FipOut, FipPatchRequest } from '@/types/api'

export function createFip(body: FipCreateRequest) {
  return post<FipOut>('/fips', body)
}

export function getFip(id: string, editToken?: string) {
  return get<FipOut>(`/fips/${id}`, editToken)
}

export function patchFip(id: string, body: FipPatchRequest, editToken?: string) {
  return patch<FipOut>(`/fips/${id}`, body, editToken)
}

export function deleteFip(id: string, editToken?: string) {
  return del<void>(`/fips/${id}`, editToken)
}

export function claimFip(id: string, editToken: string) {
  return post<FipOut>(`/fips/${id}/claim`, undefined, editToken)
}

/** Plain `<a href>` targets (spec 02 §2.4) — `Content-Disposition: attachment` already set server-side. */
export function fipExportJsonUrl(id: string): string {
  return `/api/fips/${id}/export.json`
}

export function fipExportCsvUrl(id: string): string {
  return `/api/fips/${id}/export.csv`
}

export function fipReadUrl(id: string): string {
  return `/fips/${id}`
}
