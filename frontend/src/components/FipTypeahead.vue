<template>
  <div class="fip-typeahead">
    <label class="field">
      <span>{{ $t('dashboard.similarity.fipId') }}</span>
      <input
        ref="inputEl"
        v-model="query"
        type="text"
        role="combobox"
        aria-autocomplete="list"
        :aria-expanded="open"
        aria-controls="fip-typeahead-listbox"
        :aria-activedescendant="highlighted >= 0 ? `fip-typeahead-opt-${highlighted}` : undefined"
        :placeholder="$t('dashboard.similarity.fipIdPlaceholder')"
        @focus="onFocus"
        @blur="onBlur"
        @keydown="onKeydown"
      />
    </label>
    <ul v-if="open" id="fip-typeahead-listbox" role="listbox" class="suggestions">
      <li
        v-for="(item, index) in items"
        :id="`fip-typeahead-opt-${index}`"
        :key="item.fipId"
        role="option"
        :aria-selected="index === highlighted"
        :class="{ active: index === highlighted }"
        @mousedown.prevent="select(item)"
      >
        <span class="opt-label">{{ item.label }}</span>
        <span v-if="item.areaKey" class="opt-area">{{ item.areaKey }}</span>
      </li>
      <li v-if="!loading && items.length === 0" class="no-results" role="presentation">
        {{ $t('dashboard.similarity.typeaheadNoResults') }}
      </li>
      <li v-if="loading" class="loading" role="presentation">{{ $t('common.loading') }}</li>
    </ul>
  </div>
</template>

<script lang="ts" setup>
import { ref, watch } from 'vue'
import { getFipLookup } from '@/api/dashboard'
import type { FipLookupItem } from '@/types/dashboard'

/**
 * Spec 13 §3.7/§6.2/§11.4: typeahead over `GET /api/dashboard/fips` for the
 * neighbours panel's FIP picker, replacing the plain text input. Debounced
 * 300 ms (same idiom as `NetworkFipList.vue`), at most 20 suggestions
 * (the endpoint's own cap), keyboard navigable (Up/Down/Enter/Escape,
 * `aria-activedescendant` combobox pattern), and falling back to accepting
 * a pasted id verbatim on blur or Enter with nothing highlighted — the
 * endpoint is a convenience, not a gate: a participant who already knows
 * the id can still just paste it, exactly as the plain input allowed.
 */
const props = defineProps<{
  modelValue: string
  population: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const query = ref(props.modelValue)
const items = ref<FipLookupItem[]>([])
const open = ref(false)
const loading = ref(false)
const highlighted = ref(-1)

let debounceTimer: ReturnType<typeof setTimeout> | null = null
let requestSeq = 0

watch(
  () => props.modelValue,
  (value) => {
    if (value !== lastEmitted) query.value = value
  }
)

let lastEmitted = props.modelValue

function scheduleSearch() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(runSearch, 300)
}

async function runSearch() {
  if (!props.population) {
    items.value = []
    return
  }
  const seq = ++requestSeq
  loading.value = true
  try {
    const result = await getFipLookup({ population: props.population, q: query.value.trim() || undefined, limit: 20 })
    if (seq !== requestSeq) return
    items.value = result.items.slice(0, 20)
  } catch {
    if (seq !== requestSeq) return
    items.value = []
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

function onFocus() {
  open.value = true
  scheduleSearch()
}

function select(item: FipLookupItem) {
  query.value = item.label
  lastEmitted = item.fipId
  emit('update:modelValue', item.fipId)
  open.value = false
  highlighted.value = -1
}

/** A typed/pasted value with no suggestion chosen is accepted as a literal FIP id (spec 13 §6.2's typeahead-with-fallback). */
function acceptTyped() {
  const value = query.value.trim()
  if (value && value !== lastEmitted) {
    lastEmitted = value
    emit('update:modelValue', value)
  }
  open.value = false
  highlighted.value = -1
}

function onBlur() {
  // Let a mousedown selection on an option (which preventDefault()s the
  // blur-causing focus shift) win; this only runs on a genuine blur.
  acceptTyped()
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    if (!open.value) {
      open.value = true
      scheduleSearch()
      return
    }
    highlighted.value = items.value.length === 0 ? -1 : Math.min(highlighted.value + 1, items.value.length - 1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    highlighted.value = Math.max(highlighted.value - 1, 0)
  } else if (event.key === 'Enter') {
    if (open.value && highlighted.value >= 0 && items.value[highlighted.value]) {
      event.preventDefault()
      select(items.value[highlighted.value])
    } else {
      acceptTyped()
    }
  } else if (event.key === 'Escape') {
    open.value = false
    highlighted.value = -1
  }
}

watch(query, () => {
  highlighted.value = -1
  if (open.value) scheduleSearch()
})
</script>

<style scoped>
.fip-typeahead {
  position: relative;
  display: flex;
  flex-direction: column;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: var(--font-size-sm);
}

.field input {
  min-height: 44px;
  padding: 0.3rem 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
}

.suggestions {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  z-index: 10;
  margin: 0.2rem 0 0;
  padding: 0.25rem 0;
  list-style: none;
  max-height: 16rem;
  overflow-y: auto;
  background-color: var(--color-background);
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
}

.suggestions li {
  padding: 0.4rem 0.6rem;
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.suggestions li.active {
  background-color: var(--color-hover);
}

.opt-area {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
}

.no-results,
.loading {
  color: var(--color-text-secondary);
  cursor: default;
}
</style>
