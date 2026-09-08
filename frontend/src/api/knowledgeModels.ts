import { get } from './client'
import type { KnowledgeModelOut, KnowledgeModelSummary, ListOut } from '@/types/api'

export function listKnowledgeModels(params?: { status?: string; q?: string }) {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  if (params?.q) qs.set('q', params.q)
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return get<ListOut<KnowledgeModelSummary>>(`/knowledge-models${suffix}`)
}

export function getKnowledgeModel(id: string, version: string) {
  return get<KnowledgeModelOut>(`/knowledge-models/${id}/${version}`)
}
