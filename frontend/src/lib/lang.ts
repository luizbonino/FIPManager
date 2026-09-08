import type { LangMap } from '@/types/api'

/**
 * Resolve a `LangMap` to a single string for `locale`, mirroring
 * `fipm.exporters.resolve_lang` exactly (spec 02 §1) so the two
 * implementations cannot drift: exact locale -> `pt-PT` <-> `pt-BR` sibling
 * -> `fallback` -> first available value -> `null`.
 */
export function resolveLang(
  map: LangMap | null | undefined,
  locale: string,
  fallback = 'en'
): string | null {
  if (!map) return null
  if (locale in map) return map[locale]
  if (locale === 'pt-PT' && 'pt-BR' in map) return map['pt-BR']
  if (locale === 'pt-BR' && 'pt-PT' in map) return map['pt-PT']
  if (fallback in map) return map[fallback]
  for (const value of Object.values(map)) {
    return value
  }
  return null
}
