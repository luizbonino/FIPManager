<template>
  <details class="population-picker no-print" open>
    <summary>{{ $t('dashboard.population.title') }}</summary>

    <div v-if="savedLabel" class="saved-info">
      <p class="saved-label">{{ savedLabel }}</p>
      <p class="saved-meta">
        {{ $t('dashboard.population.savedMeta', { count: savedFipCountText, computedAt: savedComputedAtText }) }}
      </p>
    </div>

    <div class="term-add-row">
      <label class="field">
        <span>{{ $t('dashboard.population.addTerm') }}</span>
        <select v-model="draftKind">
          <option value="public">{{ $t('dashboard.population.kind.public') }}</option>
          <option value="network">{{ $t('dashboard.population.kind.network') }}</option>
          <option value="mine">{{ $t('dashboard.population.kind.mine') }}</option>
          <option value="session">{{ $t('dashboard.population.kind.session') }}</option>
          <option value="questionnaire">{{ $t('dashboard.population.kind.questionnaire') }}</option>
          <option value="area">{{ $t('dashboard.population.kind.area') }}</option>
        </select>
      </label>
      <label v-if="needsId" class="field">
        <span>{{ $t('dashboard.population.idLabel') }}</span>
        <input ref="idInputRef" v-model="draftId" type="text" />
      </label>
      <label v-if="needsVersion" class="field">
        <span>{{ $t('dashboard.population.versionLabel') }}</span>
        <input v-model="draftVersion" type="text" />
      </label>
      <label v-if="draftKind === 'area'" class="field">
        <span>{{ $t('dashboard.population.sessionIdLabel') }}</span>
        <input v-model="draftSessionId" type="text" />
      </label>
      <button type="button" class="btn btn-secondary" @click="addTerm">{{ $t('dashboard.population.add') }}</button>
    </div>

    <ul class="term-list" aria-label="dashboard.population.includeList">
      <li v-for="(term, index) in modelValue.include" :key="termKey(term, index)" class="term-chip">
        {{ describeTerm(term) }}
        <button type="button" class="remove-btn" :aria-label="$t('dashboard.population.remove')" @click="removeTerm(index)">×</button>
      </li>
    </ul>
    <p v-if="modelValue.include.length === 0" class="empty-hint">{{ $t('dashboard.population.noTerms') }}</p>

    <details class="advanced">
      <summary>{{ $t('dashboard.population.advanced') }}</summary>
      <fieldset class="date-range">
        <legend>{{ $t('dashboard.population.dateRange') }}</legend>
        <label class="field">
          <span>{{ $t('dashboard.population.updatedAfter') }}</span>
          <input :value="modelValue.updatedAfter ?? ''" type="date" @change="setDate('updatedAfter', $event)" />
        </label>
        <label class="field">
          <span>{{ $t('dashboard.population.updatedBefore') }}</span>
          <input :value="modelValue.updatedBefore ?? ''" type="date" @change="setDate('updatedBefore', $event)" />
        </label>
      </fieldset>
    </details>

    <div class="save-share-row">
      <label class="field">
        <span>{{ $t('dashboard.population.labelField') }}</span>
        <input v-model="saveLabel" type="text" :placeholder="$t('dashboard.population.labelPlaceholder')" />
      </label>
      <button type="button" class="btn btn-primary" :disabled="saving || modelValue.include.length === 0" @click="save">
        {{ saving ? $t('dashboard.population.saving') : $t('dashboard.population.save') }}
      </button>
      <button type="button" class="btn btn-secondary" @click="copyLink">
        {{ copied ? $t('dashboard.population.linkCopied') : $t('dashboard.population.copyLink') }}
      </button>
    </div>
    <p v-if="saveError" class="save-error">{{ saveError }}</p>
  </details>
</template>

<script lang="ts" setup>
import { computed, nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { encodePopulationParam, type PopulationSpec, type PopulationTerm, type PopulationTermKind } from '@/lib/dashboard'
import { savePopulation } from '@/api/dashboard'
import type { SavedPopulation } from '@/types/dashboard'

/**
 * The six population-term kinds, a date range, save/share (spec 13 §2.1,
 * §6.1, §6.3). Pure view state — `modelValue` is a `PopulationSpec`, every
 * edit is a synchronous `update:modelValue`; the caller derives its `pop`
 * query param from it via `encodePopulationParam` and refetches on that
 * change (unlike a groupBy/language change, a population change *is* new
 * data). "Save this population" calls `POST /api/dashboard/populations`
 * and emits `saved` so the caller can switch the URL to the returned hash.
 */
const props = defineProps<{
  modelValue: PopulationSpec
  savedLabel?: string | null
  savedFipCount?: number | null
  savedComputedAt?: string | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: PopulationSpec): void
  (e: 'saved', value: SavedPopulation): void
}>()

const { t } = useI18n()

const draftKind = ref<PopulationTermKind>('public')
const draftId = ref('')
const draftVersion = ref('')
const draftSessionId = ref('')
const saveLabel = ref('')
const saving = ref(false)
const saveError = ref<string | null>(null)
const copied = ref(false)
const idInputRef = ref<HTMLInputElement | null>(null)

const needsId = computed(() => ['session', 'questionnaire', 'area'].includes(draftKind.value))
const needsVersion = computed(() => ['questionnaire', 'area'].includes(draftKind.value))

// `fipCount` is `null` precisely when k-anonymity withholds it (spec 13
// §2.4) — the count itself would disclose a FIP the viewer could not open
// individually. `?? 0` would render that suppressed population as "0 FIPs",
// a wrong number shown to a facilitator, so the withheld case renders as
// text instead (same treatment as `DashboardHome.vue`'s headline count).
const savedFipCountText = computed(() => (props.savedFipCount == null ? t('dashboard.home.fipCountWithheld') : props.savedFipCount))

const savedComputedAtText = computed(() => {
  if (!props.savedComputedAt) return t('dashboard.snapshot.unknownAge')
  try {
    return new Date(props.savedComputedAt).toLocaleString()
  } catch {
    return props.savedComputedAt
  }
})

function termKey(term: PopulationTerm, index: number): string {
  return `${term.kind}-${term.id ?? ''}-${term.version ?? ''}-${term.sessionId ?? ''}-${index}`
}

function describeTerm(term: PopulationTerm): string {
  switch (term.kind) {
    case 'public':
      return t('dashboard.population.kind.public')
    case 'network':
      return t('dashboard.population.kind.network')
    case 'mine':
      return t('dashboard.population.kind.mine')
    case 'session':
      return t('dashboard.population.termSession', { id: term.id })
    case 'questionnaire':
      return t('dashboard.population.termQuestionnaire', { id: term.id, version: term.version })
    case 'area':
      return t('dashboard.population.termArea', { id: term.id, version: term.version })
    default:
      return term.kind
  }
}

function addTerm() {
  const term: PopulationTerm = { kind: draftKind.value }
  if (needsId.value) term.id = draftId.value.trim()
  if (needsVersion.value) term.version = draftVersion.value.trim()
  if (draftKind.value === 'area') term.sessionId = draftSessionId.value.trim()
  if (needsId.value && !term.id) return
  emit('update:modelValue', { ...props.modelValue, include: [...props.modelValue.include, term] })
  draftId.value = ''
  draftVersion.value = ''
  draftSessionId.value = ''
}

function removeTerm(index: number) {
  const include = props.modelValue.include.filter((_, i) => i !== index)
  emit('update:modelValue', { ...props.modelValue, include })
}

function setDate(field: 'updatedAfter' | 'updatedBefore', event: Event) {
  const value = (event.target as HTMLInputElement).value
  const iso = value ? new Date(`${value}T00:00:00Z`).toISOString() : null
  emit('update:modelValue', { ...props.modelValue, [field]: iso })
}

async function save() {
  saving.value = true
  saveError.value = null
  try {
    const result = await savePopulation({
      spec: props.modelValue,
      label: saveLabel.value.trim() || null,
    })
    emit('saved', result)
  } catch {
    saveError.value = t('dashboard.population.saveFailed')
  } finally {
    saving.value = false
  }
}

async function copyLink() {
  let param: string
  try {
    param = encodePopulationParam(props.modelValue)
  } catch {
    saveError.value = t('dashboard.population.tooLargeForLink')
    return
  }
  const url = `${location.origin}${location.pathname}?pop=${param}`
  try {
    await navigator.clipboard.writeText(url)
  } catch {
    // Clipboard API unavailable — nothing more to do; the URL is already in the query bar once saved.
  }
  copied.value = true
  setTimeout(() => {
    copied.value = false
  }, 2000)
}

/**
 * Called by `DashboardHome.vue`'s empty-state "try a session" / "try a
 * questionnaire" buttons (spec 13 §9 A8 follow-up): a one-click way into
 * the term the caller most likely wants next, rather than prose telling
 * them to scroll down and pick it themselves. Preselects the term kind and
 * moves focus to its ID field; it does not add the term itself, since a
 * session/questionnaire term is meaningless without an ID only the user
 * knows.
 */
async function focusTerm(kind: PopulationTermKind) {
  draftKind.value = kind
  await nextTick()
  idInputRef.value?.focus()
}

defineExpose({ focusTerm })
</script>

<style scoped>
.population-picker {
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  padding: 0.75rem 1rem;
  background-color: var(--color-background);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.population-picker summary {
  cursor: pointer;
  font-weight: var(--font-weight-medium);
  min-height: 44px;
  display: flex;
  align-items: center;
}

.saved-info {
  padding: 0.4rem 0.6rem;
  background-color: var(--color-hover);
  border-radius: var(--border-radius-sm);
}

.saved-label {
  margin: 0;
  font-weight: var(--font-weight-medium);
}

.saved-meta {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.term-add-row,
.save-share-row {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  align-items: flex-end;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: var(--font-size-sm);
}

.field input,
.field select {
  min-height: 44px;
  padding: 0.35rem 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
}

.term-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.term-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.2rem 0.5rem;
  background-color: var(--color-chip-bg, var(--color-secondary));
  color: var(--color-chip-text, var(--color-secondary-text));
  border-radius: 999px;
  font-size: var(--font-size-xs);
}

.remove-btn {
  border: none;
  background: none;
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
  color: inherit;
}

.empty-hint {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.advanced {
  font-size: var(--font-size-sm);
}

.date-range {
  display: flex;
  gap: 0.75rem;
  border: none;
  padding: 0.5rem 0;
  flex-wrap: wrap;
}

.btn {
  min-height: 44px;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: var(--border-radius-sm);
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
  opacity: 0.6;
}

.save-error {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-status-planned-replacement);
}
</style>
