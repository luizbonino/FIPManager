<template>
  <div class="language-switcher">
    <select v-model="currentLocale" @change="changeLanguage" class="language-select">
      <option v-for="locale in locales" :key="locale" :value="locale">
        {{ $t(`languages.${locale}`) }}
      </option>
    </select>
  </div>
</template>

<script lang="ts" setup>
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { SUPPORTED_LOCALES, type Locale } from '@/i18n'

// Extracted verbatim from App.vue (spec 02 §6.3): no props; reads/writes
// localStorage['fip-language'] and emits 'changed' so a parent view (e.g.
// FipEditor, which also needs to mark the FIP dirty) can react.
const emit = defineEmits<{ changed: [locale: Locale] }>()

const { locale } = useI18n()

const currentLocale = ref<Locale>(locale.value as Locale)
const locales = SUPPORTED_LOCALES

watch(locale, (newLocale) => {
  currentLocale.value = newLocale as Locale
})

const changeLanguage = () => {
  locale.value = currentLocale.value
  try {
    localStorage.setItem('fip-language', currentLocale.value)
  } catch {
    // Private-mode Safari or storage disabled; the in-memory locale still works.
  }
  emit('changed', currentLocale.value)
}
</script>

<style scoped>
.language-switcher {
  display: flex;
  align-items: center;
}

.language-select {
  padding: 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background-color: var(--color-background);
  color: var(--color-text);
  cursor: pointer;
  font-size: 1rem;
}

.language-select:hover,
.language-select:focus {
  outline: none;
  border-color: var(--color-primary);
}
</style>
