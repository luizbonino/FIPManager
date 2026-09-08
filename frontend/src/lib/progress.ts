import { visibleQuestionCount as computeVisibleQuestionCount } from './kmContent'
import type { Answer, KnowledgeModelContent, KnowledgeModelOut } from '@/types/api'

/**
 * F/A/I/R = 6/5/6/4 questions on the GO FAIR fixture (spec 02 §1). Kept
 * only as the last-resort denominator when no knowledge model is loaded
 * yet (spec 04 §4) — every other call site now uses
 * `visibleQuestionCount(km)` or a model summary's `questionCount`.
 */
export const TOTAL_QUESTIONS = 21

/**
 * "Answered" = the FIP's `answers` entry has >= 1 declaration; a lone
 * `status: "none"` declaration still counts (spec 02 §1 — the ontology
 * treats "no choice yet" as a real declaration, spec 02 §7 A6).
 */
export function answeredCount(answers: Answer[] | null | undefined): number {
  if (!answers) return 0
  return answers.filter((answer) => (answer.declarations?.length ?? 0) > 0).length
}

/**
 * The progress denominator (spec 04 §4): non-hidden questions of a loaded
 * knowledge model, replacing the hardcoded `TOTAL_QUESTIONS = 21`. Accepts
 * either the full `KnowledgeModelOut` or its bare `content`, and falls
 * back to `TOTAL_QUESTIONS` only when no model is loaded at all.
 */
export function visibleQuestionCount(
  km: KnowledgeModelOut | KnowledgeModelContent | null | undefined
): number {
  if (!km) return TOTAL_QUESTIONS
  const content = 'content' in km ? km.content : km
  return computeVisibleQuestionCount(content)
}
