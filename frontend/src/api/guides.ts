import { get } from './client'

/** `GET /api/guides`: the guides available, and which languages each has an on-disk source for. */
export interface GuideListItem {
  id: string
  languages: string[]
}

export interface GuideListOut {
  items: GuideListItem[]
}

/**
 * `GET /api/guides/{id}?lang=`: `language` is what was actually served
 * after the pt-PT <-> pt-BR -> en fallback (mirrors `resolveLang`,
 * `@/lib/lang`), which may differ from the `lang` that was asked for.
 */
export interface GuideOut {
  id: string
  language: string
  markdown: string
}

export function listGuides() {
  return get<GuideListOut>('/guides')
}

export function getGuide(id: string, lang: string) {
  return get<GuideOut>(`/guides/${id}?lang=${encodeURIComponent(lang)}`)
}
