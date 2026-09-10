import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
import { ApiResponseError } from '@/api/client'
import type { NetworkCommunityFipResponse, NetworkDeclaration, NetworkQuestion } from '@/types/network'

// spec 11 §3.5/§3.6: the community/FIP header, all 21 questions (gaps
// shown, never omitted), `unmapped` collapsed and separate, three distinct
// network error states, and "Use as starting point".
vi.mock('@/api/network', () => ({
  getCommunityFip: vi.fn(),
  createFipFromNetwork: vi.fn(),
}))
vi.mock('@/lib/editTokens', () => ({
  setToken: vi.fn(),
}))

import { createFipFromNetwork, getCommunityFip } from '@/api/network'
import { setToken } from '@/lib/editTokens'
import NetworkFipDetail from './NetworkFipDetail.vue'

const getCommunityFipMock = vi.mocked(getCommunityFip)
const createFipFromNetworkMock = vi.mocked(createFipFromNetwork)
const setTokenMock = vi.mocked(setToken)

const COMMUNITY_IRI = 'http://purl.org/np/RAoZ#PARCToxicology'

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function makeDeclaration(overrides: Partial<NetworkDeclaration> = {}): NetworkDeclaration {
  return {
    nanopubIri: 'https://w3id.org/np/RA-decl',
    status: 'current',
    resource: {
      iri: 'http://purl.org/np/RAtIF#ORCID',
      label: 'ORCID',
      comment: null,
      homepage: 'https://orcid.org/',
      types: [],
      ferTypeKey: 'identifier-service',
      inCatalogue: null,
    },
    considerations: null,
    startDate: null,
    endDate: null,
    ...overrides,
  }
}

/** 21 synthetic questions, Q1..Q21, odd-numbered ones carrying one declaration, even ones empty (a gap). */
function makeQuestions(): NetworkQuestion[] {
  return Array.from({ length: 21 }, (_, i) => {
    const n = i + 1
    return {
      questionId: `Q${n}`,
      questionIri: `https://w3id.org/fair/fip/terms/FIP-Question-Q${n}`,
      declarations: n % 2 === 1 ? [makeDeclaration()] : [],
    }
  })
}

function makeResponse(overrides: Partial<NetworkCommunityFipResponse> = {}): NetworkCommunityFipResponse {
  return {
    community: { iri: COMMUNITY_IRI, label: 'PARCToxicology' },
    fip: {
      nanopubIri: 'https://w3id.org/np/RAKa7',
      label: 'PARC Toxicology',
      indexIri: 'https://w3id.org/np/RATReWJ',
      created: '2026-09-07T12:48:22Z',
      startDate: null,
      endDate: null,
      otherVersions: [],
    },
    questions: makeQuestions(),
    unmapped: [],
    cachedAt: '2026-09-10T12:00:00Z',
    source: 'https://query.knowledgepixels.com',
    ...overrides,
  }
}

function makeRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/network/:communityIri', name: 'NetworkFipDetail', component: NetworkFipDetail, props: true },
      { path: '/fips/:id/edit', name: 'FipEditor', component: { template: '<div/>' } },
    ],
  })
}

async function mountDetail(query: Record<string, string> = {}) {
  const router = makeRouter()
  await router.push({ path: `/network/${encodeURIComponent(COMMUNITY_IRI)}`, query })
  await router.isReady()
  const wrapper = mount(NetworkFipDetail, { global: { plugins: [makeI18n(), router] } })
  await flushPromises()
  return { wrapper, router }
}

describe('NetworkFipDetail.vue', () => {
  beforeEach(() => {
    getCommunityFipMock.mockReset()
    createFipFromNetworkMock.mockReset()
    setTokenMock.mockReset()
  })

  it('calls getCommunityFip with the decoded communityIri', async () => {
    getCommunityFipMock.mockResolvedValue(makeResponse())

    await mountDetail()

    expect(getCommunityFipMock).toHaveBeenCalledWith(COMMUNITY_IRI)
  })

  it('renders all 21 questions, in payload order, with empty declarations shown as an explicit gap', async () => {
    getCommunityFipMock.mockResolvedValue(makeResponse())

    const { wrapper } = await mountDetail()

    const cards = wrapper.findAll('.sections .question-card')
    expect(cards).toHaveLength(21)
    const ids = cards.map((c) => c.find('.question-id').text())
    expect(ids).toEqual(Array.from({ length: 21 }, (_, i) => `Q${i + 1}`))

    // Q2 has no declarations -> an explicit "no declaration" gap, not omitted.
    const gapCard = cards[1]
    expect(gapCard.text()).toContain(en.network.noDeclaration)
    expect(gapCard.find('.declaration').exists()).toBe(false)

    // Q1 has one declaration -> rendered, not a gap.
    const filledCard = cards[0]
    expect(filledCard.text()).not.toContain(en.network.noDeclaration)
    expect(filledCard.text()).toContain('ORCID')
  })

  it('renders a "no choice" declaration (resource: null) without crashing, with the status badge, the noChoiceDeclared text, and a nanodash link', async () => {
    // Real shape of a "no choice" declaration from the nanopub network
    // (spec 11 §3.3's `?nochoice` case): `resource`, `considerations`,
    // `startDate` and `endDate` are all `null`.
    const noChoiceDeclaration: NetworkDeclaration = {
      nanopubIri: 'https://w3id.org/np/RA-nochoice',
      status: 'none',
      resource: null,
      considerations: null,
      startDate: null,
      endDate: null,
    }
    const questions = makeQuestions()
    questions[0] = { ...questions[0], declarations: [noChoiceDeclaration] }
    getCommunityFipMock.mockResolvedValue(makeResponse({ questions }))

    const { wrapper } = await mountDetail()

    // Doesn't crash, and still renders all 21 questions.
    const cards = wrapper.findAll('.sections .question-card')
    expect(cards).toHaveLength(21)

    const noChoiceCard = cards[0]
    expect(noChoiceCard.text()).toContain(en.network.noChoiceDeclared)
    expect(noChoiceCard.find('.status-badge').exists()).toBe(true)
    const nanodashLinks = noChoiceCard.findAll('a.nanodash-link')
    expect(nanodashLinks.length).toBeGreaterThan(0)
    expect(nanodashLinks[0].attributes('href')).toContain(encodeURIComponent(noChoiceDeclaration.nanopubIri))
  })

  it('renders unmapped inside a collapsed <details>, separate from the 21', async () => {
    getCommunityFipMock.mockResolvedValue(
      makeResponse({
        unmapped: [
          {
            questionIri: 'https://w3id.org/fair/fip/terms/FIP-S-Question-F1-Persistency-Policy',
            declarations: [makeDeclaration()],
          },
        ],
      })
    )

    const { wrapper } = await mountDetail()

    // Still exactly 21 in the main list.
    expect(wrapper.findAll('.sections .question-card')).toHaveLength(21)

    const details = wrapper.find('details.unmapped-details')
    expect(details.exists()).toBe(true)
    expect(details.find('summary').text()).toContain(en.network.unmappedTitle.split('{')[0].trim())
    expect(details.text()).toContain('FIP-S-Question-F1-Persistency-Policy')
  })

  it('does not render the unmapped <details> when unmapped is empty', async () => {
    getCommunityFipMock.mockResolvedValue(makeResponse({ unmapped: [] }))

    const { wrapper } = await mountDetail()

    expect(wrapper.find('details.unmapped-details').exists()).toBe(false)
  })

  it('renders the network_disabled state with no retry', async () => {
    getCommunityFipMock.mockRejectedValue(new ApiResponseError(503, { detail: 'network_disabled' }))

    const { wrapper } = await mountDetail()

    expect(wrapper.text()).toContain(en.network.disabledMessage)
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('renders the network_unavailable state, Retry re-calling the api exactly once per click', async () => {
    getCommunityFipMock.mockRejectedValue(new ApiResponseError(502, { detail: 'network_unavailable' }))

    const { wrapper } = await mountDetail()

    expect(wrapper.text()).toContain(en.network.unavailableMessage)
    const retryBtn = wrapper.find('button')
    expect(retryBtn.exists()).toBe(true)

    getCommunityFipMock.mockResolvedValue(makeResponse())
    await retryBtn.trigger('click')
    await flushPromises()

    expect(getCommunityFipMock).toHaveBeenCalledTimes(2)
    expect(wrapper.findAll('.question-card')).toHaveLength(21)
  })

  it('renders the network_fip_not_found state, distinct from the other two', async () => {
    getCommunityFipMock.mockRejectedValue(new ApiResponseError(404, { detail: 'network_fip_not_found' }))

    const { wrapper } = await mountDetail()

    expect(wrapper.text()).toContain(en.network.notFoundMessage)
    expect(wrapper.text()).not.toContain(en.network.disabledMessage)
    expect(wrapper.text()).not.toContain(en.network.unavailableMessage)
  })

  it('"Use as starting point" calls createFipFromNetwork exactly once even on a double click, stores the edit token, and navigates to FipEditor', async () => {
    getCommunityFipMock.mockResolvedValue(makeResponse())
    let resolveCreate: (v: Awaited<ReturnType<typeof createFipFromNetwork>>) => void = () => {}
    createFipFromNetworkMock.mockReturnValue(
      new Promise((resolve) => {
        resolveCreate = resolve
      })
    )

    const { wrapper, router } = await mountDetail()

    const form = wrapper.find('form')
    // Two rapid submits before the (still-pending) request resolves.
    await form.trigger('submit.prevent')
    await form.trigger('submit.prevent')

    expect(createFipFromNetworkMock).toHaveBeenCalledTimes(1)
    expect(createFipFromNetworkMock).toHaveBeenCalledWith(
      expect.objectContaining({ communityIri: COMMUNITY_IRI })
    )

    resolveCreate({
      fip: { id: 'fip-new' },
      editToken: 'secret-token',
      imported: { declarations: 10, fersCreated: 2, fersMatched: 3 },
      skipped: [],
    })
    await flushPromises()

    expect(setTokenMock).toHaveBeenCalledWith('fip-new', 'secret-token')
    expect(router.currentRoute.value.name).toBe('FipEditor')
    expect(router.currentRoute.value.params.id).toBe('fip-new')
  })

  it('only calls nanodash links (target=_blank, rel=noopener noreferrer) — no other outside host', async () => {
    getCommunityFipMock.mockResolvedValue(makeResponse())

    const { wrapper } = await mountDetail()

    const nanodashLink = wrapper.find('.nanodash-link')
    expect(nanodashLink.attributes('href')).toContain('nanodash.knowledgepixels.com')
    expect(nanodashLink.attributes('target')).toBe('_blank')
    expect(nanodashLink.attributes('rel')).toBe('noopener noreferrer')
  })

  // Review finding: `community.label`, `fip.label`/`indexIri`/`nanopubIri`/
  // `created`, `otherVersions[].label`/`created`, `resource.label` and
  // `declaration.status` are all `string | null` on the wire (the network
  // proxy's best-effort lookups and optional SPARQL bindings) — every
  // render site must degrade gracefully, and a `null` status must never
  // reach `StatusBadge` (which has no `declarationStatus.undefined` entry).
  it('renders a payload where every documented-nullable field is null, with sensible fallbacks and no missing-translation leak', async () => {
    const questions = makeQuestions()
    // Q1: resource present but unlabelled -> falls back to the resource IRI's tail.
    questions[0] = {
      ...questions[0],
      declarations: [
        {
          nanopubIri: 'https://w3id.org/np/RA-decl-nulllabel',
          status: 'current',
          resource: {
            iri: 'http://purl.org/np/RAtIF#SomeResource',
            label: null,
            comment: null,
            homepage: null,
            types: [],
            ferTypeKey: null,
            inCatalogue: null,
          },
          considerations: null,
          startDate: null,
          endDate: null,
        },
      ],
    }
    // Q3: the degenerate case where neither `nochoice` nor any `declares-*`
    // predicate matched (`network.py`'s `_status_and_resource`) -- status
    // AND resource both null.
    const nullStatusDeclaration: NetworkDeclaration = {
      nanopubIri: 'https://w3id.org/np/RA-decl-nullstatus',
      status: null,
      resource: null,
      considerations: null,
      startDate: null,
      endDate: null,
    }
    questions[2] = { ...questions[2], declarations: [nullStatusDeclaration] }

    const response = makeResponse({
      community: { iri: COMMUNITY_IRI, label: null },
      fip: {
        nanopubIri: null,
        label: null,
        indexIri: null,
        created: null,
        startDate: null,
        endDate: null,
        otherVersions: [{ nanopubIri: 'https://w3id.org/np/RA-other#v1', label: null, created: null }],
      },
      questions,
      unmapped: [
        {
          questionIri: 'https://w3id.org/fair/fip/terms/FIP-S-Question-F1-Persistency-Policy',
          declarations: [
            { ...nullStatusDeclaration, nanopubIri: 'https://w3id.org/np/RA-decl-unmapped-nullstatus' },
          ],
        },
      ],
    })
    getCommunityFipMock.mockResolvedValue(response)

    const { wrapper } = await mountDetail()

    // Community label null, iri present -> the IRI's own tail.
    expect(wrapper.find('h1').text()).toBe('PARCToxicology')

    // FIP label null with nanopubIri also null -> the last-resort key.
    expect(wrapper.text()).toContain(en.network.unknownLabel)

    // No "Created" row rendered when fip.created is null.
    expect(wrapper.text()).not.toContain(en.common.created)

    // No main "View on Nanodash" link when fip.nanopubIri is null.
    expect(wrapper.find('.community-header .nanodash-link').exists()).toBe(false)

    // Other versions: a null label/created still renders (IRI-tail
    // fallback label, no parenthetical date), still linking out.
    const otherVersionItems = wrapper.findAll('.other-versions li')
    expect(otherVersionItems).toHaveLength(1)
    const otherVersionLink = otherVersionItems[0].find('a')
    expect(otherVersionLink.exists()).toBe(true)
    expect(otherVersionLink.text()).toBe('v1')

    const cards = wrapper.findAll('.sections .question-card')
    // Q1: unlabelled resource -> IRI-tail fallback, badge still shown (status is non-null).
    expect(cards[0].text()).toContain('SomeResource')
    expect(cards[0].find('.status-badge').exists()).toBe(true)

    // Q3: null status paired with null resource -> "No choice declared"
    // text, no StatusBadge, never the raw missing-key string.
    expect(cards[2].text()).toContain(en.network.noChoiceDeclared)
    expect(cards[2].find('.status-badge').exists()).toBe(false)
    expect(cards[2].text()).not.toContain('declarationStatus.undefined')

    // Same fix inside the collapsed `unmapped` section.
    const unmappedCard = wrapper.find('details.unmapped-details .question-card')
    expect(unmappedCard.text()).toContain(en.network.noChoiceDeclared)
    expect(unmappedCard.find('.status-badge').exists()).toBe(false)
    expect(unmappedCard.text()).not.toContain('declarationStatus.undefined')
  })

  it('renders the invalid_community_iri state with no retry, distinct from unavailable', async () => {
    getCommunityFipMock.mockRejectedValue(new ApiResponseError(400, { detail: 'invalid_community_iri' }))

    const { wrapper } = await mountDetail()

    expect(wrapper.text()).toContain(en.network.invalidIri)
    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.text()).not.toContain(en.network.unavailableMessage)
  })

  // Review finding: `CreateFipFromNetworkRequest` needs `joinCode` alongside
  // `sessionId` for a facilitator deep-linking here from a session
  // (`?session=<id>&code=<joinCode>`); both present together or neither.
  it('includes sessionId and joinCode in the create body when the route carries ?session=&code=', async () => {
    getCommunityFipMock.mockResolvedValue(makeResponse())
    createFipFromNetworkMock.mockResolvedValue({
      fip: { id: 'fip-session' },
      imported: { declarations: 0, fersCreated: 0, fersMatched: 0 },
      skipped: [],
    })

    const { wrapper } = await mountDetail({ session: 'sess-1', code: 'ABC123' })
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(createFipFromNetworkMock).toHaveBeenCalledWith(
      expect.objectContaining({ sessionId: 'sess-1', joinCode: 'ABC123' })
    )
  })

  it('omits sessionId and joinCode from the create body with no ?session=/?code= on the route', async () => {
    getCommunityFipMock.mockResolvedValue(makeResponse())
    createFipFromNetworkMock.mockResolvedValue({
      fip: { id: 'fip-no-session' },
      imported: { declarations: 0, fersCreated: 0, fersMatched: 0 },
      skipped: [],
    })

    const { wrapper } = await mountDetail()
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const [callArgs] = createFipFromNetworkMock.mock.calls[0]
    expect(callArgs).not.toHaveProperty('sessionId')
    expect(callArgs).not.toHaveProperty('joinCode')
  })

  it('omits sessionId and joinCode when only one of ?session=/?code= is present (a malformed link)', async () => {
    getCommunityFipMock.mockResolvedValue(makeResponse())
    createFipFromNetworkMock.mockResolvedValue({
      fip: { id: 'fip-partial' },
      imported: { declarations: 0, fersCreated: 0, fersMatched: 0 },
      skipped: [],
    })

    const { wrapper } = await mountDetail({ session: 'sess-1' })
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const [callArgs] = createFipFromNetworkMock.mock.calls[0]
    expect(callArgs).not.toHaveProperty('sessionId')
    expect(callArgs).not.toHaveProperty('joinCode')
  })
})
