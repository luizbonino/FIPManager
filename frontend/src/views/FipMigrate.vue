<template>
  <div class="fip-migrate-view">
    <div v-if="loading" class="loading">
      <p>{{ $t('common.loading') }}</p>
    </div>

    <div v-else-if="notFound" class="message-box">
      <p>{{ $t('common.notFound') }}</p>
      <router-link to="/" class="btn btn-secondary">{{ $t('nav.home') }}</router-link>
    </div>

    <div v-else-if="forbidden" class="message-box">
      <p>{{ $t('errors.forbidden') }}</p>
      <router-link :to="`/fips/${fipId}`" class="btn btn-secondary">{{ $t('common.view') }}</router-link>
    </div>

    <div v-else-if="targets.length === 0" class="message-box">
      <p>{{ $t('migration.notAvailable') }}</p>
      <router-link :to="`/fips/${fipId}/edit`" class="btn btn-secondary">{{ $t('editor.title') }}</router-link>
    </div>

    <template v-else>
      <header class="migrate-header">
        <h1>{{ $t('migration.review') }}</h1>
        <p v-if="pinned" class="pinned-notice">{{ $t('migration.pinned') }}</p>
        <label v-if="targets.length > 1" class="target-select">
          <span>{{ $t('migration.targetLabel') }}</span>
          <select v-model="selectedVersion">
            <option v-for="target in targets" :key="target.version" :value="target.version">
              {{ target.version }}
            </option>
          </select>
        </label>
        <p v-else class="target-single">{{ $t('migration.targetLabel') }}: {{ selectedVersion }}</p>
      </header>

      <div v-if="previewLoading" class="loading"><p>{{ $t('common.loading') }}</p></div>
      <p v-else-if="previewError" class="form-error">{{ previewError }}</p>

      <template v-else-if="diff">
        <p class="summary-line">
          {{ $t('migration.summary', summary) }}
        </p>

        <div class="diff-scroll">
          <table class="diff-table">
            <thead>
              <tr>
                <th scope="col">{{ $t('migration.oldQuestion') }}</th>
                <th scope="col">{{ $t('migration.newQuestion') }}</th>
                <th scope="col">{{ $t('common.status') }}</th>
                <th scope="col">{{ $t('common.confirm') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in visibleRows" :key="rowKey(item)">
                <td :data-label="$t('migration.oldQuestion')">
                  <span v-if="item.oldQuestionId" class="question-id">{{ item.oldQuestionId }}</span>
                  <p v-if="item.oldText" class="question-text">{{ item.oldText }}</p>
                </td>
                <td :data-label="$t('migration.newQuestion')">
                  <span v-if="item.newQuestionId" class="question-id">{{ item.newQuestionId }}</span>
                  <p v-if="item.newText" class="question-text">{{ item.newText }}</p>
                </td>
                <td :data-label="$t('common.status')">
                  <StatusBadge :status="item.status" />
                  <span v-for="flag in item.flags" :key="flag" class="flag-chip">
                    {{ $t(flag === 'text-changed' ? 'migration.flagTextChanged' : 'migration.flagFerTypeChanged') }}
                  </span>
                </td>
                <td :data-label="$t('common.confirm')">
                  <fieldset v-if="item.decision?.kind === 'splitCopies' && item.oldQuestionId" class="split-choice">
                    <label v-for="choice in SPLIT_CHOICES" :key="choice">
                      <input
                        type="radio"
                        :name="`split-${item.oldQuestionId}`"
                        :value="choice"
                        :checked="splitChoiceFor(item) === choice"
                        @change="setSplitChoice(item, choice)"
                      />
                      {{ $t(`migration.split${choice.charAt(0).toUpperCase()}${choice.slice(1)}`) }}
                    </label>
                  </fieldset>
                  <label v-else-if="item.decision?.kind === 'orphanReassign' && item.oldQuestionId" class="reassign-select">
                    <span class="sr-only">{{ $t('migration.reassign') }}</span>
                    <select :value="decisions.orphanReassign[item.oldQuestionId] ?? ''" @change="onReassignChange(item, $event)">
                      <option value="">{{ $t('migration.keepOrphaned') }}</option>
                      <option v-for="option in item.decision.options" :key="option" :value="option">{{ option }}</option>
                    </select>
                  </label>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <button v-if="plainItems.length > 0" type="button" class="btn btn-secondary toggle-unchanged" @click="showUnchanged = !showUnchanged">
          {{ $t('migration.showUnchanged', { count: plainItems.length }) }}
        </button>

        <p v-if="submitError" class="form-error">{{ submitError }}</p>

        <div class="migrate-actions">
          <button type="button" class="btn btn-primary" :disabled="submitting" @click="showConfirm = true">
            {{ $t('migration.migrate') }}
          </button>
        </div>

        <div v-if="showConfirm" class="confirm-overlay" role="dialog" aria-modal="true">
          <div class="confirm-dialog">
            <h2>{{ $t('migration.confirmTitle', { version: selectedVersion }) }}</h2>
            <p>{{ $t('migration.confirmBody', { version: selectedVersion }) }}</p>
            <div class="confirm-actions">
              <button type="button" class="btn btn-secondary" @click="showConfirm = false">{{ $t('common.cancel') }}</button>
              <button type="button" class="btn btn-primary" :disabled="submitting" @click="onConfirmMigrate">
                {{ $t('migration.migrate') }}
              </button>
            </div>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ApiResponseError } from '@/api/client'
import { getFip, getMigrationPreview, getMigrationTargets, migrateFip } from '@/api/fips'
import { getToken } from '@/lib/editTokens'
import { buildMigrateDecisions, defaultDecisions, summarizeDecisions } from '@/lib/migration'
import type { MigrationDecisionsState } from '@/lib/migration'
import StatusBadge from '@/components/StatusBadge.vue'
import type { MigrationDiff, MigrationDiffItem, MigrationTargetItem } from '@/types/api'

/**
 * spec 07 §5: `/fips/:id/migrate` — target select (when several), a diff
 * table (old question | new question | status | decision), a summary line,
 * a `Migrate` button that is never blocked (defaults are valid), and a
 * confirm dialog naming the target version. Write rights are checked here,
 * like `FipEditor.vue`, via the same-auth-as-write `GET /api/fips/{id}`.
 */
const SPLIT_CHOICES = ['both', 'metadata', 'data', 'none'] as const
type SplitChoice = (typeof SPLIT_CHOICES)[number]

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const fipId = computed(() => String(route.params.id))
const editToken = computed(() => getToken(fipId.value) ?? undefined)

const loading = ref(true)
const notFound = ref(false)
const forbidden = ref(false)
const pinned = ref(false)

const targets = ref<MigrationTargetItem[]>([])
const selectedVersion = ref('')

const previewLoading = ref(false)
const previewError = ref<string | null>(null)
const diff = ref<MigrationDiff | null>(null)
const decisions = ref<MigrationDecisionsState>({ splitCopies: {}, orphanReassign: {} })

const showUnchanged = ref(false)
const showConfirm = ref(false)
const submitting = ref(false)
const submitError = ref<string | null>(null)

const priorityItems = computed(() => diff.value?.items.filter((i) => i.status === 'split' || i.status === 'removed') ?? [])
const addedItems = computed(() => diff.value?.items.filter((i) => i.status === 'added') ?? [])
const flaggedItems = computed(
  () => diff.value?.items.filter((i) => (i.status === 'unchanged' || i.status === 'hidden') && i.flags.length > 0) ?? []
)
const plainItems = computed(
  () => diff.value?.items.filter((i) => (i.status === 'unchanged' || i.status === 'hidden') && i.flags.length === 0) ?? []
)
const visibleRows = computed(() => [
  ...priorityItems.value,
  ...addedItems.value,
  ...flaggedItems.value,
  ...(showUnchanged.value ? plainItems.value : []),
])

const summary = computed(() => summarizeDecisions(diff.value ?? { items: [] } as unknown as MigrationDiff, decisions.value))

function rowKey(item: MigrationDiffItem): string {
  return `${item.oldQuestionId ?? '-'}::${item.newQuestionId ?? '-'}`
}

function splitChoiceFor(item: MigrationDiffItem): SplitChoice {
  if (!item.oldQuestionId || !item.splitInto) return 'both'
  const chosen = decisions.value.splitCopies[item.oldQuestionId] ?? []
  const [metaId, dataId] = item.splitInto
  const hasMeta = chosen.includes(metaId)
  const hasData = chosen.includes(dataId)
  if (hasMeta && hasData) return 'both'
  if (hasMeta) return 'metadata'
  if (hasData) return 'data'
  return 'none'
}

function setSplitChoice(item: MigrationDiffItem, choice: SplitChoice): void {
  if (!item.oldQuestionId || !item.splitInto) return
  const [metaId, dataId] = item.splitInto
  const chosen =
    choice === 'both' ? [metaId, dataId] : choice === 'metadata' ? [metaId] : choice === 'data' ? [dataId] : []
  decisions.value.splitCopies[item.oldQuestionId] = chosen
}

function onReassignChange(item: MigrationDiffItem, event: Event): void {
  if (!item.oldQuestionId) return
  const value = (event.target as HTMLSelectElement).value
  decisions.value.orphanReassign[item.oldQuestionId] = value || null
}

async function loadPreview() {
  if (!selectedVersion.value) return
  previewLoading.value = true
  previewError.value = null
  try {
    diff.value = await getMigrationPreview(fipId.value, selectedVersion.value, editToken.value)
    decisions.value = defaultDecisions(diff.value)
  } catch {
    previewError.value = t('migration.loadError')
    diff.value = null
  } finally {
    previewLoading.value = false
  }
}

watch(selectedVersion, loadPreview)

async function onConfirmMigrate() {
  if (!diff.value) return
  showConfirm.value = false
  submitting.value = true
  submitError.value = null
  try {
    const body = { to: selectedVersion.value, decisions: buildMigrateDecisions(diff.value, decisions.value) }
    await migrateFip(fipId.value, body, editToken.value)
    await router.push(`/fips/${fipId.value}/edit`)
  } catch (err) {
    if (err instanceof ApiResponseError && err.data.detail === 'already_on_version') {
      submitError.value = t('migration.alreadyOnVersion')
    } else if (err instanceof ApiResponseError && err.data.detail === 'session_version_pinned') {
      submitError.value = t('migration.pinned')
    } else {
      submitError.value = t('errors.serverError')
    }
  } finally {
    submitting.value = false
  }
}

async function init() {
  loading.value = true
  notFound.value = false
  forbidden.value = false
  try {
    const fip = await getFip(fipId.value, editToken.value)
    pinned.value = !!fip.sessionId
    const targetsResult = await getMigrationTargets(fipId.value, editToken.value)
    targets.value = targetsResult.items
    if (targets.value.length > 0) {
      selectedVersion.value = targets.value[targets.value.length - 1].version
      await loadPreview()
    }
  } catch (err) {
    if (err instanceof ApiResponseError && err.status === 404) {
      notFound.value = true
    } else if (err instanceof ApiResponseError && err.status === 403) {
      forbidden.value = true
    } else {
      notFound.value = true
    }
  } finally {
    loading.value = false
  }
}

onMounted(init)
</script>

<style scoped>
.fip-migrate-view {
  max-width: 900px;
  margin: 0 auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.loading,
.message-box {
  text-align: center;
  padding: 3rem 1rem;
}

.migrate-header {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.migrate-header h1 {
  margin: 0;
  color: var(--color-primary);
}

.pinned-notice {
  margin: 0;
  padding: 0.5rem 0.75rem;
  background-color: var(--color-user-info);
  color: var(--color-user-info-text);
  border-radius: var(--border-radius-sm);
  font-size: var(--font-size-sm);
}

.target-select {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: var(--font-size-sm);
}

.target-select select {
  min-height: 44px;
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
}

.target-single {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.summary-line {
  margin: 0;
  font-weight: var(--font-weight-medium);
}

.diff-scroll {
  overflow-x: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
}

.diff-table {
  border-collapse: collapse;
  width: 100%;
  min-width: 40rem;
}

.diff-table th,
.diff-table td {
  border: 1px solid var(--color-border);
  padding: 0.5rem 0.6rem;
  vertical-align: top;
  text-align: left;
}

.diff-table thead th {
  background-color: var(--color-hover);
}

.question-id {
  font-family: monospace;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  background-color: var(--color-secondary);
  padding: 0.1rem 0.4rem;
  border-radius: var(--border-radius-sm);
}

.question-text {
  margin: 0.3rem 0 0;
}

.flag-chip {
  display: inline-block;
  margin: 0.25rem 0.25rem 0 0;
  font-size: var(--font-size-xs);
  color: var(--color-chip-text);
  background-color: var(--color-chip-bg);
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
}

.split-choice {
  border: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: var(--font-size-sm);
}

.reassign-select select {
  min-height: 44px;
  padding: 0.3rem 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
}

.toggle-unchanged {
  align-self: flex-start;
}

.migrate-actions {
  display: flex;
  justify-content: flex-end;
}

.confirm-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
  padding: 1rem;
}

.confirm-dialog {
  background-color: var(--color-background);
  border-radius: var(--border-radius-md);
  padding: 1.5rem;
  max-width: 24rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.btn {
  min-height: 44px;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: var(--border-radius-sm);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
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

.btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.form-error {
  color: var(--color-error);
  padding: 0.5rem;
  background-color: var(--color-error-bg);
  border-radius: var(--border-radius-sm);
}

/* 375px: the table collapses to stacked cards (spec 07 §5). */
@media (max-width: 640px) {
  .diff-table,
  .diff-table thead,
  .diff-table tbody,
  .diff-table th,
  .diff-table td,
  .diff-table tr {
    display: block;
  }

  .diff-table {
    min-width: 0;
  }

  .diff-table thead {
    position: absolute;
    left: -9999px;
  }

  .diff-table tr {
    border: 1px solid var(--color-border);
    border-radius: var(--border-radius-md);
    margin-bottom: 0.75rem;
  }

  .diff-table td {
    border: none;
    border-bottom: 1px solid var(--color-border);
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .diff-table td::before {
    content: attr(data-label);
    font-size: var(--font-size-xs);
    font-weight: var(--font-weight-bold);
    color: var(--color-text-secondary);
  }

  .diff-table tr td:last-child {
    border-bottom: none;
  }
}
</style>
