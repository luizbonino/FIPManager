import { get } from './client'
import type { FipOut, KnowledgeModelSummary, ListOut, SessionOut } from '@/types/api'

export function myFips(params?: { q?: string; limit?: number; offset?: number }) {
  const qs = new URLSearchParams()
  if (params?.q) qs.set('q', params.q)
  if (params?.limit !== undefined) qs.set('limit', String(params.limit))
  if (params?.offset !== undefined) qs.set('offset', String(params.offset))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return get<ListOut<FipOut>>(`/me/fips${suffix}`)
}

export function mySessions() {
  return get<ListOut<SessionOut>>('/me/sessions')
}

export function myKnowledgeModels() {
  return get<ListOut<KnowledgeModelSummary>>('/me/knowledge-models')
}
