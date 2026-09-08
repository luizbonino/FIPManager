import type { Answer } from '@/types/api'

/** F/A/I/R = 6/5/6/4 questions (spec 02 §1, `gofair-fip-mini-1.0.0.json`). */
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
