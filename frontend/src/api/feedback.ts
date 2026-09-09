import { get, post } from './client'

// spec 05 §4 — anonymous by construction: no user id, no IP is ever sent
// or stored client-side beyond the once-per-browser `localStorage` flag
// `FeedbackForm.vue` itself manages.

export interface FeedbackCreateRequest {
  q1: number
  q2: number
  q3: number
  comment?: string | null
  sessionId?: string | null
  fipId?: string | null
  language?: string | null
}

export function postFeedback(body: FeedbackCreateRequest) {
  return post<{ status: string }>('/feedback', body)
}

export interface FeedbackQuestionSummary {
  key: string
  /** 2 dp, `null` at 0 responses. */
  mean: number | null
  counts: Record<string, number>
}

export interface FeedbackSummary {
  responses: number
  questions: FeedbackQuestionSummary[]
  comments: { text: string; createdAt: string }[]
}

/** Owner/admin only (spec 05 §4). */
export function getSessionFeedback(sessionId: string) {
  return get<FeedbackSummary>(`/sessions/${sessionId}/feedback`)
}

/** Plain `<a href>` target — `Content-Disposition: attachment` set server-side. */
export function sessionFeedbackCsvUrl(sessionId: string): string {
  return `/api/sessions/${sessionId}/feedback.csv`
}
