import { describe, expect, it } from 'vitest'
import { resolveLang } from './lang'

// Criterion 9 (docs/specs/02-core-flows.md §8): the same six cases are
// mirrored in the pytest suite as a table test against
// `fipm.exporters.resolve_lang`, so the two implementations cannot drift.
describe('resolveLang', () => {
  it('exact locale wins', () => {
    const map = { en: 'Hello', 'pt-PT': 'Ola PT', 'pt-BR': 'Ola BR' }
    expect(resolveLang(map, 'pt-PT')).toBe('Ola PT')
  })

  it('pt-PT missing falls back to pt-BR then en', () => {
    expect(resolveLang({ en: 'Hello', 'pt-BR': 'Ola BR' }, 'pt-PT')).toBe('Ola BR')
    expect(resolveLang({ en: 'Hello' }, 'pt-PT')).toBe('Hello')
  })

  it('pt-BR missing falls back to pt-PT then en', () => {
    expect(resolveLang({ en: 'Hello', 'pt-PT': 'Ola PT' }, 'pt-BR')).toBe('Ola PT')
    expect(resolveLang({ en: 'Hello' }, 'pt-BR')).toBe('Hello')
  })

  it('a map with only de returns that value', () => {
    expect(resolveLang({ de: 'Hallo' }, 'pt-PT')).toBe('Hallo')
  })

  it('null returns null', () => {
    expect(resolveLang(null, 'en')).toBeNull()
  })

  it('an empty object returns null', () => {
    expect(resolveLang({}, 'en')).toBeNull()
  })
})
