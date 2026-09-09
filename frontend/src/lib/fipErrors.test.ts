import { describe, expect, it } from 'vitest'
import { ApiResponseError } from '@/api/client'
import { createFipErrorMessage } from './fipErrors'

// Identity translator so assertions can compare against the raw key.
const t = (key: string) => key

describe('createFipErrorMessage', () => {
  it('falls back to errors.serverError for a non-ApiResponseError', () => {
    expect(createFipErrorMessage(t, new Error('boom'))).toBe('errors.serverError')
  })

  it('maps known session details the same regardless of context', () => {
    expect(createFipErrorMessage(t, new ApiResponseError(404, { detail: 'session_not_found' }))).toBe(
      'join.invalidCode'
    )
    expect(createFipErrorMessage(t, new ApiResponseError(409, { detail: 'session_closed' }))).toBe('join.closed')
  })

  it('maps email_verification_required to the existing i18n key', () => {
    expect(
      createFipErrorMessage(t, new ApiResponseError(403, { detail: 'email_verification_required' }), 'standalone')
    ).toBe('errors.emailVerificationRequired')
    expect(
      createFipErrorMessage(t, new ApiResponseError(403, { detail: 'email_verification_required' }), 'join')
    ).toBe('errors.emailVerificationRequired')
  })

  describe('unmapped 403 fallback', () => {
    it('defaults (join context) to join.invalidCode, unchanged from before', () => {
      expect(createFipErrorMessage(t, new ApiResponseError(403, { detail: 'some_unmapped_reason' }))).toBe(
        'join.invalidCode'
      )
      expect(
        createFipErrorMessage(t, new ApiResponseError(403, { detail: 'some_unmapped_reason' }), 'join')
      ).toBe('join.invalidCode')
    })

    it('in standalone context falls back to errors.serverError instead', () => {
      expect(
        createFipErrorMessage(t, new ApiResponseError(403, { detail: 'some_unmapped_reason' }), 'standalone')
      ).toBe('errors.serverError')
    })
  })

  it('keeps status-code fallbacks for 429 and 409 unaffected by context', () => {
    expect(createFipErrorMessage(t, new ApiResponseError(429, { detail: 'x' }), 'standalone')).toBe(
      'errors.rateLimited'
    )
    expect(createFipErrorMessage(t, new ApiResponseError(409, { detail: 'x' }), 'standalone')).toBe('join.closed')
  })

  it('falls back to errors.serverError for an unmapped, unrecognised status', () => {
    expect(createFipErrorMessage(t, new ApiResponseError(500, { detail: 'oops' }))).toBe('errors.serverError')
  })
})
