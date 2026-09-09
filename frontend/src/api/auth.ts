import { post } from './client'
import type { User } from '@/stores/auth'

/**
 * spec 07 §2/§3: mail-backed account flows. `stores/auth.ts` keeps the
 * sign-in/register/logout/me calls it already had (and the `verificationRequired`
 * flag piggybacked on `GET /api/auth/me`) — this file adds only the new
 * verification/reset endpoints, which no store needs to hold state for.
 */

/** `POST /api/auth/verify-email {token}` — 200 `UserOut` on success, no auth (the token is the credential). */
export function verifyEmail(token: string) {
  return post<User>('/auth/verify-email', { token })
}

/** `POST /api/auth/verify-email/resend` (U) — 202 always, even if already verified. */
export function resendVerification() {
  return post<void>('/auth/verify-email/resend')
}

/** `POST /api/auth/password-reset/request {email}` — always 202, empty body, whatever the address. */
export function requestPasswordReset(email: string) {
  return post<void>('/auth/password-reset/request', { email })
}

/** `POST /api/auth/password-reset/confirm {token, newPassword}` — 204 on success. */
export function confirmPasswordReset(token: string, newPassword: string) {
  return post<void>('/auth/password-reset/confirm', { token, newPassword })
}
