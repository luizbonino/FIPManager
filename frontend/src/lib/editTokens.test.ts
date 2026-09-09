import { beforeEach, describe, expect, it } from 'vitest'
import type { LocationQuery } from 'vue-router'
import { adoptTokenFromQuery, getToken } from './editTokens'

// Spec 09 follow-up: the edit link (`/fips/:id/edit?token=...`) hands this
// device edit rights via the URL instead of only localStorage.
// FipEditor.vue calls `adoptTokenFromQuery` on setup before loading the
// FIP, then strips `token` from the query with `router.replace`. Since
// FipEditor.vue has no existing test file to extend, this exercises the
// extracted, router-free helper directly.
describe('adoptTokenFromQuery', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('stores the token and returns it when query.token is a non-empty string', () => {
    const result = adoptTokenFromQuery('fip-1', { token: 'secret-abc' } as LocationQuery)

    expect(result).toBe('secret-abc')
    expect(getToken('fip-1')).toBe('secret-abc')
  })

  it('returns null and stores nothing when there is no token in the query', () => {
    const result = adoptTokenFromQuery('fip-1', {} as LocationQuery)

    expect(result).toBeNull()
    expect(getToken('fip-1')).toBeNull()
  })

  it('returns null and stores nothing when query.token is an empty string', () => {
    const result = adoptTokenFromQuery('fip-1', { token: '' } as LocationQuery)

    expect(result).toBeNull()
    expect(getToken('fip-1')).toBeNull()
  })

  it('returns null and stores nothing when query.token is an array (repeated query param)', () => {
    const result = adoptTokenFromQuery('fip-1', { token: ['a', 'b'] } as LocationQuery)

    expect(result).toBeNull()
    expect(getToken('fip-1')).toBeNull()
  })

  it('returns null and stores nothing when query.token is null', () => {
    const result = adoptTokenFromQuery('fip-1', { token: null } as LocationQuery)

    expect(result).toBeNull()
    expect(getToken('fip-1')).toBeNull()
  })
})
