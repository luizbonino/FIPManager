<template>
  <div class="fer-picker">
    <div v-if="mode === 'catalogue'" class="catalogue-mode">
      <label class="sr-only" :for="inputId">{{ $t('editor.chooseFer') }}</label>
      <input
        :id="inputId"
        v-model="query"
        type="text"
        class="fer-input"
        :placeholder="$t('editor.searchFer')"
        :disabled="disabled"
        autocomplete="off"
        @focus="showList = true"
        @input="showList = true"
        @blur="onBlur"
      />
      <ul v-if="showList && filtered.length > 0" class="fer-list">
        <li v-for="opt in filtered" :key="opt.id">
          <button type="button" class="fer-option" @mousedown.prevent="select(opt)">
            <span class="fer-option-label">{{ labelOf(opt) }}</span>
            <span v-if="opt.homepage" class="fer-option-homepage">{{ opt.homepage }}</span>
          </button>
        </li>
      </ul>
      <p v-else-if="showList && query.trim()" class="no-match">
        {{ $t('editor.noFerMatch') }}
      </p>
    </div>

    <div v-else class="free-text-mode">
      <label class="sr-only" :for="inputId">{{ $t('editor.freeTextPlaceholder') }}</label>
      <input
        :id="inputId"
        v-model="freeTextValue"
        type="text"
        class="fer-input"
        :placeholder="$t('editor.freeTextPlaceholder')"
        :disabled="disabled"
        @input="onFreeTextInput"
      />
    </div>

    <button type="button" class="toggle-mode" :disabled="disabled" @click="toggleMode">
      {{ mode === 'catalogue' ? $t('editor.useFreeText') : $t('editor.useCatalogue') }}
    </button>
  </div>
</template>

<script lang="ts" setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { resolveLang } from '@/lib/lang'
import type { FerOut } from '@/types/api'

/**
 * Combobox over the catalogue FERs of one `ferType` (spec 02 §2.2): a
 * search box filtering `options` client-side, and a "Use my own wording"
 * toggle writing `ferFreeText` instead. `ferId` xor `ferFreeText`, matching
 * the backend validator — `change` always emits exactly one of the two set.
 */
const props = defineProps<{
  options: FerOut[]
  ferId: string | null
  ferFreeText: string | null
  disabled?: boolean
}>()

const emit = defineEmits<{ change: [{ ferId: string | null; ferFreeText: string | null }] }>()

const { locale } = useI18n()

let uid = 0
const inputId = `fer-picker-${++uid}`

const mode = ref<'catalogue' | 'freeText'>(props.ferFreeText ? 'freeText' : 'catalogue')
const showList = ref(false)

function labelOf(opt: FerOut): string {
  return resolveLang(opt.label, locale.value) ?? opt.id
}

const selectedOption = computed(() => props.options.find((o) => o.id === props.ferId) ?? null)

const query = ref(selectedOption.value ? labelOf(selectedOption.value) : '')
const freeTextValue = ref(props.ferFreeText ?? '')

// Keep the local input in sync when the declaration changes from outside
// (e.g. store hydration after a save round trip).
watch(
  () => props.ferId,
  () => {
    query.value = selectedOption.value ? labelOf(selectedOption.value) : query.value
  }
)
watch(
  () => props.ferFreeText,
  (v) => {
    freeTextValue.value = v ?? ''
  }
)

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  const list = q ? props.options.filter((o) => labelOf(o).toLowerCase().includes(q)) : props.options
  return list.slice(0, 30)
})

function select(opt: FerOut) {
  query.value = labelOf(opt)
  showList.value = false
  emit('change', { ferId: opt.id, ferFreeText: null })
}

function onBlur() {
  // Delay so a `mousedown` on an option still registers before the list unmounts.
  setTimeout(() => {
    showList.value = false
  }, 150)
}

function toggleMode() {
  if (mode.value === 'catalogue') {
    mode.value = 'freeText'
    freeTextValue.value = freeTextValue.value || query.value
    emit('change', { ferId: null, ferFreeText: freeTextValue.value })
  } else {
    mode.value = 'catalogue'
    query.value = selectedOption.value ? labelOf(selectedOption.value) : ''
    emit('change', { ferId: selectedOption.value?.id ?? null, ferFreeText: null })
  }
}

function onFreeTextInput() {
  emit('change', { ferId: null, ferFreeText: freeTextValue.value })
}
</script>

<style scoped>
.fer-picker {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.catalogue-mode,
.free-text-mode {
  position: relative;
}

.fer-input {
  width: 100%;
  min-height: 44px;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
  font-size: var(--font-size-md);
}

.fer-list {
  position: absolute;
  z-index: 20;
  top: calc(100% + 2px);
  left: 0;
  right: 0;
  max-height: 14rem;
  overflow-y: auto;
  margin: 0;
  padding: 0.25rem;
  list-style: none;
  background-color: var(--color-background);
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  box-shadow: var(--shadow-md);
}

.fer-option {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: 44px;
  padding: 0.4rem 0.6rem;
  border: none;
  background: none;
  text-align: left;
  color: var(--color-text);
  border-radius: var(--border-radius-sm);
}

.fer-option:hover,
.fer-option:focus {
  background-color: var(--color-hover);
}

.fer-option-label {
  font-size: var(--font-size-sm);
}

.fer-option-homepage {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.no-match {
  margin: 0.25rem 0 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.toggle-mode {
  align-self: flex-start;
  min-height: 44px;
  padding: 0.3rem 0.6rem;
  border: none;
  background: none;
  color: var(--color-link);
  font-size: var(--font-size-sm);
  text-decoration: underline;
}
</style>
