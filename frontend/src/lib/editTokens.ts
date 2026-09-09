/**
 * Per-FIP edit-token storage (spec 02 §2.1/§2.5): `localStorage['fipm.editToken.<fipId>']`.
 * Every call is wrapped in try/catch — private-mode Safari throws on any
 * localStorage access, and losing the token should degrade to read-only,
 * never crash the app.
 */

import type { LocationQuery } from 'vue-router'

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
 * Spec 09: the FIP ids this device holds an edit token for — Home.vue's
 * "FIPs on this device" list for anonymous visitors. Order is whatever
 * `localStorage` iterates in (insertion order in every browser this app
 * targets); callers that care about a cap slice the result themselves.
 */
export function listTokenFipIds(): string[] {
  const ids: string[] = []
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key && key.startsWith(PREFIX)) {
        ids.push(key.slice(PREFIX.length))
      }
    }
  } catch {
    // Storage unavailable: nothing to list.
  }
  return ids
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

/**
 * The "edit link" (spec 09 follow-up: an edit token today lives only in
 * `localStorage`, so a participant has no way to move a FIP to another
 * device or hand it to a colleague). FipEditor.vue calls this on setup
 * with `route.query`: if `?token=...` is present and non-empty, it's
 * stored via `setToken` — the same one that GET requests already send as
 * `X-Edit-Token` — and returned so the caller can strip it from the URL
 * with `router.replace` before it lingers in the address bar or history.
 * Returns `null` (and stores nothing) when there's no token to adopt.
 */
export function adoptTokenFromQuery(fipId: string, query: LocationQuery): string | null {
  const raw = query.token
  const token = typeof raw === 'string' ? raw : null
  if (!token) return null
  setToken(fipId, token)
  return token
}
