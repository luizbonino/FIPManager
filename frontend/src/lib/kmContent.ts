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
export const SUPPORTED_LANGUAGES = ['en', 'pt-PT', 'pt-BR'] as const
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
  }
}

function cloneSection(section: KnowledgeModelSection): KnowledgeModelSection {
  return {
    ...section,
    title: cloneLangMap(section.title),
    questions: section.questions.map(cloneQuestion),
  }
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

/**
 * `validate_content(doc) -> list[ContentError]` (spec §3.3). Collects up to
 * 50 errors (the API's own cap) rather than stopping at the first one, so
 * `KmValidationList.vue` can show the whole picture at once.
 */
export function validateContent(
  content: KnowledgeModelContent,
  ferTypeKeys: readonly string[]
): ContentError[] {
  const errors: ContentError[] = []
  function push(path: string, code: string, message: string) {
    if (errors.length < MAX_ERRORS) errors.push({ path, code, message })
  }

  function validateLangMap(value: unknown, path: string) {
    if (!isPlainObject(value)) {
      push(path, 'missing_en', `${path} must be an object containing "en"`)
      return
    }
    let hasEn = false
    for (const [key, langValue] of Object.entries(value)) {
      if (!(SUPPORTED_LANGUAGES as readonly string[]).includes(key)) {
        push(`${path}.${key}`, 'unknown_language', `unknown language "${key}"`)
        continue
      }
      if (key === 'en') hasEn = true
      if (typeof langValue !== 'string' || langValue === '') {
        push(`${path}.${key}`, 'empty_string', `${path}.${key} must be a non-empty string`)
      } else if (langValue.length > MAX_TEXT_LENGTH) {
        push(`${path}.${key}`, 'too_long', `${path}.${key} exceeds ${MAX_TEXT_LENGTH} characters`)
      }
    }
    if (!hasEn) push(path, 'missing_en', `${path} must include "en"`)
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

      for (const field of ['required', 'allowMultiple', 'hidden'] as const) {
        const value = question[field]
        if (value !== undefined && typeof value !== 'boolean') {
          push(`${questionPath}.${field}`, 'invalid_value', `${field} must be a boolean`)
        }
      }
    })
  })

  if (questionCount > MAX_QUESTIONS) {
    push('sections', 'too_many', `more than ${MAX_QUESTIONS} questions`)
  }

  return errors
}
