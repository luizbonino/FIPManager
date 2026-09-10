import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/en.json'
import ExportButtons from './ExportButtons.vue'

// spec 11 §3.5/§8.2: a fifth, optional export entry — Nanopublications
// (.zip) — alongside the four pre-existing JSON/CSV/TTL/JSON-LD links.
function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

const BASE_PROPS = {
  jsonUrl: '/api/fips/fip-1/export.json',
  csvUrl: '/api/fips/fip-1/export.csv',
  ttlUrl: '/api/fips/fip-1/export.ttl',
  jsonldUrl: '/api/fips/fip-1/export.jsonld',
}

describe('ExportButtons.vue', () => {
  it('renders the four pre-existing export links unchanged', () => {
    const wrapper = mount(ExportButtons, { props: BASE_PROPS, global: { plugins: [makeI18n()] } })

    expect(wrapper.find(`a[href="${BASE_PROPS.jsonUrl}"]`).exists()).toBe(true)
    expect(wrapper.find(`a[href="${BASE_PROPS.csvUrl}"]`).exists()).toBe(true)
    expect(wrapper.find(`a[href="${BASE_PROPS.ttlUrl}"]`).exists()).toBe(true)
    expect(wrapper.find(`a[href="${BASE_PROPS.jsonldUrl}"]`).exists()).toBe(true)
  })

  it('does not render a nanopublications link when nanopubZipUrl is absent', () => {
    const wrapper = mount(ExportButtons, { props: BASE_PROPS, global: { plugins: [makeI18n()] } })

    expect(wrapper.text()).not.toContain(en.nanopubExport.exportLinkLabel)
  })

  it('renders a nanopublications (.zip) link when nanopubZipUrl is passed', () => {
    const zipUrl = '/api/fips/fip-1/export/nanopubs.zip'
    const wrapper = mount(ExportButtons, {
      props: { ...BASE_PROPS, nanopubZipUrl: zipUrl },
      global: { plugins: [makeI18n()] },
    })

    const link = wrapper.find(`a[href="${zipUrl}"]`)
    expect(link.exists()).toBe(true)
    expect(link.text()).toBe(en.nanopubExport.exportLinkLabel)
  })
})
