/**
 * Pure, client-side mirror of `backend/fipm/dmp.py`'s `normalise_related_dmps`
 * URL rules (spec 06 §1.1) — used by `DmpLinkList.vue` to show `dmp.urlInvalid`
 * inline on blur, before any request. The server remains the source of
 * truth: its normalised list always replaces local state from the PATCH
 * response, so this module only needs to agree with the backend closely
 * enough that a valid entry here is never rejected there.
 */

/** `FIPM_FIODMP_BASE_URL`'s default host (spec 06 §1.1) — not configurable client-side. */
export const FIODMP_HOST = 'fiodmp.fiocruz.br'

const FIODMP_URL_RE = /^https:\/\/(?:www\.)?fiodmp\.fiocruz\.br\/(?:publico\/)?([A-Za-z0-9]{4,16})$/

const MAX_URL_LENGTH = 2048
/** Any whitespace or C0/DEL control character anywhere in the trimmed URL is rejected. */
const FORBIDDEN_CHARS_RE = /[\s\x00-\x1f\x7f]/

/**
 * Trim; require an absolute `https://` URL, non-empty host, no userinfo, no
 * whitespace/control chars, <= 2048 chars; lowercase scheme + host (the
 * `URL` constructor already does this); drop a default port, a fragment and
 * an empty query; strip one trailing `/`. Returns `null` when the input
 * fails validation.
 */
export function normaliseDmpUrl(raw: string): string | null {
  const trimmed = raw.trim()
  if (!trimmed || trimmed.length > MAX_URL_LENGTH) return null
  if (FORBIDDEN_CHARS_RE.test(trimmed)) return null

  let parsed: URL
  try {
    parsed = new URL(trimmed)
  } catch {
    return null
  }

  if (parsed.protocol !== 'https:') return null
  if (!parsed.hostname) return null
  if (parsed.username || parsed.password) return null

  const port = parsed.port ? `:${parsed.port}` : ''
  let pathname = parsed.pathname
  if (pathname.endsWith('/')) {
    pathname = pathname.slice(0, -1)
  }
  const search = parsed.search === '?' ? '' : parsed.search

  return `https://${parsed.hostname}${port}${pathname}${search}`
}

export interface DetectedDmp {
  /** Canonical URL: the FioDMP form when `system === 'FioDMP'`, else `normalisedUrl` unchanged. */
  url: string
  system: 'FioDMP' | 'other'
  dmpId?: string
}

/**
 * Takes an already-`normaliseDmpUrl`-ed URL and checks it against the FioDMP
 * pattern `https://(www.)?fiodmp.fiocruz.br/(publico/)?<ID>` (4-16
 * alphanumeric chars). A match rewrites the URL to
 * `https://fiodmp.fiocruz.br/<ID upper>` and reports `dmpId` uppercased;
 * anything else is `system: 'other'` with the URL unchanged.
 */
export function detectSystem(normalisedUrl: string): DetectedDmp {
  const match = FIODMP_URL_RE.exec(normalisedUrl)
  if (match) {
    const dmpId = match[1].toUpperCase()
    return { url: `https://${FIODMP_HOST}/${dmpId}`, system: 'FioDMP', dmpId }
  }
  return { url: normalisedUrl, system: 'other' }
}
