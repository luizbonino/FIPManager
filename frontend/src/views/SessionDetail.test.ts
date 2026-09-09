import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import en from '@/i18n/en.json'
import type { SessionOut } from '@/types/api'

// A "Delete session" danger zone (backend: DELETE /api/sessions/{id}, owner
// or admin only) — deletes the session and its anonymous FIPs, detaches
// claimed FIPs. `GET /sessions/{id}` (what `useSessionStore().load` calls)
// is itself owner-or-admin gated, so the button only needs to key off
// whether the session loaded at all: a non-owner never reaches this
// session-loaded branch in the first place.
vi.mock('@/api/sessions', () => ({
  getSession: vi.fn(),
  listSessionFips: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  deleteSession: vi.fn(),
  sessionExportJsonUrl: (id: string) => `/api/sessions/${id}/export.json`,
  sessionExportCsvUrl: (id: string) => `/api/sessions/${id}/export.csv`,
  sessionExportTtlUrl: (id: string) => `/api/sessions/${id}/export.ttl`,
}))

import { deleteSession, getSession } from '@/api/sessions'
import SessionDetail from './SessionDetail.vue'

const getSessionMock = vi.mocked(getSession)
const deleteSessionMock = vi.mocked(deleteSession)

function makeSession(overrides: Partial<SessionOut> = {}): SessionOut {
  return {
    id: 'session-1',
    joinCode: 'ABC123',
    joinUrl: 'https://example.org/join/ABC123',
    ownerId: 'u1',
    questionnaireId: 'gofair-fip-mini',
    questionnaireVersion: '1.0.0',
    defaultLanguage: 'en',
    title: 'Test session',
    status: 'open',
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

async function mountSessionDetail() {
  const pinia = createPinia()
  setActivePinia(pinia)

  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/sessions/:id', name: 'SessionDetail', component: SessionDetail, props: true },
      { path: '/workspace', name: 'Workspace', component: { template: '<div/>' } },
    ],
  })
  await router.push('/sessions/session-1')
  await router.isReady()

  const wrapper = mount(SessionDetail, {
    global: {
      plugins: [pinia, makeI18n(), router],
      stubs: { QrCode: true, FeedbackForm: true, FeedbackSummary: true },
    },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('SessionDetail.vue — danger zone', () => {
  beforeEach(() => {
    getSessionMock.mockReset()
    deleteSessionMock.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows the delete button once the owner-gated session loads', async () => {
    getSessionMock.mockResolvedValue(makeSession())
    const { wrapper } = await mountSessionDetail()

    expect(wrapper.text()).toContain(en.sessionAdmin.dangerZone)
    const deleteBtn = wrapper.findAll('button').find((b) => b.text() === en.sessionAdmin.delete)
    expect(deleteBtn).toBeTruthy()
    wrapper.unmount()
  })

  it('does not show the delete button when the session fails to load (non-owner/admin)', async () => {
    getSessionMock.mockRejectedValue(new Error('not_found'))
    const { wrapper } = await mountSessionDetail()

    expect(wrapper.text()).not.toContain(en.sessionAdmin.dangerZone)
    const deleteBtn = wrapper.findAll('button').find((b) => b.text() === en.sessionAdmin.delete)
    expect(deleteBtn).toBeFalsy()
    wrapper.unmount()
  })

  it('calls deleteSession and redirects to /workspace after a confirmed delete', async () => {
    getSessionMock.mockResolvedValue(makeSession())
    deleteSessionMock.mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    const { wrapper, router } = await mountSessionDetail()
    const deleteBtn = wrapper.findAll('button').find((b) => b.text() === en.sessionAdmin.delete)!
    await deleteBtn.trigger('click')
    await flushPromises()

    expect(window.confirm).toHaveBeenCalledWith(en.sessionAdmin.deleteConfirm)
    expect(deleteSessionMock).toHaveBeenCalledWith('session-1')
    expect(router.currentRoute.value.path).toBe('/workspace')
    expect(router.currentRoute.value.query.sessionDeleted).toBe('1')
    wrapper.unmount()
  })

  it('does not call deleteSession when the confirm dialog is dismissed', async () => {
    getSessionMock.mockResolvedValue(makeSession())
    vi.spyOn(window, 'confirm').mockReturnValue(false)

    const { wrapper, router } = await mountSessionDetail()
    const deleteBtn = wrapper.findAll('button').find((b) => b.text() === en.sessionAdmin.delete)!
    await deleteBtn.trigger('click')
    await flushPromises()

    expect(deleteSessionMock).not.toHaveBeenCalled()
    expect(router.currentRoute.value.path).toBe('/sessions/session-1')
    wrapper.unmount()
  })
})
