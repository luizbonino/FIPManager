import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
import { computeMigrationDiff } from '@/lib/migration'
import { answers, newContent, oldContent } from '@/lib/__fixtures__/migrationDiff'
import type { FipOut } from '@/types/api'

vi.mock('@/api/fips', () => ({
  getFip: vi.fn(),
  getMigrationTargets: vi.fn(),
  getMigrationPreview: vi.fn(),
  migrateFip: vi.fn(),
}))
vi.mock('@/lib/editTokens', () => ({
  getToken: vi.fn().mockReturnValue(null),
}))

import { getFip, getMigrationPreview, getMigrationTargets, migrateFip } from '@/api/fips'
import FipMigrate from './FipMigrate.vue'

const getFipMock = vi.mocked(getFip)
const getMigrationTargetsMock = vi.mocked(getMigrationTargets)
const getMigrationPreviewMock = vi.mocked(getMigrationPreview)
const migrateFipMock = vi.mocked(migrateFip)

const diff = computeMigrationDiff({ content: oldContent }, { content: newContent }, answers)

function makeFip(): FipOut {
  return {
    id: 'fip1',
    ownerId: 'u1',
    sessionId: null,
    visibility: 'private',
    questionnaireId: 'gofair-fip-mini',
    questionnaireVersion: '1.0.0',
    title: null,
    community: null,
    relatedDmps: [],
    answers,
    language: 'en',
    license: 'CC0-1.0',
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
  }
}

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

async function mountFipMigrate() {
  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/fips/:id/migrate', name: 'FipMigrate', component: FipMigrate, props: true },
      { path: '/fips/:id/edit', name: 'FipEditor', component: { template: '<div/>' } },
      { path: '/fips/:id', name: 'FipRead', component: { template: '<div/>' } },
      { path: '/', name: 'Home', component: { template: '<div/>' } },
    ],
  })
  await router.push('/fips/fip1/migrate')
  await router.isReady()

  const wrapper = mount(FipMigrate, { global: { plugins: [makeI18n(), router] } })
  await flushPromises()
  return { wrapper, router }
}

// Criterion 20 (vitest half): FipMigrate.vue with a stubbed preview renders
// one row per item, unchanged rows behind the toggle, split radios
// defaulting to both, and a confirm dialog naming the target version.
describe('FipMigrate.vue', () => {
  beforeEach(() => {
    getFipMock.mockReset().mockResolvedValue(makeFip())
    getMigrationTargetsMock.mockReset().mockResolvedValue({
      current: { id: 'gofair-fip-mini', version: '1.0.0' },
      items: [{ id: 'gofair-fip-mini', version: '1.1.0', title: { en: 'v1.1' }, changelog: [], publishedAt: '2026-11-02T00:00:00Z' }],
      total: 1,
    })
    getMigrationPreviewMock.mockReset().mockResolvedValue(diff)
    migrateFipMock.mockReset()
  })

  it('renders one row for every flagged/added/removed/split item, then reveals the rest behind "show unchanged"', async () => {
    const { wrapper } = await mountFipMigrate()

    // 5 items total: F1 (unchanged+flag), F2 (split), F3 (hidden, no flags), A2 (removed), R1.3-data (added).
    // F3 alone is a "plain" unchanged/hidden row, hidden behind the toggle.
    expect(wrapper.findAll('tbody tr')).toHaveLength(4)

    const toggle = wrapper.findAll('button').find((b) => b.text().startsWith('Show unchanged'))
    expect(toggle).toBeTruthy()
    await toggle!.trigger('click')

    expect(wrapper.findAll('tbody tr')).toHaveLength(diff.items.length)
  })

  it('defaults the split item’s radios to "both"', async () => {
    const { wrapper } = await mountFipMigrate()

    const bothRadio = wrapper.find('input[type="radio"][name="split-F2"][value="both"]')
    expect(bothRadio.exists()).toBe(true)
    expect((bothRadio.element as HTMLInputElement).checked).toBe(true)
  })

  it('opens a confirm dialog naming the target version, and migrates on confirm', async () => {
    migrateFipMock.mockResolvedValue(makeFip())
    const { wrapper, router } = await mountFipMigrate()

    const migrateBtn = wrapper.findAll('button').find((b) => b.text() === en.migration.migrate)
    await migrateBtn!.trigger('click')

    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(wrapper.find('[role="dialog"]').text()).toContain('1.1.0')

    const confirmBtn = wrapper.find('[role="dialog"]').findAll('button').find((b) => b.text() === en.migration.migrate)
    await confirmBtn!.trigger('click')
    await flushPromises()

    expect(migrateFipMock).toHaveBeenCalledWith(
      'fip1',
      {
        to: '1.1.0',
        decisions: { splitCopies: { F2: ['F2-metadata', 'F2-data'] } },
      },
      undefined
    )
    expect(router.currentRoute.value.name).toBe('FipEditor')
  })
})
