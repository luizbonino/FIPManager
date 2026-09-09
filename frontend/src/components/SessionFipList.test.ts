import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/en.json'
import type { FipOut, KnowledgeModelOut } from '@/types/api'

vi.mock('@/api/knowledgeModels', () => ({
  getKnowledgeModel: vi.fn(),
}))

import { getKnowledgeModel } from '@/api/knowledgeModels'
import SessionFipList from './SessionFipList.vue'

const getKnowledgeModelMock = vi.mocked(getKnowledgeModel)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function makeFip(overrides: Partial<FipOut> = {}): FipOut {
  return {
    id: 'fip-1',
    ownerId: null,
    sessionId: 'session-1',
    visibility: 'link',
    questionnaireId: 'gofair-fip-mini',
    questionnaireVersion: '1.0.0',
    title: null,
    community: { name: 'Alpha', links: [] },
    relatedDmps: [],
    answers: [{ questionId: 'F1-metadata', declarations: [{ status: 'current', ferId: 'x' }] }],
    language: 'en',
    license: 'CC0-1.0',
    createdAt: '2026-09-01T00:00:00Z',
    updatedAt: '2026-09-01T00:00:00Z',
    ...overrides,
  }
}

function makeKm(questionCount: number): KnowledgeModelOut {
  return {
    id: 'gofair-fip-mini',
    version: '1.0.0',
    status: 'published',
    visibility: 'public',
    license: 'CC0-1.0',
    source: 'test',
    title: { en: 'Model' },
    description: { en: '' },
    changelog: [],
    content: {
      id: 'gofair-fip-mini',
      version: '1.0.0',
      status: 'published',
      license: 'CC0-1.0',
      title: { en: 'Model' },
      description: { en: '' },
      changelog: [],
      sections: [
        {
          id: 'F',
          title: { en: 'Findable' },
          questions: Array.from({ length: questionCount }, (_, i) => ({
            id: `q${i}`,
            principle: null,
            scope: null,
            text: { en: `Q${i}` },
            help: null,
            ferType: null,
            required: false,
            allowMultiple: true,
          })),
        },
      ],
    },
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
  }
}

describe('SessionFipList.vue', () => {
  beforeEach(() => {
    getKnowledgeModelMock.mockReset()
  })

  it('renders an area chip when a FIP carries areaLabel, none when it does not', async () => {
    getKnowledgeModelMock.mockResolvedValue(makeKm(21))
    const fips = [makeFip({ id: 'fip-1', areaLabel: { en: 'Public health' } }), makeFip({ id: 'fip-2', createdAt: '2026-09-02T00:00:00Z' })]
    const wrapper = mount(SessionFipList, { props: { fips }, global: { plugins: [makeI18n()] } })
    await flushPromises()

    const rows = wrapper.findAll('.fip-row')
    expect(rows[0].find('.area-chip').exists()).toBe(true)
    expect(rows[0].get('.area-chip').text()).toBe('Public health')
    expect(rows[1].find('.area-chip').exists()).toBe(false)
  })

  // Spec 08 §3.2: the denominator is per-FIP — that FIP's own model's
  // visible question count, not a hardcoded 21.
  it('uses the FIP\'s own model visible question count as the progress denominator, fetched once per distinct ref', async () => {
    getKnowledgeModelMock.mockResolvedValue(makeKm(5))
    const fips = [
      makeFip({ id: 'fip-1' }),
      makeFip({ id: 'fip-2', createdAt: '2026-09-02T00:00:00Z' }), // same ref
    ]
    const wrapper = mount(SessionFipList, { props: { fips }, global: { plugins: [makeI18n()] } })
    await flushPromises()

    expect(getKnowledgeModelMock).toHaveBeenCalledTimes(1) // cached across the two same-ref FIPs
    expect(wrapper.text()).toContain(en.editor.progress.replace('{answered}', '1').replace('{total}', '5'))
  })

  it('falls back to TOTAL_QUESTIONS (21) when the model fetch fails', async () => {
    getKnowledgeModelMock.mockRejectedValue(new Error('network'))
    const fips = [makeFip({ id: 'fip-1' })]
    const wrapper = mount(SessionFipList, { props: { fips }, global: { plugins: [makeI18n()] } })
    await flushPromises()

    expect(wrapper.text()).toContain(en.editor.progress.replace('{answered}', '1').replace('{total}', '21'))
  })
})
