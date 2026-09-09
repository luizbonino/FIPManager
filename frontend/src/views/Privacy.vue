<template>
  <div class="privacy-view">
    <div v-if="loading" class="loading">
      <p>{{ $t('common.loading') }}</p>
    </div>

    <div v-else-if="notFound" class="message-box">
      <p>{{ $t('common.notFound') }}</p>
    </div>

    <template v-else-if="notice">
      <h1>{{ $t('privacy.title') }}</h1>
      <p class="version">{{ $t('privacy.version', { version: notice.version, date: notice.date }) }}</p>
      <!-- eslint-disable-next-line vue/no-v-html -- `renderedHtml` is escape-first (lib/markdown.ts); no raw HTML ever passes through. -->
      <div class="markdown-body" v-html="renderedHtml"></div>
    </template>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { get } from '@/api/client'
import { getPrivacyNotice, type PrivacyNotice } from '@/api/privacy'
import { renderMarkdown } from '@/lib/markdown'

// spec 05 §2: public route, current locale, re-renders on a language switch.
const { locale } = useI18n()

const loading = ref(true)
const notFound = ref(false)
const notice = ref<PrivacyNotice | null>(null)

const renderedHtml = computed(() => (notice.value ? renderMarkdown(notice.value.markdown) : ''))

/**
 * `{{CONTACT_EMAIL}}`/`{{HOSTING_ORG}}` substitution (task brief): neither
 * `GET /api/health` nor any other spec-defined endpoint currently exposes
 * these values, and the shipped `data/i18n/privacy/en.md` draft (spec 05
 * §2.1) writes the contact address out in full rather than using a
 * placeholder. This is therefore a no-op today — kept only so a future
 * placeholder in the notice text resolves automatically once (if ever)
 * `/api/health` grows those fields, instead of staying silently broken.
 */
async function substitutePlaceholders(markdown: string): Promise<string> {
  if (!markdown.includes('{{CONTACT_EMAIL}}') && !markdown.includes('{{HOSTING_ORG}}')) return markdown
  try {
    const health = await get<Record<string, unknown>>('/health')
    let result = markdown
    if (typeof health.contactEmail === 'string') {
      result = result.replaceAll('{{CONTACT_EMAIL}}', health.contactEmail)
    }
    if (typeof health.hostingOrg === 'string') {
      result = result.replaceAll('{{HOSTING_ORG}}', health.hostingOrg)
    }
    return result
  } catch {
    return markdown
  }
}

async function load() {
  loading.value = true
  notFound.value = false
  try {
    const raw = await getPrivacyNotice(locale.value)
    notice.value = { ...raw, markdown: await substitutePlaceholders(raw.markdown) }
  } catch {
    notFound.value = true
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(locale, load)
</script>

<style scoped>
.privacy-view {
  max-width: 720px;
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

h1 {
  margin: 0;
  color: var(--color-primary);
}

.version {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}

.markdown-body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  line-height: var(--line-height);
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  color: var(--color-primary);
  margin: 0.5rem 0 0;
}

.markdown-body :deep(p) {
  margin: 0;
}

.markdown-body :deep(ul) {
  margin: 0;
  padding-left: 1.25rem;
}

.markdown-body :deep(a) {
  color: var(--color-link);
}

.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--color-border);
  margin: 0.5rem 0;
}
</style>
