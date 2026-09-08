import { del, get, patch, post } from './client'
import type { FipCreateRequest, FipExportDoc, FipOut, FipPatchRequest } from '@/types/api'

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

/**
 * Minimal addition beyond spec 02 §6.4's listed API: `FipRead.vue`'s single
 * data source is this same export document (spec 02 §4.3), fetched (not
 * just linked) so the read view needs no separate knowledge-model or FER
 * requests.
 */
export function getFipExport(id: string) {
  return get<FipExportDoc>(`/fips/${id}/export.json`)
}

/** Plain `<a href>` targets (spec 02 §2.4) — `Content-Disposition: attachment` already set server-side. */
export function fipExportJsonUrl(id: string): string {
  return `/api/fips/${id}/export.json`
}

export function fipExportCsvUrl(id: string): string {
  return `/api/fips/${id}/export.csv`
}

/** `GET /api/fips/{id}/export.ttl` (spec 03 §2.5). */
export function fipExportTtlUrl(id: string): string {
  return `/api/fips/${id}/export.ttl`
}

/** `GET /api/fips/{id}/export.jsonld` (spec 03 §2.5). */
export function fipExportJsonldUrl(id: string): string {
  return `/api/fips/${id}/export.jsonld`
}

export function fipReadUrl(id: string): string {
  return `/fips/${id}`
}
