import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
import type { FipOut, KnowledgeModelOut } from '@/types/api'

// spec 11 §3.6: the one-time "prefilled from the network" banner
// (`networkPrefillInfo`), carried via `?networkCommunity=&networkImported=
// &networkSkipped=` on the navigation from `NetworkFipDetail.vue`'s "Use as
// starting point" and read/stripped once in `init()`.
vi.mock('@/api/fips', () => ({
  getFip: vi.fn(),
  patchFip: vi.fn(),
  claimFip: vi.fn(),
  deleteFip: vi.fn(),
  getMigrationTargets: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  fipExportJsonUrl: vi.fn(() => 'json-url'),
  fipExportCsvUrl: vi.fn(() => 'csv-url'),
  fipExportTtlUrl: vi.fn(() => 'ttl-url'),
  fipExportJsonldUrl: vi.fn(() => 'jsonld-url'),
}))
vi.mock('@/api/knowledgeModels', () => ({
  getKnowledgeModel: vi.fn(),
}))
vi.mock('@/api/fers', () => ({
  listFers: vi.fn().mockResolvedValue({ items: [], total: 0 }),
}))
vi.mock('@/api/ferTypes', () => ({
  getFerTypes: vi.fn().mockResolvedValue({ items: [], total: 0 }),
}))
vi.mock('@/api/sessions', () => ({
  getSession: vi.fn(),
}))
vi.mock('@/lib/editTokens', () => ({
  adoptTokenFromQuery: vi.fn(() => null),
  getToken: vi.fn(() => 'tok-1'),
  clearToken: vi.fn(),
}))

import { getFip } from '@/api/fips'
import { getKnowledgeModel } from '@/api/knowledgeModels'
import FipEditor from './FipEditor.vue'

const getFipMock = vi.mocked(getFip)
const getKnowledgeModelMock = vi.mocked(getKnowledgeModel)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function makeFip(overrides: Partial<FipOut> = {}): FipOut {
  return {
    id: 'fip-1',
    ownerId: null,
    sessionId: null,
    visibility: 'link',
    questionnaireId: 'gofair-fip-mini',
    questionnaireVersion: '1.0.0',
    title: 'Test community',
    community: { name: 'Test community', links: [] },
    relatedDmps: [],
    answers: [],
    language: 'en',
    license: 'CC0-1.0',
    createdAt: '2026-09-01T00:00:00Z',
    updatedAt: '2026-09-01T00:00:00Z',
    ...overrides,
  }
}

function makeKm(): KnowledgeModelOut {
  return {
    id: 'gofair-fip-mini',
    version: '1.0.0',
    status: 'published',
    visibility: 'public',
    license: 'CC0-1.0',
    source: 'GO FAIR FIP mini-questionnaire',
    title: { en: 'Mini FIP' },
    description: { en: '' },
    changelog: [],
    content: {
      id: 'gofair-fip-mini',
      version: '1.0.0',
      status: 'published',
      license: 'CC0-1.0',
      title: { en: 'Mini FIP' },
      description: { en: '' },
      changelog: [],
      sections: [],
    },
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
  }
}

async function mountEditor(id: string, query: Record<string, string> = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)

  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/fips/:id/edit', name: 'FipEditor', component: FipEditor, props: true },
      { path: '/fips/:id', name: 'FipRead', component: { template: '<div/>' } },
    ],
  })
  await router.push({ path: `/fips/${id}/edit`, query })
  await router.isReady()

  const wrapper = mount(FipEditor, { global: { plugins: [pinia, makeI18n(), router] }, shallow: true })
  await flushPromises()
  return { wrapper, router }
}

describe('FipEditor.vue — network-prefill banner', () => {
  beforeEach(() => {
    getFipMock.mockReset()
    getKnowledgeModelMock.mockReset().mockResolvedValue(makeKm())
  })

  it('shows the banner on the navigation carrying ?networkCommunity=&networkImported=&networkSkipped=', async () => {
    getFipMock.mockResolvedValue(
      makeFip({
        id: 'fip-1',
        networkOrigin: {
          communityIri: 'http://purl.org/np/RA1#CommunityA',
          fipNanopubIri: 'https://w3id.org/np/RA-fip1',
          indexIri: 'https://w3id.org/np/RA-index1',
          fetchedAt: '2026-09-01T00:00:00Z',
        },
      })
    )

    const { wrapper } = await mountEditor('fip-1', {
      networkCommunity: 'Community A',
      networkImported: '5',
      networkSkipped: '1',
    })

    const banner = wrapper.find('.network-prefill-banner')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('Community A')
  })

  // Bug fix: `networkPrefillInfo` was only ever set (never reset) in
  // `init()`, so editor->editor navigation (the `watch(() => route.params.id
  // , ...)` below, same route record + component instance, different `:id`)
  // could carry the *first* FIP's community label into the second FIP's
  // banner — even when that navigation carries no `?networkCommunity=` of
  // its own and the second FIP happens to also have a (different, or no)
  // `networkOrigin`.
  it('does not carry the first FIP\'s banner over to a second FIP navigated to without network query params', async () => {
    getFipMock.mockImplementation(async (id: string) => {
      if (id === 'fip-1') {
        return makeFip({
          id: 'fip-1',
          networkOrigin: {
            communityIri: 'http://purl.org/np/RA1#CommunityA',
            fipNanopubIri: 'https://w3id.org/np/RA-fip1',
            indexIri: 'https://w3id.org/np/RA-index1',
            fetchedAt: '2026-09-01T00:00:00Z',
          },
        })
      }
      // fip-2 also has a networkOrigin (it was itself created from the
      // network, at some point) -- but this navigation to it carries no
      // `?networkCommunity=` of its own, so no banner should show at all.
      return makeFip({
        id: 'fip-2',
        networkOrigin: {
          communityIri: 'http://purl.org/np/RA2#CommunityB',
          fipNanopubIri: 'https://w3id.org/np/RA-fip2',
          indexIri: 'https://w3id.org/np/RA-index2',
          fetchedAt: '2026-08-01T00:00:00Z',
        },
      })
    })

    const { wrapper, router } = await mountEditor('fip-1', {
      networkCommunity: 'Community A',
      networkImported: '5',
      networkSkipped: '1',
    })
    expect(wrapper.find('.network-prefill-banner').exists()).toBe(true)

    await router.push('/fips/fip-2/edit')
    await flushPromises()

    const banner = wrapper.find('.network-prefill-banner')
    expect(banner.exists()).toBe(false)
  })

  it('shows no banner for a FIP with no networkOrigin at all', async () => {
    getFipMock.mockResolvedValue(makeFip({ id: 'fip-3' }))

    const { wrapper } = await mountEditor('fip-3')

    expect(wrapper.find('.network-prefill-banner').exists()).toBe(false)
  })
})
