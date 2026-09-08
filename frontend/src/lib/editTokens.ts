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
