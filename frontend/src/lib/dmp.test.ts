import { describe, expect, it } from 'vitest'
import { detectSystem, normaliseDmpUrl } from './dmp'

// Criterion 11 (docs/specs/06-dmp-linkage.md §5): reproduces the §1.1
// normalisation table also asserted server-side against
// `fipm.dmp.normalise_related_dmps` — the two implementations must agree.
describe('normaliseDmpUrl', () => {
  it('lowercases scheme and host, drops a default port, fragment and empty query, strips a trailing slash', () => {
    expect(normaliseDmpUrl('HTTPS://WWW.FioDMP.fiocruz.br:443/publico/KQU5N0C/')).toBe(
      'https://www.fiodmp.fiocruz.br/publico/KQU5N0C'
    )
    expect(normaliseDmpUrl('https://example.org/plan?')).toBe('https://example.org/plan')
    expect(normaliseDmpUrl('https://example.org/')).toBe('https://example.org')
  })

  it('keeps a non-empty query but drops the fragment', () => {
    expect(normaliseDmpUrl('https://example.org/plan?x=1#f')).toBe('https://example.org/plan?x=1')
  })

  it('trims surrounding whitespace', () => {
    expect(normaliseDmpUrl('  https://example.org/plan  ')).toBe('https://example.org/plan')
  })

  it('rejects a non-https scheme', () => {
    expect(normaliseDmpUrl('http://example.org/plan')).toBeNull()
    expect(normaliseDmpUrl('javascript:alert(1)')).toBeNull()
  })

  it('rejects a URL with userinfo, internal whitespace, or no host', () => {
    expect(normaliseDmpUrl('https://user:pass@example.org/plan')).toBeNull()
    expect(normaliseDmpUrl('https://exa mple.org/plan')).toBeNull()
    expect(normaliseDmpUrl('https://')).toBeNull()
  })

  it('rejects an empty string and a URL over 2048 chars', () => {
    expect(normaliseDmpUrl('')).toBeNull()
    expect(normaliseDmpUrl('   ')).toBeNull()
    expect(normaliseDmpUrl(`https://example.org/${'a'.repeat(2048)}`)).toBeNull()
  })
})

describe('detectSystem', () => {
  it('recognises FioDMP with www and /publico/, canonicalising to an uppercase id', () => {
    const normalised = normaliseDmpUrl('https://www.fiodmp.fiocruz.br/publico/kqu5n0c')!
    expect(detectSystem(normalised)).toEqual({
      url: 'https://fiodmp.fiocruz.br/KQU5N0C',
      system: 'FioDMP',
      dmpId: 'KQU5N0C',
    })
  })

  it('recognises FioDMP without www or /publico/, and with a trailing slash already stripped', () => {
    const normalised = normaliseDmpUrl('https://fiodmp.fiocruz.br/kqu5n0c/')!
    expect(detectSystem(normalised)).toEqual({
      url: 'https://fiodmp.fiocruz.br/KQU5N0C',
      system: 'FioDMP',
      dmpId: 'KQU5N0C',
    })
  })

  it('treats a generic URL as "other" with no dmpId, URL unchanged', () => {
    const normalised = normaliseDmpUrl('https://example.org/plan?x=1#f')!
    expect(detectSystem(normalised)).toEqual({
      url: 'https://example.org/plan?x=1',
      system: 'other',
    })
  })

  it('an id outside the 4-16 alphanumeric range is treated as "other"', () => {
    const normalised = normaliseDmpUrl('https://fiodmp.fiocruz.br/abc')!
    expect(detectSystem(normalised).system).toBe('other')
  })
})
