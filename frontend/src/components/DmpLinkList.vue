<template>
  <div class="dmp-link-list">
    <p v-if="rows.length === 0" class="dmp-none">{{ $t('dmp.none') }}</p>

    <div v-for="(row, i) in rows" :key="i" class="dmp-row">
      <label class="dmp-field dmp-field-url">
        <span class="sr-only">{{ $t('dmp.url') }}</span>
        <input
          v-model.trim="row.url"
          type="url"
          class="dmp-input"
          :class="{ invalid: row.error }"
          placeholder="https://fiodmp.fiocruz.br/KQU5N0C"
          :disabled="readOnly"
          maxlength="2048"
          @blur="onUrlBlur(i)"
        />
        <span v-if="row.error" class="dmp-error">{{ $t(row.error) }}</span>
      </label>

      <label class="dmp-field dmp-field-version">
        <span class="sr-only">{{ $t('dmp.version') }}</span>
        <input
          v-model.trim="row.version"
          type="text"
          class="dmp-input"
          :placeholder="$t('dmp.version')"
          :disabled="readOnly"
          maxlength="20"
          @change="onFieldChange"
        />
      </label>

      <span
        class="dmp-system-badge"
        :class="row.system === 'FioDMP' ? 'badge-filled' : 'badge-outline'"
      >
        {{ row.system === 'FioDMP' ? $t('dmp.fiodmp') : $t('dmp.other') }}
      </span>

      <button v-if="!readOnly" type="button" class="dmp-remove-btn" @click="removeRow(i)">
        {{ $t('dmp.remove') }}
      </button>
    </div>

    <button
      v-if="!readOnly"
      type="button"
      class="dmp-add-btn"
      :disabled="rows.length >= MAX_ENTRIES"
      @click="addRow"
    >
      {{ $t('dmp.add') }}
    </button>
    <p v-if="!readOnly && rows.length >= MAX_ENTRIES" class="dmp-hint">{{ $t('dmp.maxReached') }}</p>
  </div>
</template>

<script lang="ts" setup>
import { ref, watch } from 'vue'
import { detectSystem, normaliseDmpUrl } from '@/lib/dmp'
import type { RelatedDmp } from '@/types/api'

/**
 * Up to 10 related-DMP rows (spec 06 §1.2): URL, optional version, a
 * derived system badge. Presentational only — no store access — the host
 * (`FipEditor.vue`) binds `entries`/`readOnly` and forwards `update` to
 * `store.setRelatedDmps`. Validation on blur mirrors `lib/dmp.ts`; the
 * server's normalised list is the eventual source of truth once the parent
 * re-passes `entries` after a save round trip.
 */
const props = defineProps<{ entries: RelatedDmp[]; readOnly: boolean }>()
const emit = defineEmits<{ update: [RelatedDmp[]] }>()

const MAX_ENTRIES = 10

interface Row {
  url: string
  version: string
  system: 'FioDMP' | 'other'
  dmpId?: string
  error: string | null
}

function toRow(entry: RelatedDmp): Row {
  const normalised = normaliseDmpUrl(entry.url)
  const detected = normalised ? detectSystem(normalised) : null
  return {
    url: entry.url,
    version: entry.version ?? '',
    system: detected?.system ?? (entry.system === 'FioDMP' ? 'FioDMP' : 'other'),
    dmpId: detected?.dmpId ?? entry.dmpId ?? undefined,
    error: null,
  }
}

const rows = ref<Row[]>(props.entries.map(toRow))

// Re-syncs from the prop whenever the parent's underlying list changes —
// in particular after the autosave response replaces `store.fip.relatedDmps`
// with the server's normalised entries (casing, badge, dmpId).
watch(
  () => props.entries,
  (entries) => {
    rows.value = entries.map(toRow)
  }
)

/**
 * Only rows with no `error` are sent to the parent (and, via it, the
 * server): a row still flagged `dmp.urlInvalid`/`dmp.duplicate` stays local
 * and visible with its inline error, so a version edit elsewhere in the
 * list (`onFieldChange`) can never re-emit — and PATCH — a malformed or
 * duplicate URL.
 */
function emitUpdate() {
  const result: RelatedDmp[] = rows.value
    .filter((row) => row.url.trim() !== '' && !row.error)
    .map((row) => ({
      url: row.url,
      version: row.version.trim() ? row.version.trim() : null,
      system: row.system,
      dmpId: row.dmpId ?? null,
    }))
  emit('update', result)
}

function onFieldChange() {
  emitUpdate()
}

function onUrlBlur(index: number) {
  const row = rows.value[index]
  const trimmed = row.url.trim()
  row.url = trimmed
  if (!trimmed) {
    row.error = null
    return
  }

  const normalised = normaliseDmpUrl(trimmed)
  if (!normalised) {
    row.error = 'dmp.urlInvalid'
    return
  }

  const isDuplicate = rows.value.some((other, i) => {
    if (i === index || !other.url.trim()) return false
    const otherNormalised = normaliseDmpUrl(other.url)
    return otherNormalised !== null && otherNormalised === normalised
  })
  if (isDuplicate) {
    row.error = 'dmp.duplicate'
    return
  }

  const detected = detectSystem(normalised)
  row.url = detected.url
  row.system = detected.system
  row.dmpId = detected.dmpId
  row.error = null
  emitUpdate()
}

function addRow() {
  if (rows.value.length >= MAX_ENTRIES) return
  rows.value = [...rows.value, { url: '', version: '', system: 'other', error: null }]
}

function removeRow(index: number) {
  rows.value = rows.value.filter((_, i) => i !== index)
  emitUpdate()
}
</script>

<style scoped>
.dmp-link-list {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.dmp-none {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.dmp-row {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.5rem;
  align-items: start;
  padding: 0.6rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-hover);
}

.dmp-field {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.dmp-input {
  width: 100%;
  min-height: 44px;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
  font-size: var(--font-size-sm);
}

.dmp-input.invalid {
  border-color: var(--color-error);
}

.dmp-error {
  font-size: var(--font-size-xs);
  color: var(--color-error);
}

.dmp-system-badge {
  justify-self: start;
  font-size: var(--font-size-xs);
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  white-space: nowrap;
}

.badge-filled {
  background-color: var(--color-chip-bg);
  color: var(--color-chip-text);
}

.badge-outline {
  background: none;
  border: 1px solid var(--color-border);
  color: var(--color-text-secondary);
}

.dmp-remove-btn {
  justify-self: start;
  min-height: 44px;
  padding: 0.3rem 0.75rem;
  border: 1px solid var(--color-error);
  border-radius: var(--border-radius-sm);
  background: none;
  color: var(--color-error);
  font-size: var(--font-size-sm);
}

.dmp-add-btn {
  align-self: flex-start;
  min-height: 44px;
  padding: 0.4rem 0.9rem;
  border: 1px solid var(--color-primary);
  border-radius: var(--border-radius-sm);
  background: none;
  color: var(--color-primary);
  font-size: var(--font-size-sm);
}

.dmp-add-btn:disabled {
  opacity: 0.5;
}

.dmp-hint {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

@media (min-width: 640px) {
  .dmp-row {
    grid-template-columns: 2fr 1fr auto auto;
  }
}
</style>
