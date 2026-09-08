/**
 * Per-FIP edit-token storage (spec 02 §2.1/§2.5): `localStorage['fipm.editToken.<fipId>']`.
 * Every call is wrapped in try/catch — private-mode Safari throws on any
 * localStorage access, and losing the token should degrade to read-only,
 * never crash the app.
 */

const PREFIX = 'fipm.editToken.'

export function getToken(fipId: string): string | null {
  try {
    return localStorage.getItem(PREFIX + fipId)
  } catch {
    return null
  }
}

export function setToken(fipId: string, token: string): void {
  try {
    localStorage.setItem(PREFIX + fipId, token)
  } catch {
    // Storage unavailable: edit rights on this device simply won't persist
    // across reloads, which is the same failure mode as clearing storage.
  }
}

export function clearToken(fipId: string): void {
  try {
    localStorage.removeItem(PREFIX + fipId)
  } catch {
    // Nothing to do if storage is unavailable.
  }
}

/**
 * Minimal addition beyond spec 02 §6.4's listed lib API: remembers which
 * FIP a device started within a given session, so JoinSession.vue's
 * "Continue your FIP" (§2.1 step 3) can find it without a server round
 * trip (anonymous callers cannot list a session's FIPs). Keyed separately
 * from the edit token itself so a claimed FIP (whose token is cleared,
 * spec 02 §2.5) can still be recognised as "already started" here.
 */
const SESSION_FIP_PREFIX = 'fipm.sessionFip.'

export function rememberSessionFip(sessionId: string, fipId: string): void {
  try {
    localStorage.setItem(SESSION_FIP_PREFIX + sessionId, fipId)
  } catch {
    // Storage unavailable: "Continue your FIP" simply won't appear next time.
  }
}

export function getSessionFip(sessionId: string): string | null {
  try {
    return localStorage.getItem(SESSION_FIP_PREFIX + sessionId)
  } catch {
    return null
  }
}
