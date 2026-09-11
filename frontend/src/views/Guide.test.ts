import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
import type { GuideOut } from '@/api/guides'

vi.mock('@/api/guides', () => ({
  getGuide: vi.fn(),
}))

import { getGuide } from '@/api/guides'
import Guide from './Guide.vue'

const getGuideMock = vi.mocked(getGuide)

function makeI18n(locale = 'en') {
  return createI18n({ legacy: false, locale, messages: { en } })
}

async function mountGuide(guideId: 'participant' | 'administrator', locale = 'en'): Promise<{
  wrapper: Awaited<ReturnType<typeof mount>>
  router: Router
}> {
  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/guide', name: 'GuideParticipant', component: Guide, props: { guideId: 'participant' } },
      { path: '/guide/admin', name: 'GuideAdmin', component: Guide, props: { guideId: 'administrator' } },
    ],
  })
  await router.push(guideId === 'participant' ? '/guide' : '/guide/admin')
  await router.isReady()

  const wrapper = mount(Guide, {
    props: { guideId },
    global: { plugins: [makeI18n(locale), router] },
  })
  await flushPromises()
  return { wrapper, router }
}

function makeGuide(overrides: Partial<GuideOut> = {}): GuideOut {
  return {
    id: 'participant',
    language: 'en',
    markdown: '# Filling in a FIP\n\n## 1. Overview\n\nSome text.\n\n[jump](#1-overview)\n',
    ...overrides,
  }
}

describe('Guide.vue (guides in the app)', () => {
  beforeEach(() => {
    getGuideMock.mockReset()
  })

  it('fetches and renders the participant guide for the current locale', async () => {
    getGuideMock.mockResolvedValue(makeGuide())

    const { wrapper } = await mountGuide('participant', 'en')

    expect(getGuideMock).toHaveBeenCalledWith('participant', 'en')
    expect(wrapper.text()).toContain('Some text.')
    expect(document.title).toContain(en.guide.participantTitle)
  })

  it('fetches the administrator guide when guideId is administrator', async () => {
    getGuideMock.mockResolvedValue(makeGuide({ id: 'administrator' }))

    await mountGuide('administrator', 'en')

    expect(getGuideMock).toHaveBeenCalledWith('administrator', 'en')
    expect(document.title).toContain(en.guide.administratorTitle)
  })

  it('renders the markdown H1 once, without a separate duplicate title heading', async () => {
    getGuideMock.mockResolvedValue(makeGuide())

    const { wrapper } = await mountGuide('participant', 'en')

    expect(wrapper.findAll('h1')).toHaveLength(1)
    expect(wrapper.find('h1').text()).toBe('Filling in a FIP')
  })

  it('shows no fallback notice when the served language matches the interface locale', async () => {
    getGuideMock.mockResolvedValue(makeGuide({ language: 'en' }))

    const { wrapper } = await mountGuide('participant', 'en')

    expect(wrapper.find('.fallback-notice').exists()).toBe(false)
  })

  it('shows a fallback notice naming the served language when it differs from the interface locale', async () => {
    // Interface stays in English; the guide itself falls back to pt-PT
    // (no en/pt-BR source yet). Keeping the mounted i18n instance in 'en'
    // (only locale with messages loaded here) exercises the comparison
    // logic without needing pt-PT UI strings.
    getGuideMock.mockResolvedValue(makeGuide({ language: 'pt-PT' }))

    const { wrapper } = await mountGuide('participant', 'en')

    const notice = wrapper.find('.fallback-notice')
    expect(notice.exists()).toBe(true)
    expect(notice.text()).toContain(en.languages['pt-PT'])
  })

  it('assigns a GitHub-style slug id to rendered headings so in-page anchors resolve', async () => {
    getGuideMock.mockResolvedValue(makeGuide())

    const { wrapper } = await mountGuide('participant', 'en')

    const heading = wrapper.find('h2')
    expect(heading.attributes('id')).toBe('1-overview')
  })

  it('keeps accented characters in the slug id, matching the guides own hand-written TOC anchors', async () => {
    // Headings copied verbatim from docs/participant-guide.pt-PT.md and
    // docs/administrator-guide.es.md, whose own "Índice"/"Tabla de
    // contenidos" sections link `#3-o-editor-à-primeira-vista` and
    // `#9-el-catálogo-fer` respectively. A `\w`-only (ASCII) slug strips
    // every accented character and breaks these anchors (review finding 3).
    getGuideMock.mockResolvedValue(
      makeGuide({
        markdown: '# G\n\n## 3. O editor à primeira vista\n\nA.\n\n## 9. El catálogo FER\n\nB.\n',
      })
    )

    const { wrapper } = await mountGuide('participant', 'en')

    const headings = wrapper.findAll('h2')
    expect(headings.map((h) => h.attributes('id'))).toEqual([
      '3-o-editor-à-primeira-vista',
      '9-el-catálogo-fer',
    ])
  })

  it('de-duplicates heading ids when two headings render the same slug', async () => {
    getGuideMock.mockResolvedValue(
      makeGuide({ markdown: '# T\n\n## Step\n\nA.\n\n## Step\n\nB.\n' })
    )

    const { wrapper } = await mountGuide('participant', 'en')

    const headings = wrapper.findAll('h2')
    expect(headings.map((h) => h.attributes('id'))).toEqual(['step', 'step-1'])
  })

  it('renders a not-found message when the API call fails', async () => {
    getGuideMock.mockRejectedValue(new Error('boom'))

    const { wrapper } = await mountGuide('participant', 'en')

    expect(wrapper.text()).toContain(en.common.notFound)
  })

  it('offers a switcher link to the other guide', async () => {
    getGuideMock.mockResolvedValue(makeGuide())

    const { wrapper } = await mountGuide('participant', 'en')

    const adminLink = wrapper.find('a[href="/guide/admin"]')
    expect(adminLink.exists()).toBe(true)
    expect(adminLink.text()).toBe(en.guide.administratorLabel)
  })
})
