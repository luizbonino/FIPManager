import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/en.json'
import type { NanopubBundleIndex } from '@/types/network'

// spec 11 §2.6/§2.7/§3.5: the "Prepare nanopublications" dialog. Mocked
// exactly to the index.json shape of spec 11 §2.6 and the preview.trig
// plain-text response of §2.7.
vi.mock('@/api/network', () => ({
  getNanopubIndex: vi.fn(),
  getNanopubPreview: vi.fn(),
  nanopubZipUrl: (fipId: string) => `/api/fips/${fipId}/export/nanopubs.zip`,
}))

import { getNanopubIndex, getNanopubPreview } from '@/api/network'
import NanopubExportDialog from './NanopubExportDialog.vue'

const getNanopubIndexMock = vi.mocked(getNanopubIndex)
const getNanopubPreviewMock = vi.mocked(getNanopubPreview)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function makeIndex(overrides: Partial<NanopubBundleIndex> = {}): NanopubBundleIndex {
  return {
    schema: 'fipm-nanopub-bundle/1',
    generator: { tool: 'FIP Manager', agent: 'https://fipm.example.org', generatedAt: '2026-09-10T12:00:00Z' },
    fip: {
      id: 'K7QX2',
      url: 'https://fipm.example.org/fips/K7QX2',
      title: 'FIP of the CONFOA 2026 group A',
      language: 'en',
      license: 'CC0-1.0',
      questionnaire: { id: 'gofair-fip-mini', version: '1.0.0' },
    },
    tempBase: 'http://purl.org/nanopub/temp/fipm/K7QX2/',
    signed: false,
    nanopubs: [],
    signingOrder: [1, 2],
    rewrites: [],
    counts: { nanopubs: 24, declarations: 21, skipped: 2 },
    skipped: [{ questionId: 'confoa-omics-1', declarationIndex: 0, reason: 'no_question_individual' }],
    notRepresented: {
      notApplicable: ['A2'],
      answerComments: ['F2'],
      dmpEvidence: [{ questionId: 'F4-metadata', declarationIndex: 0 }],
      relatedDmps: 2,
    },
    publishPrerequisites: {
      satisfied: [],
      missing: [{ what: 'orcid', detail: 'No ORCID iD is recorded for this FIP author.' }],
    },
    ...overrides,
  }
}

async function mountDialog(open: boolean) {
  const wrapper = mount(NanopubExportDialog, {
    props: { open, fipId: 'K7QX2' },
    global: { plugins: [makeI18n()] },
  })
  await flushPromises()
  return wrapper
}

describe('NanopubExportDialog.vue', () => {
  beforeEach(() => {
    getNanopubIndexMock.mockReset()
    getNanopubPreviewMock.mockReset()
  })

  it('renders nothing when closed', async () => {
    const wrapper = await mountDialog(false)

    expect(wrapper.find('.nanopub-export-dialog').exists()).toBe(false)
    expect(getNanopubIndexMock).not.toHaveBeenCalled()
  })

  it("fetches index.json and preview.trig on open, the unsigned/unpublished notice is the dialog's first visible line", async () => {
    getNanopubIndexMock.mockResolvedValue(makeIndex())
    getNanopubPreviewMock.mockResolvedValue('@prefix fip: <https://w3id.org/fair/fip/terms/> .')

    const wrapper = mount(NanopubExportDialog, {
      props: { open: false, fipId: 'K7QX2' },
      global: { plugins: [makeI18n()] },
    })
    await wrapper.setProps({ open: true })
    await flushPromises()

    expect(getNanopubIndexMock).toHaveBeenCalledWith('K7QX2')
    expect(getNanopubPreviewMock).toHaveBeenCalledWith('K7QX2')

    const dialog = wrapper.find('.nanopub-export-dialog')
    expect(dialog.exists()).toBe(true)
    const firstParagraph = dialog.find('p')
    expect(firstParagraph.text()).toBe(en.nanopubExport.unsignedNotice)
  })

  it('renders counts, skipped, notRepresented and publishPrerequisites.missing from index.json', async () => {
    getNanopubIndexMock.mockResolvedValue(makeIndex())
    getNanopubPreviewMock.mockResolvedValue('@prefix fip: <https://w3id.org/fair/fip/terms/> .')

    const wrapper = await mountDialog(true)

    const text = wrapper.text()
    expect(text).toContain('24')
    expect(text).toContain('21')
    expect(text).toContain('confoa-omics-1')
    expect(text).toContain('no_question_individual')
    expect(text).toContain('A2')
    expect(text).toContain('F2')
    expect(text).toContain('orcid')
    expect(text).toContain('No ORCID iD is recorded for this FIP author.')
  })

  it('shows the preview.trig text', async () => {
    getNanopubIndexMock.mockResolvedValue(makeIndex())
    getNanopubPreviewMock.mockResolvedValue('@prefix fip: <https://w3id.org/fair/fip/terms/> .')

    const wrapper = await mountDialog(true)

    expect(wrapper.find('.preview-trig').text()).toBe('@prefix fip: <https://w3id.org/fair/fip/terms/> .')
  })

  it('the download is a plain <a href> to nanopubZipUrl(fipId), not a click handler', async () => {
    getNanopubIndexMock.mockResolvedValue(makeIndex())
    getNanopubPreviewMock.mockResolvedValue('trig')

    const wrapper = await mountDialog(true)

    const link = wrapper.find('a.btn-primary')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('/api/fips/K7QX2/export/nanopubs.zip')
    expect(link.text()).toBe(en.nanopubExport.downloadButton)
  })

  it('shows a load error and no download link when the fetch fails', async () => {
    getNanopubIndexMock.mockRejectedValue(new Error('boom'))
    getNanopubPreviewMock.mockResolvedValue('trig')

    const wrapper = await mountDialog(true)

    expect(wrapper.text()).toContain(en.nanopubExport.loadError)
    expect(wrapper.find('a.btn-primary').exists()).toBe(false)
  })

  it('emits close when the Close button is clicked', async () => {
    getNanopubIndexMock.mockResolvedValue(makeIndex())
    getNanopubPreviewMock.mockResolvedValue('trig')

    const wrapper = await mountDialog(true)
    await wrapper.find('button.btn-secondary').trigger('click')

    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})
