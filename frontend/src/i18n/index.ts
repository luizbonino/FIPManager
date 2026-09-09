import { createI18n } from 'vue-i18n'
import en from './en.json'
import ptPT from './pt-PT.json'
import ptBR from './pt-BR.json'
import es from './es.json'

export type Locale = 'en' | 'pt-PT' | 'pt-BR' | 'es'

type MessageSchema = typeof en

export const SUPPORTED_LOCALES: Locale[] = ['en', 'pt-PT', 'pt-BR', 'es']

// pt-PT/pt-BR/es are translated independently of en and may be mid-update at
// any given time (missing keys fall back via `fallbackLocale` at runtime),
// so their shape is not guaranteed to match `MessageSchema` structurally.
export const messages: Record<Locale, MessageSchema> = {
  'en': en,
  'pt-PT': ptPT as unknown as MessageSchema,
  'pt-BR': ptBR as unknown as MessageSchema,
  'es': es as unknown as MessageSchema,
}

function getBrowserLocale(): Locale {
  const browserLocales = navigator.languages || []

  for (const locale of browserLocales) {
    const baseLocale = locale.split('-')[0]
    const regionLocale = locale.split('-')[0] + '-' + (locale.split('-')[1] || '').toUpperCase()

    if (SUPPORTED_LOCALES.includes(regionLocale as Locale)) {
      return regionLocale as Locale
    }

    if (baseLocale === 'pt') {
      return 'pt-PT'
    }

    // 'es' (unlike 'pt') is itself a supported locale, so any 'es-*' variant
    // (es-ES, es-MX, es-419, ...) is caught by the generic check below.
    if (SUPPORTED_LOCALES.includes(baseLocale as Locale)) {
      return baseLocale as Locale
    }
  }

  return 'en'
}

function getStoredLocale(): Locale | null {
  const stored = localStorage.getItem('fip-language')
  if (stored && SUPPORTED_LOCALES.includes(stored as Locale)) {
    return stored as Locale
  }
  return null
}

export function getInitialLocale(): Locale {
  const storedLocale = getStoredLocale()
  if (storedLocale) {
    return storedLocale
  }
  
  const browserLocale = getBrowserLocale()
  
  return browserLocale
}

export function setupI18n() {
  const initialLocale = getInitialLocale()
  
  const i18n = createI18n({
    legacy: false,
    locale: initialLocale,
    fallbackLocale: {
      'pt-PT': ['pt-BR', 'en'],
      'pt-BR': ['pt-PT', 'en'],
      'es': ['en'],
      'en': ['en'],
    },
    messages,
    globalInjection: true,
  })

  return i18n
}

export function setLocale(locale: Locale) {
  localStorage.setItem('fip-language', locale)
  const i18n = setupI18n()
  i18n.global.locale.value = locale
  return i18n
}
