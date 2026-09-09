/**
 * Pure edit operations + content validator for a knowledge model's
 * `content` document (docs/specs/04-knowledge-model-editor.md §2, §3.3).
 * Every op takes a `KnowledgeModelContent` and returns a *new* one, never
 * mutating its input — `stores/kmEditor.ts` is the only caller that keeps
 * state, this module has none. `validateContent` mirrors
 * `backend/fipm/km_content.py`'s `validate_content` rule for rule so the
 * two cannot silently drift (spec 04 §3.3).
 */
import type {
  DeclarationStatus,
  FerOut,
  InlineFer,
  KnowledgeModelContent,
  KnowledgeModelQuestion,
  KnowledgeModelSection,
  LangMap,
} from '@/types/api'

// ---------------------------------------------------------------------------
// Shared constants (spec 04 §3.3)
// ---------------------------------------------------------------------------

export const QUESTION_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/
export const SECTION_ID_PATTERN = QUESTION_ID_PATTERN
export const SUPPORTED_LANGUAGES = ['en', 'pt-PT', 'pt-BR', 'es'] as const
export const PRINCIPLES = [
  'F1',
  'F2',
  'F3',
  'F4',
  'A1',
  'A1.1',
  'A1.2',
  'A2',
  'I1',
  'I2',
  'I3',
  'R1',
  'R1.1',
  'R1.2',
  'R1.3',
] as const
export const MAX_SECTIONS = 50
export const MAX_QUESTIONS = 300
export const MAX_TEXT_LENGTH = 4000
const MAX_ERRORS = 50

// ---------------------------------------------------------------------------
// Spec 08 §1 — suggested options / inline FERs / declaration defaults.
// ---------------------------------------------------------------------------

/** `fipm.config.DECLARATION_STATUSES` (spec 02 §1) — kept here too since the model-level default needs it. */
export const DECLARATION_STATUSES: readonly DeclarationStatus[] = [
  'current',
  'planned',
  'planned-development',
  'planned-replacement',
  'none',
]

export const MAX_SUGGESTED_FERS = 12
export const MAX_INLINE_FERS = 300

/** An absolute `http(s)` IRI (spec 08 §1.2 rule 9/12): a same-shape check the backend's `httpx`-style parse mirrors. */
export function isAbsoluteHttpIri(value: unknown): value is string {
  if (typeof value !== 'string' || value === '') return false
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

// ---------------------------------------------------------------------------
// Errors thrown by the edit ops (mirroring the API's error codes, spec §3)
// ---------------------------------------------------------------------------

export class KmContentOpError extends Error {
  constructor(
    public code: string,
    message: string
  ) {
    super(message)
    this.name = 'KmContentOpError'
  }
}

function notFound(kind: 'section' | 'question', id: string): never {
  throw new KmContentOpError('not_found', `${kind} "${id}" not found`)
}

// ---------------------------------------------------------------------------
// Cloning helpers — every op below clones before mutating its copy.
// ---------------------------------------------------------------------------

function cloneLangMap(map: LangMap | null | undefined): LangMap {
  return map ? { ...map } : {}
}

function cloneQuestion(question: KnowledgeModelQuestion): KnowledgeModelQuestion {
  return {
    ...question,
    text: cloneLangMap(question.text),
    help: question.help ? cloneLangMap(question.help) : null,
    suggestedFerIds: question.suggestedFerIds ? [...question.suggestedFerIds] : question.suggestedFerIds,
  }
}

function cloneSection(section: KnowledgeModelSection): KnowledgeModelSection {
  return {
    ...section,
    title: cloneLangMap(section.title),
    questions: section.questions.map(cloneQuestion),
  }
}

function cloneInlineFer(fer: InlineFer): InlineFer {
  return { ...fer, label: cloneLangMap(fer.label) }
}

/** Deep-enough clone: every section, question and LangMap gets its own copy. */
export function cloneContent(content: KnowledgeModelContent): KnowledgeModelContent {
  return {
    ...content,
    title: cloneLangMap(content.title),
    description: cloneLangMap(content.description),
    changelog: content.changelog.map((entry) => ({ ...entry })),
    sections: content.sections.map(cloneSection),
    forkedFrom: content.forkedFrom ? { ...content.forkedFrom } : content.forkedFrom,
    inlineFers: content.inlineFers ? content.inlineFers.map(cloneInlineFer) : content.inlineFers,
  }
}

function findSectionIndex(content: KnowledgeModelContent, sectionId: string): number {
  const index = content.sections.findIndex((s) => s.id === sectionId)
  if (index === -1) notFound('section', sectionId)
  return index
}

function findQuestionLocation(
  content: KnowledgeModelContent,
  questionId: string
): { sectionIndex: number; questionIndex: number } {
  for (let sectionIndex = 0; sectionIndex < content.sections.length; sectionIndex += 1) {
    const questionIndex = content.sections[sectionIndex].questions.findIndex((q) => q.id === questionId)
    if (questionIndex !== -1) return { sectionIndex, questionIndex }
  }
  notFound('question', questionId)
}

// ---------------------------------------------------------------------------
// Text editing (spec §2 "edit texts")
// ---------------------------------------------------------------------------

export type TextTarget =
  | { field: 'title' }
  | { field: 'description' }
  | { field: 'sectionTitle'; sectionId: string }
  | { field: 'questionText'; questionId: string }
  | { field: 'questionHelp'; questionId: string }

function applyLangValue(map: LangMap, lang: string, value: string): LangMap {
  const next = { ...map }
  if (value === '') {
    if (lang === 'en') {
      throw new KmContentOpError('missing_en', 'the English ("en") text cannot be deleted')
    }
    delete next[lang]
  } else {
    next[lang] = value
  }
  return next
}

/**
 * Sets (or, given `''`, deletes) one language key of one translatable
 * string. `en` may never be deleted (spec §2). Deleting the last remaining
 * key of a `help` text turns it into `null` (an "empty help" is no help).
 */
export function setText(
  content: KnowledgeModelContent,
  target: TextTarget,
  lang: string,
  value: string
): KnowledgeModelContent {
  const next = cloneContent(content)
  switch (target.field) {
    case 'title':
      next.title = applyLangValue(next.title, lang, value)
      return next
    case 'description':
      next.description = applyLangValue(next.description, lang, value)
      return next
    case 'sectionTitle': {
      const index = findSectionIndex(next, target.sectionId)
      next.sections[index].title = applyLangValue(next.sections[index].title, lang, value)
      return next
    }
    case 'questionText': {
      const { sectionIndex, questionIndex } = findQuestionLocation(next, target.questionId)
      const question = next.sections[sectionIndex].questions[questionIndex]
      question.text = applyLangValue(question.text, lang, value)
      return next
    }
    case 'questionHelp': {
      const { sectionIndex, questionIndex } = findQuestionLocation(next, target.questionId)
      const question = next.sections[sectionIndex].questions[questionIndex]
      // Unlike `title`/`description`/`text`, `help` is optional as a whole
      // (spec §3.3 rule 3: a LangMap must contain `en` "when present"), so
      // clearing its `en` collapses the whole thing to `null` instead of
      // throwing — there is no such thing as a help text with no English.
      if (lang === 'en' && value === '') {
        question.help = null
        return next
      }
      const updated = applyLangValue(question.help ?? {}, lang, value)
      question.help = Object.keys(updated).length > 0 ? updated : null
      return next
    }
  }
}

// ---------------------------------------------------------------------------
// Hide / unhide
// ---------------------------------------------------------------------------

/** Sets `hidden: true`; the question stays in `content`, keeps its id and any stored answers (spec §2). */
export function hideQuestion(content: KnowledgeModelContent, questionId: string): KnowledgeModelContent {
  const next = cloneContent(content)
  const { sectionIndex, questionIndex } = findQuestionLocation(next, questionId)
  next.sections[sectionIndex].questions[questionIndex].hidden = true
  return next
}

/** Removes `hidden`, restoring the question to questionnaires, exports and progress. */
export function unhideQuestion(content: KnowledgeModelContent, questionId: string): KnowledgeModelContent {
  const next = cloneContent(content)
  const { sectionIndex, questionIndex } = findQuestionLocation(next, questionId)
  delete next.sections[sectionIndex].questions[questionIndex].hidden
  return next
}

// ---------------------------------------------------------------------------
// Reorder (within-parent only — cross-section moves are v2, spec §2)
// ---------------------------------------------------------------------------

export type MoveDirection = 'up' | 'down'

function moveWithinArray<T>(items: T[], index: number, direction: MoveDirection): T[] {
  const target = direction === 'up' ? index - 1 : index + 1
  if (target < 0 || target >= items.length) return items.slice()
  const next = items.slice()
  const [item] = next.splice(index, 1)
  next.splice(target, 0, item)
  return next
}

/** Moves a section one step up/down among its siblings; a no-op at either end. */
export function moveSection(
  content: KnowledgeModelContent,
  sectionId: string,
  direction: MoveDirection
): KnowledgeModelContent {
  const next = cloneContent(content)
  const index = findSectionIndex(next, sectionId)
  next.sections = moveWithinArray(next.sections, index, direction)
  return next
}

/** Moves a question one step up/down within its own section; a no-op at either end. */
export function moveQuestion(
  content: KnowledgeModelContent,
  questionId: string,
  direction: MoveDirection
): KnowledgeModelContent {
  const next = cloneContent(content)
  const { sectionIndex, questionIndex } = findQuestionLocation(next, questionId)
  const section = next.sections[sectionIndex]
  section.questions = moveWithinArray(section.questions, questionIndex, direction)
  return next
}

// ---------------------------------------------------------------------------
// Add section / question
// ---------------------------------------------------------------------------

export interface AddSectionInput {
  id: string
  title: LangMap
}

export function addSection(content: KnowledgeModelContent, input: AddSectionInput): KnowledgeModelContent {
  const next = cloneContent(content)
  next.sections.push({ id: input.id, title: { ...input.title }, questions: [] })
  return next
}

export interface AddQuestionInput {
  id: string
  principle?: string | null
  scope?: 'metadata' | 'data' | null
  text: LangMap
  help?: LangMap | null
  ferType?: string | null
  required?: boolean
  allowMultiple?: boolean
}

/** Appends a new question, with the spec's defaults, to `sectionId` (spec §2 "add question"). */
export function addQuestion(
  content: KnowledgeModelContent,
  sectionId: string,
  input: AddQuestionInput
): KnowledgeModelContent {
  const next = cloneContent(content)
  const index = findSectionIndex(next, sectionId)
  const question: KnowledgeModelQuestion = {
    id: input.id,
    principle: input.principle ?? null,
    scope: input.scope ?? null,
    text: { ...input.text },
    help: input.help ? { ...input.help } : null,
    ferType: input.ferType ?? null,
    required: input.required ?? false,
    allowMultiple: input.allowMultiple ?? true,
  }
  next.sections[index].questions.push(question)
  return next
}

// ---------------------------------------------------------------------------
// Split
// ---------------------------------------------------------------------------

/**
 * Replaces a question, in place, with `<id>-metadata` and `<id>-data`
 * copies (spec §2 "split"). Throws `cannot_split` when the id already ends
 * in `-metadata`/`-data`, `duplicate_question_id` on a collision.
 */
export function splitQuestion(content: KnowledgeModelContent, questionId: string): KnowledgeModelContent {
  if (questionId.endsWith('-metadata') || questionId.endsWith('-data')) {
    throw new KmContentOpError('cannot_split', `question "${questionId}" is already split`)
  }
  const next = cloneContent(content)
  const { sectionIndex, questionIndex } = findQuestionLocation(next, questionId)
  const original = next.sections[sectionIndex].questions[questionIndex]

  const metadataId = `${questionId}-metadata`
  const dataId = `${questionId}-data`
  const allIds = new Set(next.sections.flatMap((s) => s.questions.map((q) => q.id)))
  allIds.delete(questionId)
  if (allIds.has(metadataId) || allIds.has(dataId)) {
    const collision = allIds.has(metadataId) ? metadataId : dataId
    throw new KmContentOpError('duplicate_question_id', `question id "${collision}" already exists`)
  }

  const metadataQuestion: KnowledgeModelQuestion = {
    ...cloneQuestion(original),
    id: metadataId,
    scope: 'metadata',
  }
  const dataQuestion: KnowledgeModelQuestion = {
    ...cloneQuestion(original),
    id: dataId,
    scope: 'data',
  }
  next.sections[sectionIndex].questions.splice(questionIndex, 1, metadataQuestion, dataQuestion)
  return next
}

// ---------------------------------------------------------------------------
// FER type
// ---------------------------------------------------------------------------

export function setFerType(
  content: KnowledgeModelContent,
  questionId: string,
  ferType: string | null
): KnowledgeModelContent {
  const next = cloneContent(content)
  const { sectionIndex, questionIndex } = findQuestionLocation(next, questionId)
  next.sections[sectionIndex].questions[questionIndex].ferType = ferType
  return next
}

// ---------------------------------------------------------------------------
// Spec 08 §1.4 — suggested options, inline FERs, model-level declaration defaults.
// ---------------------------------------------------------------------------

/** Replaces a question's whole `suggestedFerIds` list (e.g. after a `MoveButtons` reorder). */
export function setSuggestedFerIds(
  content: KnowledgeModelContent,
  questionId: string,
  ids: string[]
): KnowledgeModelContent {
  const next = cloneContent(content)
  const { sectionIndex, questionIndex } = findQuestionLocation(next, questionId)
  next.sections[sectionIndex].questions[questionIndex].suggestedFerIds = [...ids]
  return next
}

/** Appends `ferId` to the question's suggestions, a no-op if already present or at the 12 cap. */
export function addSuggestedFer(
  content: KnowledgeModelContent,
  questionId: string,
  ferId: string
): KnowledgeModelContent {
  const next = cloneContent(content)
  const { sectionIndex, questionIndex } = findQuestionLocation(next, questionId)
  const question = next.sections[sectionIndex].questions[questionIndex]
  const current = question.suggestedFerIds ?? []
  if (current.includes(ferId) || current.length >= MAX_SUGGESTED_FERS) return next
  question.suggestedFerIds = [...current, ferId]
  return next
}

/** Removes `ferId` from the question's suggestions, if present. */
export function removeSuggestedFer(
  content: KnowledgeModelContent,
  questionId: string,
  ferId: string
): KnowledgeModelContent {
  const next = cloneContent(content)
  const { sectionIndex, questionIndex } = findQuestionLocation(next, questionId)
  const question = next.sections[sectionIndex].questions[questionIndex]
  question.suggestedFerIds = (question.suggestedFerIds ?? []).filter((id) => id !== ferId)
  return next
}

/** Moves one suggested id one step up/down within its question's list (`MoveButtons.vue`, spec §1.4). */
export function moveSuggestedFer(
  content: KnowledgeModelContent,
  questionId: string,
  ferId: string,
  direction: MoveDirection
): KnowledgeModelContent {
  const next = cloneContent(content)
  const { sectionIndex, questionIndex } = findQuestionLocation(next, questionId)
  const question = next.sections[sectionIndex].questions[questionIndex]
  const ids = question.suggestedFerIds ?? []
  const index = ids.indexOf(ferId)
  if (index === -1) return next
  question.suggestedFerIds = moveWithinArray(ids, index, direction)
  return next
}

/** The `allowFreeText` checkbox (spec §1.1/§1.4); `undefined` means "true" (the spec default). */
export function setAllowFreeText(
  content: KnowledgeModelContent,
  questionId: string,
  value: boolean
): KnowledgeModelContent {
  const next = cloneContent(content)
  const { sectionIndex, questionIndex } = findQuestionLocation(next, questionId)
  next.sections[sectionIndex].questions[questionIndex].allowFreeText = value
  return next
}

/**
 * "Add inline FER" (spec §1.4): appends `fer` to `model.inlineFers` *and* to
 * `questionId`'s `suggestedFerIds` in one op, matching the editor's single
 * sub-form action. A no-op on a duplicate inline id (the caller should
 * validate first; this stays a pure, throw-free op like its siblings).
 */
export function addInlineFer(
  content: KnowledgeModelContent,
  questionId: string,
  fer: InlineFer
): KnowledgeModelContent {
  const next = cloneContent(content)
  const existingInline = next.inlineFers ?? []
  if (existingInline.some((f) => f.id === fer.id)) return next
  next.inlineFers = [...existingInline, cloneInlineFer(fer)]
  const { sectionIndex, questionIndex } = findQuestionLocation(next, questionId)
  const question = next.sections[sectionIndex].questions[questionIndex]
  const suggested = question.suggestedFerIds ?? []
  if (!suggested.includes(fer.id) && suggested.length < MAX_SUGGESTED_FERS) {
    question.suggestedFerIds = [...suggested, fer.id]
  }
  return next
}

/** Deletes an `inlineFers` entry (the settings panel's delete button on an "unused" one, spec §1.4). */
export function removeInlineFer(content: KnowledgeModelContent, ferId: string): KnowledgeModelContent {
  const next = cloneContent(content)
  next.inlineFers = (next.inlineFers ?? []).filter((f) => f.id !== ferId)
  return next
}

/** `model.inlineFers` entries no question's `suggestedFerIds` references (spec §1.2 rule 13's "unused" note). */
export function unusedInlineFers(content: KnowledgeModelContent): InlineFer[] {
  const referenced = new Set(allQuestions(content).flatMap((q) => q.suggestedFerIds ?? []))
  return (content.inlineFers ?? []).filter((f) => !referenced.has(f.id))
}

/**
 * Resolves one suggested id to a `FerOut`-shaped option (spec §1.3): an
 * `inlineFers` entry first (so a draft model / offline laptop can render its
 * own quick-pick before publish promotes anything), then the catalogue map;
 * `null` when neither has it (a stale suggestion, not rendered).
 */
export function resolveSuggestedFer(
  ferId: string,
  content: KnowledgeModelContent,
  fers: Record<string, FerOut> | Map<string, FerOut>
): FerOut | null {
  const inline = (content.inlineFers ?? []).find((f) => f.id === ferId)
  if (inline) {
    return { id: inline.id, label: inline.label, type: inline.type, homepage: inline.homepage ?? null, source: 'model' }
  }
  const catalogued = fers instanceof Map ? fers.get(ferId) : fers[ferId]
  return catalogued ?? null
}

/** The full, ordered, resolved suggested-FER list for one question (spec §1.5's `suggested` prop). */
export function suggestedFersFor(
  content: KnowledgeModelContent,
  questionId: string,
  fers: Record<string, FerOut> | Map<string, FerOut>
): FerOut[] {
  const question = allQuestions(content).find((q) => q.id === questionId)
  const ids = question?.suggestedFerIds ?? []
  const resolved: FerOut[] = []
  for (const id of ids) {
    const fer = resolveSuggestedFer(id, content, fers)
    if (fer) resolved.push(fer)
  }
  return resolved
}

export function setDefaultDeclarationStatus(
  content: KnowledgeModelContent,
  value: DeclarationStatus
): KnowledgeModelContent {
  return { ...cloneContent(content), defaultDeclarationStatus: value }
}

export function setCompactDeclarations(content: KnowledgeModelContent, value: boolean): KnowledgeModelContent {
  return { ...cloneContent(content), compactDeclarations: value }
}

// ---------------------------------------------------------------------------
// Delete
// ---------------------------------------------------------------------------

export function deleteQuestion(content: KnowledgeModelContent, questionId: string): KnowledgeModelContent {
  const next = cloneContent(content)
  const { sectionIndex, questionIndex } = findQuestionLocation(next, questionId)
  next.sections[sectionIndex].questions.splice(questionIndex, 1)
  return next
}

export function deleteSection(content: KnowledgeModelContent, sectionId: string): KnowledgeModelContent {
  const next = cloneContent(content)
  const index = findSectionIndex(next, sectionId)
  next.sections.splice(index, 1)
  return next
}

// ---------------------------------------------------------------------------
// Progress / completeness (spec §4, §5)
// ---------------------------------------------------------------------------

/** All questions across all sections, hidden or not. */
export function allQuestions(content: KnowledgeModelContent): KnowledgeModelQuestion[] {
  return content.sections.flatMap((s) => s.questions)
}

/** `visibleQuestionCount(km)` (spec §4): questions with `hidden !== true` — the new progress denominator. */
export function visibleQuestionCount(content: KnowledgeModelContent): number {
  return allQuestions(content).filter((q) => q.hidden !== true).length
}

export interface Completeness {
  done: number
  total: number
}

/**
 * Translation-completeness meter (spec §5's `TranslationMeter`): the
 * fraction of question `text` entries that have a value for `lang`, over
 * every question in the model (hidden included — hidden text still needs
 * translating for when it is unhidden again).
 */
export function completeness(content: KnowledgeModelContent, lang: string): Completeness {
  const questions = allQuestions(content)
  const done = questions.filter((q) => typeof q.text[lang] === 'string' && q.text[lang] !== '').length
  return { done, total: questions.length }
}

// ---------------------------------------------------------------------------
// Validation (spec §3.3) — mirrors backend/fipm/km_content.py rule for rule.
// ---------------------------------------------------------------------------

export interface ContentError {
  path: string
  code: string
  message: string
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Options mirroring the backend's `validate_content` keyword args (spec 08 §1.2 rule 10/13). */
export interface ValidateContentOptions {
  /**
   * The picker's cached catalogue map — `undefined`/`null` **skips** the
   * catalogue half of rule 10 (resolution still checks `inlineFers`), same
   * as the backend's `known_fer_ids=None`.
   */
  knownFerIds?: Set<string> | null
  /** Rule 13 (`no_answer_path`, `inline_fer_duplicates_catalogue`) applies publish-time only. */
  publishing?: boolean
}

/**
 * `validate_content(doc) -> list[ContentError]` (spec §3.3, extended by spec
 * 08 §1.2 rules 9-13). Collects up to 50 errors (the API's own cap) rather
 * than stopping at the first one, so `KmValidationList.vue` can show the
 * whole picture at once.
 */
export function validateContent(
  content: KnowledgeModelContent,
  ferTypeKeys: readonly string[],
  options: ValidateContentOptions = {}
): ContentError[] {
  const { knownFerIds = null, publishing = false } = options
  const errors: ContentError[] = []
  function push(path: string, code: string, message: string) {
    if (errors.length < MAX_ERRORS) errors.push({ path, code, message })
  }

  function validateLangMap(value: unknown, path: string, requireEn = true) {
    if (!isPlainObject(value)) {
      push(path, 'missing_en', `${path} must be an object containing "en"`)
      return
    }
    let hasEn = false
    let hasAny = false
    for (const [key, langValue] of Object.entries(value)) {
      if (!(SUPPORTED_LANGUAGES as readonly string[]).includes(key)) {
        push(`${path}.${key}`, 'unknown_language', `unknown language "${key}"`)
        continue
      }
      if (key === 'en') hasEn = true
      if (typeof langValue !== 'string' || langValue === '') {
        push(`${path}.${key}`, 'empty_string', `${path}.${key} must be a non-empty string`)
      } else {
        hasAny = true
        if (langValue.length > MAX_TEXT_LENGTH) {
          push(`${path}.${key}`, 'too_long', `${path}.${key} exceeds ${MAX_TEXT_LENGTH} characters`)
        }
      }
    }
    if (requireEn) {
      if (!hasEn) push(path, 'missing_en', `${path} must include "en"`)
    } else if (!hasAny) {
      // spec §1.2 rule 12 / §7 A7: an area/inline-FER label needs no `en`,
      // just >= 1 non-empty language value.
      push(path, 'missing_key', `${path} must have at least one non-empty language value`)
    }
  }

  if (!Array.isArray(content.sections)) {
    push('sections', 'missing_key', 'sections must be a list')
    return errors
  }
  if (content.sections.length > MAX_SECTIONS) {
    push('sections', 'too_many', `more than ${MAX_SECTIONS} sections`)
  }

  validateLangMap(content.title, 'title')
  validateLangMap(content.description, 'description')

  const sectionIds = new Set<string>()
  const questionIds = new Set<string>()
  let questionCount = 0

  content.sections.forEach((section, sectionIndex) => {
    const sectionPath = `sections[${sectionIndex}]`
    if (typeof section.id !== 'string' || section.id === '') {
      push(`${sectionPath}.id`, 'missing_key', 'section id is required')
    } else if (!SECTION_ID_PATTERN.test(section.id)) {
      push(`${sectionPath}.id`, 'invalid_id', `invalid section id "${section.id}"`)
    } else if (sectionIds.has(section.id)) {
      push(`${sectionPath}.id`, 'duplicate_section_id', `duplicate section id "${section.id}"`)
    } else {
      sectionIds.add(section.id)
    }

    validateLangMap(section.title, `${sectionPath}.title`)

    if (!Array.isArray(section.questions)) {
      push(`${sectionPath}.questions`, 'missing_key', 'questions must be a list')
      return
    }

    section.questions.forEach((question, questionIndex) => {
      questionCount += 1
      const questionPath = `${sectionPath}.questions[${questionIndex}]`

      if (typeof question.id !== 'string' || question.id === '') {
        push(`${questionPath}.id`, 'missing_key', 'question id is required')
      } else if (!QUESTION_ID_PATTERN.test(question.id)) {
        push(`${questionPath}.id`, 'invalid_id', `invalid question id "${question.id}"`)
      } else if (questionIds.has(question.id)) {
        push(`${questionPath}.id`, 'duplicate_question_id', `duplicate question id "${question.id}"`)
      } else {
        questionIds.add(question.id)
      }

      validateLangMap(question.text, `${questionPath}.text`)
      if (question.help !== null && question.help !== undefined) {
        validateLangMap(question.help, `${questionPath}.help`)
      }

      if (
        question.ferType !== null &&
        question.ferType !== undefined &&
        !ferTypeKeys.includes(question.ferType)
      ) {
        push(`${questionPath}.ferType`, 'unknown_fer_type', `unknown FER type "${question.ferType}"`)
      }

      if (
        question.principle !== null &&
        question.principle !== undefined &&
        !(PRINCIPLES as readonly string[]).includes(question.principle)
      ) {
        push(`${questionPath}.principle`, 'unknown_principle', `unknown principle "${question.principle}"`)
      }

      if (question.scope !== null && question.scope !== undefined && !['metadata', 'data'].includes(question.scope)) {
        push(`${questionPath}.scope`, 'invalid_value', `invalid scope "${question.scope}"`)
      }

      for (const field of ['required', 'allowMultiple', 'hidden', 'allowFreeText'] as const) {
        const value = question[field]
        if (value !== undefined && typeof value !== 'boolean') {
          push(`${questionPath}.${field}`, 'invalid_value', `${field} must be a boolean`)
        }
      }

      // Spec 08 §1.2 rule 9: suggestedFerIds — unique absolute http(s) IRIs, <= 12.
      const suggested = question.suggestedFerIds
      if (suggested !== undefined) {
        if (!Array.isArray(suggested)) {
          push(`${questionPath}.suggestedFerIds`, 'invalid_value', 'suggestedFerIds must be a list')
        } else {
          if (suggested.length > MAX_SUGGESTED_FERS) {
            push(`${questionPath}.suggestedFerIds`, 'too_many', `more than ${MAX_SUGGESTED_FERS} suggested FERs`)
          }
          const seen = new Set<string>()
          suggested.forEach((id, idIndex) => {
            const idPath = `${questionPath}.suggestedFerIds[${idIndex}]`
            if (!isAbsoluteHttpIri(id)) {
              push(idPath, 'invalid_fer_iri', `"${id}" is not an absolute http(s) IRI`)
              return
            }
            if (seen.has(id)) {
              push(idPath, 'duplicate_suggested_fer', `duplicate suggested FER "${id}"`)
              return
            }
            seen.add(id)
            // Rule 10: resolve against inlineFers ∪ knownFerIds; the
            // catalogue half is skipped entirely when knownFerIds is null,
            // exactly like the backend's known_fer_ids=None.
            const inlineIds = new Set((content.inlineFers ?? []).map((f) => f.id))
            const resolvable = inlineIds.has(id) || knownFerIds === null || knownFerIds.has(id)
            if (!resolvable) {
              push(idPath, 'unknown_suggested_fer', `suggested FER "${id}" does not resolve`)
            }
          })
        }
      }

      // Spec 08 §1.2 rule 13 (publish only): no suggestions and no free text -> unanswerable.
      if (publishing) {
        const allowFreeText = question.allowFreeText ?? true
        const hasSuggestions = Array.isArray(suggested) && suggested.length > 0
        if (!allowFreeText && !hasSuggestions) {
          push(`${questionPath}`, 'no_answer_path', `question "${question.id}" has no way to be answered`)
        }
      }
    })
  })

  if (questionCount > MAX_QUESTIONS) {
    push('sections', 'too_many', `more than ${MAX_QUESTIONS} questions`)
  }

  // Spec 08 §1.2 rule 11: model-level declaration defaults.
  if (content.defaultDeclarationStatus !== undefined && !DECLARATION_STATUSES.includes(content.defaultDeclarationStatus)) {
    push('defaultDeclarationStatus', 'invalid_value', `invalid defaultDeclarationStatus "${content.defaultDeclarationStatus}"`)
  }
  if (content.compactDeclarations !== undefined && typeof content.compactDeclarations !== 'boolean') {
    push('compactDeclarations', 'invalid_value', 'compactDeclarations must be a boolean')
  }

  // Spec 08 §1.2 rule 12: inlineFers — <= 300, unique absolute IRI ids, known type, non-empty label, valid homepage.
  const inlineFers = content.inlineFers
  if (inlineFers !== undefined) {
    if (!Array.isArray(inlineFers)) {
      push('inlineFers', 'invalid_value', 'inlineFers must be a list')
    } else {
      if (inlineFers.length > MAX_INLINE_FERS) {
        push('inlineFers', 'too_many', `more than ${MAX_INLINE_FERS} inline FERs`)
      }
      const seenIds = new Set<string>()
      inlineFers.forEach((fer, ferIndex) => {
        const ferPath = `inlineFers[${ferIndex}]`
        if (!isAbsoluteHttpIri(fer.id)) {
          push(`${ferPath}.id`, 'invalid_fer_iri', `"${fer.id}" is not an absolute http(s) IRI`)
        } else if (seenIds.has(fer.id)) {
          push(`${ferPath}.id`, 'duplicate_inline_fer', `duplicate inline FER id "${fer.id}"`)
        } else {
          seenIds.add(fer.id)
          if (publishing && knownFerIds?.has(fer.id)) {
            push(`${ferPath}.id`, 'inline_fer_duplicates_catalogue', `"${fer.id}" already exists in the catalogue`)
          }
        }

        if (!ferTypeKeys.includes(fer.type)) {
          push(`${ferPath}.type`, 'unknown_fer_type', `unknown FER type "${fer.type}"`)
        }

        validateLangMap(fer.label, `${ferPath}.label`, false)

        if (fer.homepage !== null && fer.homepage !== undefined && !isAbsoluteHttpIri(fer.homepage)) {
          push(`${ferPath}.homepage`, 'invalid_value', `"${fer.homepage}" is not an absolute http(s) IRI`)
        }
      })
    }
  }

  return errors
}
