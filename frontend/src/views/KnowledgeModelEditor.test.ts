import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
// The real content of `data/knowledge-models/gofair-fip-mini-1.0.0.json`
// (as `lib/matrix.test.ts` and `lib/kmContent.test.ts` already do), so this
// rendering test cannot drift from the questionnaire the app actually
// serves. Criterion 14.
import kmFixtureJson from '../../../data/knowledge-models/gofair-fip-mini-1.0.0.json'
import type { KnowledgeModelContent, KnowledgeModelOut } from '@/types/api'

// The store's data source is stubbed at the API boundary (matching
// `stores/fipEditor.test.ts`'s established pattern) — every function the
// `kmEditor` store or `KnowledgeModelEditor.vue` imports from
// `@/api/knowledgeModels`/`@/api/ferTypes` must be present, even if a
// given test never calls it.
vi.mock('@/api/knowledgeModels', () => ({
  getKnowledgeModel: vi.fn(),
  createKnowledgeModel: vi.fn(),
  forkKnowledgeModel: vi.fn(),
  importKnowledgeModel: vi.fn(),
  kmExportJsonUrl: (id: string, version: string) => `/api/knowledge-models/${id}/${version}/export.json`,
  patchKnowledgeModel: vi.fn(),
  putKnowledgeModelContent: vi.fn(),
  publishKnowledgeModel: vi.fn(),
  newKnowledgeModelVersion: vi.fn(),
  deleteKnowledgeModel: vi.fn(),
  listKnowledgeModels: vi.fn(),
}))

vi.mock('@/api/ferTypes', () => ({
  getFerTypes: vi.fn(),
}))

import { getKnowledgeModel } from '@/api/knowledgeModels'
import { getFerTypes } from '@/api/ferTypes'
import { useKmEditorStore } from '@/stores/kmEditor'
import KnowledgeModelEditor from './KnowledgeModelEditor.vue'

const getKnowledgeModelMock = vi.mocked(getKnowledgeModel)
const getFerTypesMock = vi.mocked(getFerTypes)

function fixtureContent(): KnowledgeModelContent {
  const content = JSON.parse(JSON.stringify(kmFixtureJson)) as KnowledgeModelContent
  // The on-disk fixture is the *published* GO FAIR system model; the
  // editor route is for a draft (spec §1/§5), so force draft status here —
  // otherwise every control renders read-only/disabled.
  content.status = 'draft'
  return content
}

function makeModel(content: KnowledgeModelContent): KnowledgeModelOut {
  return {
    id: content.id,
    version: content.version,
    status: content.status,
    visibility: 'private',
    license: content.license,
    // The top-level `source` (unlike `content.source`) is always a plain
    // string server-side; not asserted on by this suite.
    source: 'GO FAIR FIP mini-questionnaire',
    title: content.title,
    description: content.description,
    changelog: content.changelog,
    content,
    createdAt: '2026-09-01T00:00:00Z',
    updatedAt: '2026-09-01T00:00:00Z',
    etag: '"etag-1"',
  }
}

function makeI18n(locale: string) {
  // `messages` registers only `en` — a non-`en` `locale` (e.g. 'pt-PT')
  // therefore resolves every string through `fallbackLocale`, which is
  // exactly what lets this suite assert English copy (`en.json` is the
  // only file this task may touch) while still exercising the store's
  // per-language `completeness('pt-PT')` and `$t('languages.pt-PT')`
  // ("Portuguese (Portugal)"). `missingWarn`/`fallbackWarn` silence the
  // resulting (expected, harmless) per-key fallback console noise.
  return createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'en',
    messages: { en },
    missingWarn: false,
    fallbackWarn: false,
  })
}

async function flushPromises() {
  for (let i = 0; i < 4; i += 1) await Promise.resolve()
}

async function mountEditor(content: KnowledgeModelContent, locale = 'pt-PT') {
  const pinia = createPinia()
  setActivePinia(pinia)

  getKnowledgeModelMock.mockResolvedValue(makeModel(content))
  getFerTypesMock.mockResolvedValue({ items: [], total: 0 })

  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Home', component: { template: '<div/>' } },
      { path: '/knowledge-models', name: 'KnowledgeModelList', component: { template: '<div/>' } },
      {
        path: '/knowledge-models/:id/:version/edit',
        name: 'KnowledgeModelEditor',
        component: KnowledgeModelEditor,
        props: true,
      },
    ],
  })
  await router.push(`/knowledge-models/${content.id}/${content.version}/edit`)
  await router.isReady()

  const wrapper = mount(KnowledgeModelEditor, {
    global: { plugins: [pinia, makeI18n(locale), router] },
  })
  await flushPromises()
  return { wrapper, pinia }
}

beforeEach(() => {
  getKnowledgeModelMock.mockReset()
  getFerTypesMock.mockReset()
})

describe('KnowledgeModelEditor.vue', () => {
  it('renders one accordion head per section, up/down disabled at the ends', async () => {
    const { wrapper } = await mountEditor(fixtureContent())
    const sections = wrapper.findAll('.section')
    expect(sections).toHaveLength(4)

    const firstMoveButtons = sections[0].findAll('.summary-actions .move-btn')
    expect(firstMoveButtons).toHaveLength(2)
    expect(firstMoveButtons[0].attributes('disabled')).toBeDefined() // up, at the first section
    expect(firstMoveButtons[1].attributes('disabled')).toBeUndefined()

    const lastMoveButtons = sections[sections.length - 1].findAll('.summary-actions .move-btn')
    expect(lastMoveButtons[0].attributes('disabled')).toBeUndefined()
    expect(lastMoveButtons[1].attributes('disabled')).toBeDefined() // down, at the last section
  })

  it('renders question cards with three language tabs (en / pt-PT / pt-BR)', async () => {
    const { wrapper } = await mountEditor(fixtureContent())
    const cards = wrapper.findAll('.km-question-card')
    expect(cards.length).toBeGreaterThan(0)
    // Each card has two `KmLangTabs` instances (text, help); scope to the
    // first field group (the question text) for "three tabs".
    const tabs = cards[0].get('.field-group').findAll('.tabs .tab')
    expect(tabs).toHaveLength(3)
    expect(tabs.map((t) => t.text().replace(/\s+/g, ' ').trim())).toEqual(
      expect.arrayContaining([expect.stringContaining('English')])
    )
  })

  it('a question missing pt-PT text renders its en fallback with the missing class and km.missingTranslation, and the meter reads 19 of 21', async () => {
    const content = fixtureContent()
    const q0 = content.sections[0].questions[0]
    const q1 = content.sections[0].questions[1]
    // Drop pt-PT (and pt-BR, so resolveLang's pt-PT<->pt-BR sibling
    // fallback can't paper over it) from exactly two of the 21 questions.
    q0.text = { en: q0.text.en }
    q1.text = { en: q1.text.en }

    const { wrapper } = await mountEditor(content, 'pt-PT')

    const meterText = wrapper.get('.meter-text').text()
    expect(meterText).toBe('19 of 21 texts in Portuguese (Portugal)')

    const missing = wrapper.find('.km-question-card .missing')
    expect(missing.exists()).toBe(true)
    expect(missing.text()).toContain(q0.text.en)
    expect(missing.text()).toContain('Missing — showing Portuguese (Portugal)')
  })

  it('KmPublishDialog: Publish is disabled until notes is non-empty', async () => {
    const { wrapper } = await mountEditor(fixtureContent())
    await wrapper.get('.publish-trigger-btn').trigger('click')
    await flushPromises()

    const dialog = wrapper.get('.km-publish-dialog')
    const publishBtn = dialog.get('.btn-primary')
    expect((publishBtn.element as HTMLButtonElement).disabled).toBe(true)

    await dialog.get('textarea').setValue('Translated question F1, hid one question')
    expect((publishBtn.element as HTMLButtonElement).disabled).toBe(false)
  })

  it('a 409 conflict state renders km.conflict with a Reload button', async () => {
    const { wrapper, pinia } = await mountEditor(fixtureContent())
    setActivePinia(pinia)
    const store = useKmEditorStore()
    store.conflict = true
    await flushPromises()

    expect(wrapper.text()).toContain('This draft changed elsewhere. Reload to see the newer version.')
    expect(wrapper.find('.reload-btn').exists()).toBe(true)
  })
})
