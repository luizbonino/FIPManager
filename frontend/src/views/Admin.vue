<template>
  <div class="admin-view">
    <template v-if="isAdmin">
      <h1>{{ $t('admin.title') }}</h1>

      <section class="panel">
        <h2>{{ $t('admin.users') }}</h2>
        <input
          v-model="userQuery"
          type="search"
          class="search-input"
          :placeholder="$t('admin.search')"
          @input="onUserSearch"
        />
        <div class="table-scroll">
          <table class="users-table">
            <thead>
              <tr>
                <th>{{ $t('common.name') }}</th>
                <th>{{ $t('auth.emailLabel') }}</th>
                <th>{{ $t('admin.role') }}</th>
                <th>{{ $t('admin.created') }}</th>
                <th>{{ $t('admin.fips') }}</th>
                <th>{{ $t('admin.sessions') }}</th>
                <th>{{ $t('admin.models') }}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in users" :key="u.id">
                <td>{{ u.displayName }}</td>
                <td>{{ u.email }}</td>
                <td>{{ u.role }}</td>
                <td>{{ formatDate(u.createdAt) }}</td>
                <td>{{ u.fipCount }}</td>
                <td>{{ u.sessionCount }}</td>
                <td>{{ u.knowledgeModelCount }}</td>
                <td>
                  <button
                    type="button"
                    class="btn btn-secondary"
                    :disabled="u.id === authStore.user?.id"
                    @click="onResetPassword(u)"
                  >
                    {{ $t('admin.resetPassword') }}
                  </button>
                </td>
              </tr>
              <tr v-if="users.length === 0">
                <td colspan="8" class="empty-state">{{ $t('common.notFound') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel">
        <h2>{{ $t('admin.pendingFers') }}</h2>
        <p v-if="mergeResultMessage" class="merge-result">{{ mergeResultMessage }}</p>
        <p v-if="pendingFers.length === 0" class="empty-state">{{ $t('admin.noPendingFers') }}</p>
        <ul v-else class="fer-list">
          <li v-for="f in pendingFers" :key="f.id" class="fer-row">
            <div class="fer-row-main">
              <span class="fer-label">{{ resolveLang(f.label, locale) ?? f.id }}</span>
              <span class="fer-type-chip">{{ f.type }}</span>
            </div>
            <span class="fer-owner">{{ $t('admin.owner') }}: {{ f.ownerEmail ?? '—' }}</span>
            <span class="fer-usage">{{ $t('admin.usage', { count: f.usageCount }) }}</span>
            <div class="fer-actions">
              <button type="button" class="btn btn-secondary" @click="onPromote(f)">{{ $t('admin.promote') }}</button>
              <button type="button" class="btn btn-secondary" @click="openMerge(f)">{{ $t('admin.merge') }}</button>
            </div>
          </li>
        </ul>
      </section>

      <div v-if="tempPassword" class="modal-backdrop" @click.self="tempPassword = null">
        <div class="modal">
          <h2>{{ $t('admin.tempPassword') }}</h2>
          <p class="hint">{{ $t('admin.tempPasswordOnce') }}</p>
          <div class="temp-password-row">
            <input
              :value="tempPassword"
              type="text"
              readonly
              class="temp-password-input"
              @focus="($event.target as HTMLInputElement).select()"
            />
            <button type="button" class="btn btn-secondary" @click="copyTempPassword">{{ $t('common.copy') }}</button>
          </div>
          <p v-if="copyDone" class="copy-done">{{ $t('share.copied') }}</p>
          <div class="modal-actions">
            <button type="button" class="btn btn-primary" @click="tempPassword = null">{{ $t('common.close') }}</button>
          </div>
        </div>
      </div>

      <div v-if="mergeSource" class="modal-backdrop" @click.self="closeMerge">
        <div class="modal">
          <h2>{{ $t('admin.merge') }}</h2>
          <p class="hint">{{ resolveLang(mergeSource.label, locale) ?? mergeSource.id }}</p>
          <FerPicker
            :options="mergeOptions"
            :fer-id="mergeTargetFerId"
            :fer-free-text="null"
            @change="onMergeFerChange"
          />
          <div class="modal-actions">
            <button type="button" class="btn btn-secondary" @click="closeMerge">{{ $t('common.cancel') }}</button>
            <button
              type="button"
              class="btn btn-primary"
              :disabled="!mergeTargetFerId"
              @click="confirmMerge"
            >
              {{ $t('common.confirm') }}
            </button>
          </div>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="message-box">
        <p>{{ $t('common.notFound') }}</p>
      </div>
    </template>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { listAdminFers, listAdminUsers, mergeFer, promoteFer, resetUserPassword } from '@/api/admin'
import { listFers } from '@/api/fers'
import { resolveLang } from '@/lib/lang'
import FerPicker from '@/components/FerPicker.vue'
import type { AdminFerOut, AdminUserOut, FerOut } from '@/types/api'

// spec 05 §1: the view itself renders `common.notFound` and calls no
// `/api/admin/*` route at all when the signed-in user isn't an admin —
// `require_admin_404` on the backend never confirms the prefix exists
// either way, so this mirrors that leak rule on the client.
const { t, locale } = useI18n()
const authStore = useAuthStore()

const isAdmin = computed(() => authStore.user?.role === 'admin')

// --- Users -----------------------------------------------------------

const users = ref<AdminUserOut[]>([])
const userQuery = ref('')
const tempPassword = ref<string | null>(null)
const copyDone = ref(false)
let searchTimer: ReturnType<typeof setTimeout> | null = null

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString()
}

async function loadUsers() {
  const result = await listAdminUsers({ q: userQuery.value || undefined, limit: 50 }).catch(() => ({
    items: [],
    total: 0,
  }))
  users.value = result.items
}

function onUserSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(loadUsers, 300)
}

async function onResetPassword(u: AdminUserOut) {
  if (u.id === authStore.user?.id) return
  if (!confirm(t('admin.resetConfirm'))) return
  try {
    const result = await resetUserPassword(u.id)
    copyDone.value = false
    tempPassword.value = result.temporaryPassword
  } catch {
    // Minimal v1 error handling: the confirm dialog already explained the
    // consequence; a failed reset simply leaves the modal unopened.
  }
}

async function copyTempPassword() {
  if (!tempPassword.value) return
  try {
    await navigator.clipboard.writeText(tempPassword.value)
    copyDone.value = true
  } catch {
    // Clipboard API unavailable (e.g. insecure context) — the readonly
    // input is still focusable/selectable for a manual copy.
  }
}

// --- FER promotions ----------------------------------------------------

const pendingFers = ref<AdminFerOut[]>([])
const mergeSource = ref<AdminFerOut | null>(null)
const mergeOptions = ref<FerOut[]>([])
const mergeTargetFerId = ref<string | null>(null)
const mergeResultMessage = ref<string | null>(null)

async function loadPendingFers() {
  const result = await listAdminFers({ pending: true, limit: 100 }).catch(() => ({ items: [], total: 0 }))
  pendingFers.value = result.items
}

async function onPromote(fer: AdminFerOut) {
  if (!confirm(t('admin.promoteConfirm'))) return
  try {
    await promoteFer(fer.id)
    await loadPendingFers()
  } catch {
    // Minimal v1 error handling — an already-promoted row (409) simply
    // stays in the list; the admin can retry or refresh.
  }
}

async function openMerge(fer: AdminFerOut) {
  mergeSource.value = fer
  mergeTargetFerId.value = null
  mergeResultMessage.value = null
  const result = await listFers({ type: fer.type, limit: 500 }).catch(() => ({ items: [], total: 0 }))
  mergeOptions.value = result.items.filter((f) => f.id !== fer.id)
}

function closeMerge() {
  mergeSource.value = null
  mergeOptions.value = []
  mergeTargetFerId.value = null
}

function onMergeFerChange(payload: { ferId: string | null; ferFreeText: string | null }) {
  mergeTargetFerId.value = payload.ferId
}

async function confirmMerge() {
  if (!mergeSource.value || !mergeTargetFerId.value) return
  const target = mergeOptions.value.find((f) => f.id === mergeTargetFerId.value)
  const label = target ? resolveLang(target.label, locale.value) ?? target.id : mergeTargetFerId.value
  // "then a double confirm" (spec 05 §1): picking a target in this modal is
  // the first step, this native confirm — irreversible, spelled out — the second.
  if (!confirm(t('admin.mergeConfirm', { label }))) return
  const source = mergeSource.value
  try {
    const result = await mergeFer(source.id, mergeTargetFerId.value)
    mergeResultMessage.value = t('admin.mergeDone', {
      declarations: result.repointedDeclarations,
      fips: result.repointedFips,
    })
    closeMerge()
    await loadPendingFers()
  } catch {
    // Minimal v1 error handling — the modal stays open so the admin can retry.
  }
}

onMounted(() => {
  if (!isAdmin.value) return
  void loadUsers()
  void loadPendingFers()
})
</script>

<style scoped>
.admin-view {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.message-box {
  text-align: center;
  padding: 3rem 1rem;
}

.panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.panel h2 {
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 0.4rem;
}

.search-input {
  min-height: 44px;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  max-width: 20rem;
}

.table-scroll {
  overflow-x: auto;
}

.users-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.users-table th,
.users-table td {
  text-align: left;
  padding: 0.5rem 0.6rem;
  border-bottom: 1px solid var(--color-border);
  white-space: nowrap;
}

.empty-state {
  color: var(--color-text-secondary);
  padding: 0.75rem 0;
  text-align: center;
}

.fer-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.fer-row {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.4rem;
  padding: 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  align-items: center;
}

.fer-row-main {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.fer-label {
  font-weight: var(--font-weight-medium);
}

.fer-type-chip {
  font-size: var(--font-size-xs);
  color: var(--color-chip-text);
  background-color: var(--color-chip-bg);
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
}

.fer-owner,
.fer-usage {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.fer-actions {
  display: flex;
  gap: 0.5rem;
}

.merge-result {
  padding: 0.5rem 0.75rem;
  background-color: var(--color-success-bg);
  color: var(--color-success);
  border-radius: var(--border-radius-sm);
  font-size: var(--font-size-sm);
}

.btn {
  min-height: 44px;
  padding: 0.4rem 0.9rem;
  border: none;
  border-radius: var(--border-radius-sm);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.btn-primary {
  background-color: var(--color-primary);
  color: var(--color-primary-text);
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  z-index: 100;
}

.modal {
  background-color: var(--color-background);
  border-radius: var(--border-radius-md);
  padding: 1.5rem;
  max-width: 28rem;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.modal .hint {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.temp-password-row {
  display: flex;
  gap: 0.5rem;
}

.temp-password-input {
  flex: 1;
  min-height: 44px;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  font-family: monospace;
  font-size: 1rem;
  letter-spacing: 0.05em;
}

.copy-done {
  margin: 0;
  color: var(--color-success);
  font-size: var(--font-size-xs);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}

@media (min-width: 640px) {
  .fer-row {
    grid-template-columns: 2fr 1fr 1fr auto;
  }
}
</style>
