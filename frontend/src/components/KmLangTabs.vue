<template>
  <div class="km-lang-tabs">
    <div class="tabs" role="tablist">
      <button
        v-for="lang in LANGUAGES"
        :key="lang"
        type="button"
        role="tab"
        :aria-selected="lang === active"
        class="tab"
        :class="{ active: lang === active }"
        @click="active = lang"
      >
        {{ $t(`languages.${lang}`) }}
        <span v-if="!modelValue?.[lang]" class="missing-dot" aria-hidden="true" title="missing" />
      </button>
    </div>

    <p v-if="!hasActiveValue" class="missing">
      {{ fallbackText }}
      <span class="missing-badge">{{ $t('km.missingTranslation', { language: $t(`languages.${active}`) }) }}</span>
    </p>

    <textarea
      v-if="multiline"
      class="lang-input"
      :value="modelValue?.[active] ?? ''"
      :disabled="disabled"
      :placeholder="fallbackText ?? ''"
      rows="2"
      @change="onChange"
    />
    <input
      v-else
      type="text"
      class="lang-input"
      :value="modelValue?.[active] ?? ''"
      :disabled="disabled"
      :placeholder="fallbackText ?? ''"
      @change="onChange"
    />
  </div>
</template>

<script lang="ts" setup>
import { computed, ref } from 'vue'
import { resolveLang } from '@/lib/lang'
import { SUPPORTED_LANGUAGES } from '@/lib/kmContent'
import type { LangMap } from '@/types/api'

/**
 * Language tabs (en / pt-PT / pt-BR) over one translatable field
 * (`question.text` or `question.help`, spec 04 §5). The tab dot marks a
 * missing language; the active tab, if missing, shows the `en ⇄
 * pt-PT/pt-BR` fallback text greyed out with the `missing` class and
 * `km.missingTranslation`, per spec 04 §2's "missing translations
 * are never blocked" rule.
 */
const props = defineProps<{
  modelValue: LangMap | null | undefined
  multiline?: boolean
  disabled?: boolean
  defaultLang?: string
}>()

const emit = defineEmits<{ change: [lang: string, value: string] }>()

const LANGUAGES = SUPPORTED_LANGUAGES

const active = ref<string>(props.defaultLang ?? 'en')

const hasActiveValue = computed(() => {
  const value = props.modelValue?.[active.value]
  return typeof value === 'string' && value !== ''
})

const fallbackText = computed(() => resolveLang(props.modelValue, active.value))

function onChange(event: Event) {
  const value = (event.target as HTMLInputElement | HTMLTextAreaElement).value
  // `en` may never be deleted (spec §2) — a blanked `en` field is simply
  // not committed, reverting to its previous value on the next render.
  if (active.value === 'en' && value === '') return
  emit('change', active.value, value)
}
</script>

<style scoped>
.km-lang-tabs {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.tabs {
  display: flex;
  gap: 0.35rem;
  flex-wrap: wrap;
}

.tab {
  min-height: 44px;
  padding: 0.3rem 0.7rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
}

.tab.active {
  border-color: var(--color-primary);
  color: var(--color-primary);
  font-weight: var(--font-weight-medium);
}

.missing-dot {
  width: 0.4rem;
  height: 0.4rem;
  border-radius: 50%;
  background-color: var(--color-status-planned);
  display: inline-block;
}

.missing {
  margin: 0;
  padding: 0.4rem 0.6rem;
  border-radius: var(--border-radius-sm);
  background-color: var(--color-hover);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  font-style: italic;
}

.missing-badge {
  display: inline-block;
  margin-left: 0.5rem;
  padding: 0.05rem 0.4rem;
  border-radius: 999px;
  background-color: var(--color-status-planned);
  color: #ffffff;
  font-size: var(--font-size-xs);
  font-style: normal;
}

.lang-input {
  min-height: 44px;
  padding: 0.5rem 0.6rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
  font-family: inherit;
  font-size: var(--font-size-sm);
  width: 100%;
}

textarea.lang-input {
  resize: vertical;
}
</style>
