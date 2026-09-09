import { get } from './client'

/** `GET /api/privacy?lang=` (spec 05 §2): one version across every language. */
export interface PrivacyNotice {
  version: string
  date: string
  lang: string
  markdown: string
}

export function getPrivacyNotice(lang: string) {
  return get<PrivacyNotice>(`/privacy?lang=${encodeURIComponent(lang)}`)
}
