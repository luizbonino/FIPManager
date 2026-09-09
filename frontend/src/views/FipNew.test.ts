import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
import type { KnowledgeModelSummary } from '@/types/api'

// Spec 09: standalone FIPs — FipNew.vue works signed out, stores the
// returned edit token, and supports `?km=<id>@<version>` preselection.
vi.mock('@/api/knowledgeModels', () => ({
  listKnowledgeModels: vi.fn(),
}))
vi.mock('@/api/fips', () => ({
  createFip: vi.fn(),
}))
vi.mock('@/lib/editTokens', () => ({
  setToken: vi.fn(),
}))

import { listKnowledgeModels } from '@/api/knowledgeModels'
import { createFip } from '@/api/fips'
import { setToken } from '@/lib/editTokens'
import FipNew from './FipNew.vue'

const listKnowledgeModelsMock = vi.mocked(listKnowledgeModels)
const createFipMock = vi.mocked(createFip)
const setTokenMock = vi.mocked(setToken)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function makeKm(overrides: Partial<KnowledgeModelSummary> = {}): KnowledgeModelSummary {
  return {
    id: 'km-1',
    version: '1.0.0',
    title: { en: 'Model One' },
    description: { en: '' },
    isSystem: true,
    ownerId: null,
    status: 'published',
    questionCount: 3,
    forkedFrom: null,
    ...overrides,
  } as KnowledgeModelSummary
}

async function mountFipNew(query: Record<string, string> = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)

  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/fips/new', name: 'FipNew', component: FipNew },
      { path: '/fips/:id/edit', name: 'FipEditor', component: { template: '<div/>' } },
    ],
  })
  await router.push({ path: '/fips/new', query })
  await router.isReady()

  const wrapper = mount(FipNew, { global: { plugins: [pinia, makeI18n(), router] } })
  await flushPromises()
  return { wrapper, router }
}

describe('FipNew.vue (spec 09: standalone FIPs)', () => {
  beforeEach(() => {
    listKnowledgeModelsMock.mockReset()
    createFipMock.mockReset()
    setTokenMock.mockReset()
    listKnowledgeModelsMock.mockResolvedValue({ items: [makeKm()], total: 1 })
  })

  it('shows the anonymous hint and the community form works for a signed-out visitor', async () => {
    const { wrapper } = await mountFipNew()

    // Choose the only listed model to reach the community form.
    await wrapper.get('input[type="radio"]').setValue()
    await flushPromises()

    expect(wrapper.text()).toContain(en.fipNew.anonymousHint)
  })

  it('creates a FIP without a sessionId, stores the returned edit token, and navigates to the editor', async () => {
    createFipMock.mockResolvedValue({ id: 'fip-1', editToken: 'tok-123' } as never)
    const { wrapper, router } = await mountFipNew()

    await wrapper.get('input[type="radio"]').setValue()
    await flushPromises()
    await wrapper.get('input[type="text"]').setValue('My community')
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(createFipMock).toHaveBeenCalledWith(
      expect.objectContaining({ questionnaireRef: { id: 'km-1', version: '1.0.0' } })
    )
    const [callArgs] = createFipMock.mock.calls[0]
    expect(callArgs).not.toHaveProperty('sessionId')

    expect(setTokenMock).toHaveBeenCalledWith('fip-1', 'tok-123')
    expect(router.currentRoute.value.name).toBe('FipEditor')
    expect(router.currentRoute.value.params.id).toBe('fip-1')
  })

  it('does not store a token when the caller is signed in (no editToken on the response)', async () => {
    createFipMock.mockResolvedValue({ id: 'fip-2' } as never)
    const { wrapper } = await mountFipNew()

    await wrapper.get('input[type="radio"]').setValue()
    await flushPromises()
    await wrapper.get('input[type="text"]').setValue('My community')
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(setTokenMock).not.toHaveBeenCalled()
  })

  it('`?km=` preselects a matching listed published model, skipping the choice step', async () => {
    const { wrapper } = await mountFipNew({ km: 'km-1@1.0.0' })

    // Straight to the community form, no radio group.
    expect(wrapper.find('input[type="radio"]').exists()).toBe(false)
    expect(wrapper.find('input[type="text"]').exists()).toBe(true)
  })

  it('an unmatched `?km=` value falls back to the ordinary choice step', async () => {
    const { wrapper } = await mountFipNew({ km: 'nope@9.9.9' })

    expect(wrapper.find('input[type="radio"]').exists()).toBe(true)
  })
})
