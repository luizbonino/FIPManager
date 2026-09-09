import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
import type { FipExportDoc } from '@/types/api'

vi.mock('@/api/fips', () => ({
  getFipExport: vi.fn(),
  getFip: vi.fn(),
  getMigrationTargets: vi.fn(),
  fipExportJsonUrl: vi.fn(() => 'json-url'),
  fipExportCsvUrl: vi.fn(() => 'csv-url'),
  fipExportTtlUrl: vi.fn(() => 'ttl-url'),
  fipExportJsonldUrl: vi.fn(() => 'jsonld-url'),
}))
vi.mock('@/api/knowledgeModels', () => ({
  getKnowledgeModel: vi.fn().mockResolvedValue({ license: 'CC0-1.0' }),
}))
vi.mock('@/lib/editTokens', () => ({
  getToken: vi.fn().mockReturnValue(null),
}))

import { getFipExport, getMigrationTargets } from '@/api/fips'
import FipRead from './FipRead.vue'

const getFipExportMock = vi.mocked(getFipExport)
const getMigrationTargetsMock = vi.mocked(getMigrationTargets)

function makeDoc(overrides: Partial<FipExportDoc> = {}): FipExportDoc {
  return {
    exportVersion: 2,
    generatedAt: '2026-01-01T00:00:00Z',
    tool: { name: 'FIP Manager', baseUrl: 'https://example.org' },
    fip: {
      id: 'fip1',
      url: 'https://example.org/fips/fip1',
      language: 'en',
      license: 'CC0-1.0',
      visibility: 'public',
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
      community: { name: 'Test community', links: [] },
      relatedDMPs: [],
    },
    questionnaireRef: { id: 'gofair-fip-mini', version: '1.0.0', title: 'Mini FIP', source: 'https://example.org' },
    answers: [],
    ...overrides,
  }
}

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

async function mountFipRead(doc: FipExportDoc) {
  getFipExportMock.mockReset().mockResolvedValue(doc)
  getMigrationTargetsMock.mockReset().mockResolvedValue({ current: { id: 'x', version: '1' }, items: [], total: 0 })

  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/fips/:id', name: 'FipRead', component: FipRead }],
  })
  await router.push('/fips/fip1')
  await router.isReady()

  const wrapper = mount(FipRead, { global: { plugins: [makeI18n(), router] } })
  await flushPromises()
  return wrapper
}

// Finding: `dmpEvidence.dmpUrl` is `null` once its plan was removed (or,
// legacy evidence, when its stored URL fails the safe-https check) — the
// view must never render an anchor with a null/unsafe href.
describe('FipRead.vue — DMP evidence rendering', () => {
  it('renders a safe https dmpUrl as a clickable link', async () => {
    const doc = makeDoc({
      answers: [
        {
          sectionId: 'F',
          sectionTitle: 'Findable',
          questionId: 'F1-metadata',
          questionText: 'Q',
          principle: null,
          scope: null,
          ferType: null,
          comment: null,
          declarations: [
            {
              fer: null,
              ferFreeText: 'Dataset',
              status: 'current',
              note: null,
              successor: null,
              successorFreeText: null,
              dmpEvidence: {
                dmpIndex: 0,
                dmpUrl: 'https://fiodmp.fiocruz.br/KQU5N0C',
                dmpSystem: 'FioDMP',
                dmpVersion: '1',
                section: null,
                questionRef: null,
              },
            },
          ],
        },
      ],
    })
    const wrapper = await mountFipRead(doc)

    const link = wrapper.get('.declaration-evidence a')
    expect(link.attributes('href')).toBe('https://fiodmp.fiocruz.br/KQU5N0C')
    expect(link.text()).toBe('KQU5N0C')
  })

  it('renders no anchor, and no empty href, when dmpUrl is null (plan removed)', async () => {
    const doc = makeDoc({
      answers: [
        {
          sectionId: 'F',
          sectionTitle: 'Findable',
          questionId: 'F1-metadata',
          questionText: 'Q',
          principle: null,
          scope: null,
          ferType: null,
          comment: null,
          declarations: [
            {
              fer: null,
              ferFreeText: 'Dataset',
              status: 'current',
              note: null,
              successor: null,
              successorFreeText: null,
              dmpEvidence: {
                dmpIndex: null,
                dmpUrl: null,
                dmpSystem: null,
                dmpVersion: null,
                section: 'Storage',
                questionRef: null,
              },
            },
          ],
        },
      ],
    })
    const wrapper = await mountFipRead(doc)

    expect(wrapper.find('.declaration-evidence a').exists()).toBe(false)
    // The section is still shown even with no plan URL to link to.
    expect(wrapper.get('.declaration-evidence').text()).toContain('Storage')
  })

  it('falls back to rawUrl as plain text (never a href) for an unsafe legacy URL', async () => {
    const doc = makeDoc({
      answers: [
        {
          sectionId: 'F',
          sectionTitle: 'Findable',
          questionId: 'F1-metadata',
          questionText: 'Q',
          principle: null,
          scope: null,
          ferType: null,
          comment: null,
          declarations: [
            {
              fer: null,
              ferFreeText: 'Dataset',
              status: 'current',
              note: null,
              successor: null,
              successorFreeText: null,
              dmpEvidence: {
                dmpIndex: null,
                dmpUrl: null,
                dmpSystem: null,
                dmpVersion: null,
                section: null,
                questionRef: null,
                rawUrl: 'javascript:alert(1)',
              },
            },
          ],
        },
      ],
    })
    const wrapper = await mountFipRead(doc)

    expect(wrapper.find('.declaration-evidence a').exists()).toBe(false)
    expect(wrapper.get('.declaration-evidence').text()).toContain('javascript:alert(1)')
  })
})
