import { ApiResponseError } from '@/api/client'

/**
 * Maps a `POST /api/fips` failure to user-facing copy. Shared by
 * JoinSession.vue (session-joining flow) and FipNew.vue (spec 09
 * standalone flow) — the session-specific `detail`s below simply never
 * occur on the standalone path, and the anonymous-standalone `detail`s
 * (`anonymous_fips_disabled`, `private_requires_account`, `rate_limited`)
 * are checked first so they win over any generic status fallback.
 *
 * `t` is the caller's `useI18n().t` — passed in rather than imported so
 * this stays a plain function (no composable-inside-composable ordering
 * issues) and is trivial to unit test.
 *
 * `context` distinguishes the two callers for the unmapped-403 fallback:
 * JoinSession's join codes make `join.invalidCode` ("invalid code") the
 * right generic message, but that copy makes no sense on FipNew's
 * standalone flow (there is no code to be invalid) — there the fallback
 * is the generic `errors.serverError`. Defaults to `'join'` so existing
 * JoinSession call sites are unaffected.
 */
export function createFipErrorMessage(
  t: (key: string) => string,
  err: unknown,
  context: 'join' | 'standalone' = 'join'
): string {
  if (!(err instanceof ApiResponseError)) return t('errors.serverError')
  switch (err.data.detail) {
    case 'session_not_found':
      return t('join.invalidCode')
    case 'session_closed':
      return t('join.closed')
    case 'questionnaire_not_found':
      return t('join.questionnaireUnavailable')
    case 'invalid_join_code':
      return t('join.invalidCode')
    case 'anonymous_fips_disabled':
      return t('errors.anonymousFipsDisabled')
    case 'private_requires_account':
      return t('errors.privateRequiresAccount')
    case 'rate_limited':
      return t('errors.rateLimited')
    case 'email_verification_required':
      return t('errors.emailVerificationRequired')
    default:
      if (err.status === 429) return t('errors.rateLimited')
      if (err.status === 409) return t('join.closed')
      if (err.status === 403) return context === 'standalone' ? t('errors.serverError') : t('join.invalidCode')
      return t('errors.serverError')
  }
}
