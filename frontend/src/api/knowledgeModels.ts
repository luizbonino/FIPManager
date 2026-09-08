import { del, get, getWithEtag, patch, post, putWithEtag } from './client'
import type {
  KnowledgeModelContent,
  KnowledgeModelOut,
  KnowledgeModelSummary,
  KnowledgeModelVersionEntry,
  LangMap,
  ListOut,
} from '@/types/api'

// Spec 04 §3 — the 12 knowledge-model endpoints. Bodies/responses camelCase.

/** #1 `GET /knowledge-models`. */
export function listKnowledgeModels(params?: { status?: string; q?: string; mine?: boolean }) {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  if (params?.q) qs.set('q', params.q)
  if (params?.mine) qs.set('mine', 'true')
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return get<ListOut<KnowledgeModelSummary>>(`/knowledge-models${suffix}`)
}

/** #2 `GET /knowledge-models/{id}/versions`. */
export function listKnowledgeModelVersions(id: string) {
  return get<ListOut<KnowledgeModelVersionEntry>>(`/knowledge-models/${id}/versions`)
}

/**
 * #3 `GET /knowledge-models/{id}/{version}`. The body also carries the
 * `ETag` response header (`content_sha256`) needed for the editor's
 * `If-Match`; callers that don't need it can ignore `.etag`.
 */
export async function getKnowledgeModel(id: string, version: string): Promise<KnowledgeModelOut> {
  const { data, etag } = await getWithEtag<KnowledgeModelOut>(`/knowledge-models/${id}/${version}`)
  return { ...data, etag }
}

export interface CreateKnowledgeModelRequest {
  id?: string
  title: LangMap
  description?: LangMap
  license?: string
  sections?: KnowledgeModelContent['sections']
}

/** #4 `POST /knowledge-models` — "from scratch". */
export function createKnowledgeModel(body: CreateKnowledgeModelRequest) {
  return post<KnowledgeModelOut>('/knowledge-models', body)
}

export interface ForkKnowledgeModelRequest {
  newId?: string
  title?: LangMap
}

/** #5 `POST /knowledge-models/{id}/{version}/fork`. */
export function forkKnowledgeModel(id: string, version: string, body?: ForkKnowledgeModelRequest) {
  return post<KnowledgeModelOut>(`/knowledge-models/${id}/${version}/fork`, body ?? {})
}

export interface ImportKnowledgeModelRequest {
  id?: string
  document: unknown
}

/** #6 `POST /knowledge-models/import`. */
export function importKnowledgeModel(body: ImportKnowledgeModelRequest) {
  return post<KnowledgeModelOut>('/knowledge-models/import', body)
}

/** #7 `GET /knowledge-models/{id}/{version}/export.json` — plain `<a href>` target. */
export function kmExportJsonUrl(id: string, version: string): string {
  return `/api/knowledge-models/${id}/${version}/export.json`
}

export interface PatchKnowledgeModelRequest {
  title?: LangMap
  description?: LangMap
  visibility?: string
}

/** #8 `PATCH /knowledge-models/{id}/{version}`. */
export function patchKnowledgeModel(id: string, version: string, body: PatchKnowledgeModelRequest) {
  return patch<KnowledgeModelOut>(`/knowledge-models/${id}/${version}`, body)
}

export interface PutKnowledgeModelContentRequest {
  sections: KnowledgeModelContent['sections']
  title?: LangMap
  description?: LangMap
}

/**
 * #9 `PUT /knowledge-models/{id}/{version}/content` — `If-Match` required
 * (spec 04 §2/§3 #9); returns the new `ETag` alongside the body.
 */
export async function putKnowledgeModelContent(
  id: string,
  version: string,
  body: PutKnowledgeModelContentRequest,
  etag: string
): Promise<KnowledgeModelOut> {
  const { data, etag: newEtag } = await putWithEtag<KnowledgeModelOut>(
    `/knowledge-models/${id}/${version}/content`,
    body,
    etag
  )
  return { ...data, etag: newEtag }
}

/** #10 `POST /knowledge-models/{id}/{version}/publish`. */
export function publishKnowledgeModel(id: string, version: string, notes: string) {
  return post<KnowledgeModelOut>(`/knowledge-models/${id}/${version}/publish`, { notes })
}

export interface NewKnowledgeModelVersionRequest {
  bump?: 'minor' | 'patch' | 'major'
  version?: string
}

/** #11 `POST /knowledge-models/{id}/{version}/new-version`. */
export function newKnowledgeModelVersion(id: string, version: string, body?: NewKnowledgeModelVersionRequest) {
  return post<KnowledgeModelOut>(`/knowledge-models/${id}/${version}/new-version`, body ?? {})
}

/** #12 `DELETE /knowledge-models/{id}/{version}`. */
export function deleteKnowledgeModel(id: string, version: string) {
  return del<void>(`/knowledge-models/${id}/${version}`)
}
