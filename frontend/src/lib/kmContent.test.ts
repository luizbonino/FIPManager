import { describe, expect, it } from 'vitest'
import {
  KmContentOpError,
  addQuestion,
  addSection,
  completeness,
  deleteQuestion,
  deleteSection,
  hideQuestion,
  moveQuestion,
  moveSection,
  setFerType,
  setText,
  splitQuestion,
  unhideQuestion,
  validateContent,
  visibleQuestionCount,
} from './kmContent'
// The real content of `data/knowledge-models/gofair-fip-mini-1.0.0.json`,
// read directly (as `lib/matrix.test.ts` does) so this suite cannot drift
// from the questionnaire the app actually serves. Criterion 13.
import kmFixtureJson from '../../../data/knowledge-models/gofair-fip-mini-1.0.0.json'
import type { KnowledgeModelContent } from '@/types/api'

const FER_TYPE_KEYS = [
  'identifier-service',
  'metadata-schema',
  'metadata-data-linking-schema',
  'registry',
  'communication-protocol',
  'authentication-authorization-service',
  'metadata-preservation-policy',
  'knowledge-representation-language',
  'structured-vocabulary',
  'semantic-model',
  'data-usage-license',
  'provenance-model',
]

function fixture(): KnowledgeModelContent {
  // Deep-clone so mutation-detection tests can freely compare against a
  // pristine copy without any risk of aliasing the shared fixture object.
  return JSON.parse(JSON.stringify(kmFixtureJson)) as KnowledgeModelContent
}

describe('kmContent — immutability', () => {
  it('hideQuestion returns a new object and leaves the input untouched', () => {
    const before = fixture()
    const beforeJson = JSON.stringify(before)
    const after = hideQuestion(before, 'F1-metadata')
    expect(after).not.toBe(before)
    expect(JSON.stringify(before)).toBe(beforeJson)
    expect(after.sections[0].questions[0].hidden).toBe(true)
    expect(before.sections[0].questions[0].hidden).toBeUndefined()
  })

  it('setText, addQuestion, deleteSection each return new objects', () => {
    const content = fixture()
    expect(setText(content, { field: 'title' }, 'en', 'New title')).not.toBe(content)
    expect(
      addQuestion(content, 'F', {
        id: 'extra-1',
        text: { en: 'Extra question' },
      })
    ).not.toBe(content)
    expect(deleteSection(content, 'F')).not.toBe(content)
  })
})

describe('kmContent — reorder no-ops at ends', () => {
  it('moveQuestion up at index 0 is a no-op', () => {
    const content = fixture()
    const moved = moveQuestion(content, 'F1-metadata', 'up')
    expect(moved.sections[0].questions.map((q) => q.id)).toEqual(
      content.sections[0].questions.map((q) => q.id)
    )
  })

  it('moveQuestion down at the last index is a no-op', () => {
    const content = fixture()
    const lastId = content.sections[0].questions[content.sections[0].questions.length - 1].id
    const moved = moveQuestion(content, lastId, 'down')
    expect(moved.sections[0].questions.map((q) => q.id)).toEqual(
      content.sections[0].questions.map((q) => q.id)
    )
  })

  it('moveQuestion up in the middle swaps with the previous sibling', () => {
    const content = fixture()
    const ids = content.sections[0].questions.map((q) => q.id)
    const moved = moveQuestion(content, ids[1], 'up')
    expect(moved.sections[0].questions.map((q) => q.id)).toEqual([ids[1], ids[0], ...ids.slice(2)])
  })

  it('moveSection up at index 0 is a no-op; down at the last index is a no-op', () => {
    const content = fixture()
    const ids = content.sections.map((s) => s.id)
    expect(moveSection(content, ids[0], 'up').sections.map((s) => s.id)).toEqual(ids)
    expect(moveSection(content, ids[ids.length - 1], 'down').sections.map((s) => s.id)).toEqual(ids)
  })
})

describe('kmContent — splitQuestion', () => {
  it('splits "F2" into F2-metadata and F2-data in place, copying text/help/principle/ferType', () => {
    const content = fixture()
    const original = content.sections[0].questions.find((q) => q.id === 'F2')
    expect(original).toBeDefined()
    const result = splitQuestion(content, 'F2')
    const section = result.sections[0]
    const originalIndex = content.sections[0].questions.findIndex((q) => q.id === 'F2')
    expect(section.questions[originalIndex].id).toBe('F2-metadata')
    expect(section.questions[originalIndex + 1].id).toBe('F2-data')
    expect(section.questions[originalIndex].scope).toBe('metadata')
    expect(section.questions[originalIndex + 1].scope).toBe('data')
    expect(section.questions[originalIndex].text).toEqual(original!.text)
    expect(section.questions[originalIndex + 1].text).toEqual(original!.text)
    expect(section.questions[originalIndex].principle).toBe(original!.principle)
    expect(section.questions[originalIndex].ferType).toBe(original!.ferType)
    expect(section.questions.some((q) => q.id === 'F2')).toBe(false)
  })

  it('throws cannot_split on an id already ending in -metadata', () => {
    const content = fixture()
    expect(() => splitQuestion(content, 'F1-metadata')).toThrow(KmContentOpError)
    try {
      splitQuestion(content, 'F1-metadata')
    } catch (err) {
      expect(err).toBeInstanceOf(KmContentOpError)
      expect((err as KmContentOpError).code).toBe('cannot_split')
    }
  })

  it('throws cannot_split on an id already ending in -data', () => {
    const content = fixture()
    expect(() => splitQuestion(content, 'F1-data')).toThrow(KmContentOpError)
  })

  it('throws duplicate_question_id on a collision', () => {
    const content = addQuestion(fixture(), 'F', { id: 'F2-data', text: { en: 'Collides' } })
    expect(() => splitQuestion(content, 'F2')).toThrow(KmContentOpError)
    try {
      splitQuestion(content, 'F2')
    } catch (err) {
      expect((err as KmContentOpError).code).toBe('duplicate_question_id')
    }
  })
})

describe('kmContent — hide / unhide and visibleQuestionCount', () => {
  it('hideQuestion sets hidden: true and keeps the question in content', () => {
    const content = fixture()
    const hidden = hideQuestion(content, 'F1-metadata')
    const question = hidden.sections[0].questions.find((q) => q.id === 'F1-metadata')
    expect(question?.hidden).toBe(true)
    expect(hidden.sections[0].questions).toHaveLength(content.sections[0].questions.length)
  })

  it('unhideQuestion removes the flag again', () => {
    const content = hideQuestion(fixture(), 'F1-metadata')
    const unhidden = unhideQuestion(content, 'F1-metadata')
    const question = unhidden.sections[0].questions.find((q) => q.id === 'F1-metadata')
    expect(question?.hidden).toBeUndefined()
  })

  it('visibleQuestionCount is 21 on the real fixture and 20 after hiding one', () => {
    const content = fixture()
    expect(visibleQuestionCount(content)).toBe(21)
    expect(visibleQuestionCount(hideQuestion(content, 'F1-metadata'))).toBe(20)
  })
})

describe('kmContent — addSection / addQuestion / deleteQuestion / deleteSection / setFerType', () => {
  it('addSection appends an empty section', () => {
    const content = addSection(fixture(), { id: 'extra', title: { en: 'Extra' } })
    expect(content.sections[content.sections.length - 1]).toEqual({
      id: 'extra',
      title: { en: 'Extra' },
      questions: [],
    })
  })

  it('addQuestion appends with the spec defaults', () => {
    const content = addQuestion(fixture(), 'F', { id: 'new-q', text: { en: 'New question' } })
    const question = content.sections[0].questions[content.sections[0].questions.length - 1]
    expect(question).toMatchObject({
      id: 'new-q',
      principle: null,
      scope: null,
      ferType: null,
      required: false,
      allowMultiple: true,
    })
  })

  it('deleteQuestion removes exactly that question', () => {
    const content = deleteQuestion(fixture(), 'F1-metadata')
    expect(content.sections[0].questions.some((q) => q.id === 'F1-metadata')).toBe(false)
    expect(visibleQuestionCount(content)).toBe(20)
  })

  it('deleteSection removes the whole section', () => {
    const content = deleteSection(fixture(), 'F')
    expect(content.sections.some((s) => s.id === 'F')).toBe(false)
  })

  it('setFerType changes only the targeted question', () => {
    const content = setFerType(fixture(), 'F1-metadata', null)
    expect(content.sections[0].questions.find((q) => q.id === 'F1-metadata')?.ferType).toBeNull()
    expect(content.sections[0].questions.find((q) => q.id === 'F1-data')?.ferType).toBe('identifier-service')
  })
})

describe('kmContent — setText', () => {
  it('writing a value sets the language key', () => {
    const content = setText(fixture(), { field: 'questionText', questionId: 'F1-metadata' }, 'pt-PT', 'Novo texto')
    expect(content.sections[0].questions[0].text['pt-PT']).toBe('Novo texto')
  })

  it('writing an empty string deletes the key', () => {
    const content = setText(fixture(), { field: 'questionText', questionId: 'F1-metadata' }, 'pt-PT', '')
    expect('pt-PT' in content.sections[0].questions[0].text).toBe(false)
  })

  it('deleting "en" throws', () => {
    expect(() => setText(fixture(), { field: 'title' }, 'en', '')).toThrow(KmContentOpError)
  })

  it('deleting the last help key turns help into null', () => {
    // 'en' cannot be deleted from `text`, but `help` has no such
    // restriction — it may legitimately become empty and collapse to null.
    const content = fixture()
    content.sections[0].questions[0].help = { en: 'Only English help' }
    const result = setText(content, { field: 'questionHelp', questionId: 'F1-metadata' }, 'en', '')
    expect(result.sections[0].questions[0].help).toBeNull()
  })
})

describe('kmContent — completeness', () => {
  it('is 21/21 on the untouched real fixture for every supported language', () => {
    const content = fixture()
    expect(completeness(content, 'en')).toEqual({ done: 21, total: 21 })
    expect(completeness(content, 'pt-PT')).toEqual({ done: 21, total: 21 })
    expect(completeness(content, 'pt-BR')).toEqual({ done: 21, total: 21 })
  })

  it('drops by one per question missing that language', () => {
    let content = setText(fixture(), { field: 'questionText', questionId: 'F1-metadata' }, 'pt-PT', '')
    content = setText(content, { field: 'questionText', questionId: 'F1-data' }, 'pt-PT', '')
    expect(completeness(content, 'pt-PT')).toEqual({ done: 19, total: 21 })
  })
})

// Criterion 13 / 11's fixture table, mirrored here so the frontend validator
// agrees with `backend/fipm/km_content.py`'s `validate_content`.
describe('kmContent — validateContent', () => {
  it('returns [] for the real gofair-fip-mini-1.0.0.json', () => {
    expect(validateContent(fixture(), FER_TYPE_KEYS)).toEqual([])
  })

  it('flags a duplicate question id at the second occurrence, path and code exact', () => {
    const content = fixture()
    content.sections[0].questions[1] = { ...content.sections[0].questions[1], id: content.sections[0].questions[0].id }
    const errors = validateContent(content, FER_TYPE_KEYS)
    expect(errors).toContainEqual({
      path: 'sections[0].questions[1].id',
      code: 'duplicate_question_id',
      message: expect.any(String),
    })
  })

  it('flags an unknown ferType', () => {
    const content = fixture()
    content.sections[0].questions[0].ferType = 'not-a-real-type'
    const errors = validateContent(content, FER_TYPE_KEYS)
    expect(errors).toContainEqual({
      path: 'sections[0].questions[0].ferType',
      code: 'unknown_fer_type',
      message: expect.any(String),
    })
  })

  it('flags an unknown principle', () => {
    const content = fixture()
    content.sections[0].questions[0].principle = 'Z9'
    const errors = validateContent(content, FER_TYPE_KEYS)
    expect(errors).toContainEqual({
      path: 'sections[0].questions[0].principle',
      code: 'unknown_principle',
      message: expect.any(String),
    })
  })

  it('flags a question text missing "en"', () => {
    const content = fixture()
    content.sections[0].questions[0].text = { 'pt-PT': 'Só português' }
    const errors = validateContent(content, FER_TYPE_KEYS)
    expect(errors).toContainEqual({
      path: 'sections[0].questions[0].text',
      code: 'missing_en',
      message: expect.any(String),
    })
  })

  it('flags a bad scope value', () => {
    const content = fixture()
    // @ts-expect-error deliberately invalid for the test
    content.sections[0].questions[0].scope = 'nonsense'
    const errors = validateContent(content, FER_TYPE_KEYS)
    expect(errors).toContainEqual({
      path: 'sections[0].questions[0].scope',
      code: 'invalid_value',
      message: expect.any(String),
    })
  })

  it('flags too many questions over the 300 cap', () => {
    const content = fixture()
    const section = content.sections[0]
    const template = section.questions[0]
    for (let i = 0; i < 301; i += 1) {
      section.questions.push({ ...template, id: `extra-${i}` })
    }
    const errors = validateContent(content, FER_TYPE_KEYS)
    expect(errors).toContainEqual({
      path: 'sections',
      code: 'too_many',
      message: expect.any(String),
    })
  })
})
