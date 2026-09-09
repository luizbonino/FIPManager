import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/en.json'
import ShareBox from './ShareBox.vue'

// Spec 09 follow-up: FipEditor.vue passes this device's edit token (when
// it has one) as the `edit-token` prop, and ShareBox shows an extra
// "Edit link" row + warning only then — a read-only viewer with no token
// (or a private FIP, gated by the caller's `v-if`) never sees it.
function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function mountShareBox(props: { url: string; fipId: string; editToken?: string }) {
  return mount(ShareBox, { props, global: { plugins: [makeI18n()] } })
}

describe('ShareBox.vue — edit link row', () => {
  it('does not render the edit link row when no editToken prop is passed', () => {
    const wrapper = mountShareBox({ url: 'https://example.test/fips/fip-1', fipId: 'fip-1' })

    expect(wrapper.text()).not.toContain(en.share.editLink)
    expect(wrapper.find('.share-edit-link').exists()).toBe(false)
  })

  it('renders the edit link row, URL, and warning when editToken is set', () => {
    const wrapper = mountShareBox({
      url: 'https://example.test/fips/fip-1',
      fipId: 'fip-1',
      editToken: 'secret-token',
    })

    const row = wrapper.find('.share-edit-link')
    expect(row.exists()).toBe(true)
    expect(row.text()).toContain(en.share.editLink)
    expect(row.text()).toContain(en.share.editLinkWarning)

    const input = wrapper.find<HTMLInputElement>('.edit-link-input')
    expect(input.exists()).toBe(true)
    expect(input.element.value).toBe(
      `${window.location.origin}/fips/fip-1/edit?token=secret-token`
    )
  })

  it('URL-encodes a token that needs it', () => {
    const wrapper = mountShareBox({
      url: 'https://example.test/fips/fip-1',
      fipId: 'fip-1',
      editToken: 'a b+c',
    })

    const input = wrapper.find<HTMLInputElement>('.edit-link-input')
    expect(input.element.value).toBe(
      `${window.location.origin}/fips/fip-1/edit?token=${encodeURIComponent('a b+c')}`
    )
  })
})
