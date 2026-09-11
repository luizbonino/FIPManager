<template>
  <div class="guide-view">
    <nav class="guide-switcher">
      <router-link to="/guide" class="guide-switch-link" :class="{ active: guideId === 'participant' }">
        {{ $t('guide.participantLabel') }}
      </router-link>
      <router-link to="/guide/admin" class="guide-switch-link" :class="{ active: guideId === 'administrator' }">
        {{ $t('guide.administratorLabel') }}
      </router-link>
    </nav>

    <div v-if="loading" class="loading">
      <p>{{ $t('common.loading') }}</p>
    </div>

    <div v-else-if="notFound" class="message-box">
      <p>{{ $t('common.notFound') }}</p>
    </div>

    <template v-else-if="guide">
      <p v-if="fallbackNotice" class="fallback-notice">{{ fallbackNotice }}</p>
      <!-- eslint-disable-next-line vue/no-v-html -- `renderedHtml` is escape-first (lib/markdown.ts); no raw HTML ever passes through. -->
      <div ref="contentRef" class="markdown-body" v-html="renderedHtml"></div>
    </template>
  </div>
</template>

<script lang="ts" setup>
import { computed, nextTick, onMounted, ref, watch, watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { getGuide, type GuideOut } from '@/api/guides'
import { renderMarkdown } from '@/lib/markdown'

interface Props {
  guideId: 'participant' | 'administrator'
}

const props = defineProps<Props>()

const { locale, t } = useI18n()
const route = useRoute()

const loading = ref(true)
const notFound = ref(false)
const guide = ref<GuideOut | null>(null)
const contentRef = ref<HTMLElement | null>(null)

const title = computed(() =>
  props.guideId === 'participant' ? t('guide.participantTitle') : t('guide.administratorTitle')
)

// The markdown itself opens with a translated `# ...` H1 that always matches
// the content (unlike a separately maintained visible heading, which would
// drift and, worse, duplicate it -- see docs/specs, the in-app guide viewer
// review). Use the i18n title for the browser tab instead of a second
// on-page heading.
watchEffect(() => {
  document.title = `${title.value} · FIP Manager`
})

const renderedHtml = computed(() => (guide.value ? renderMarkdown(guide.value.markdown) : ''))

// Guides ship in fewer languages than the UI (spec: en/pt-PT/pt-BR/es);
// `guide.language` is what the API actually served after its own
// pt-PT <-> pt-BR -> en fallback, which may not be the interface locale.
const fallbackNotice = computed(() => {
  if (!guide.value || guide.value.language === locale.value) return null
  return t('guide.languageFallback', { language: t(`languages.${guide.value.language}`) })
})

/**
 * The guides carry their own GitHub-style "Table of contents" section
 * (`[Step 1](#step-1--...)`), but `renderMarkdown` emits headings with no
 * `id` (spec 05's privacy notice never needed one). Assign ids here, off
 * the rendered heading text, using the same slug algorithm the guide
 * authors wrote their links against -- the GitHub/GFM scheme: lowercase;
 * strip everything but letters, numbers, spaces and hyphens (accents are
 * kept, e.g. "à"/"é"/"ã"/"ç" -- most non-English headings are accented);
 * spaces -> hyphens; de-duplicate. `\w` is ASCII-only in JS, so a plain
 * `[^\w\- ]` filter used to strip every accented character and break the
 * guides' own hand-written TOC anchors in pt-PT/pt-BR/es; `\p{L}\p{N}`
 * (with the `u` flag) is Unicode-aware and keeps them.
 * Plain `<a href="#...">` tags are never intercepted by vue-router (only
 * `<router-link>` is), so once the ids exist the browser's native
 * same-page scroll handles the rest.
 */
function slugify(text: string, seen: Map<string, number>): string {
  const base = text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\- ]/gu, '')
    .replace(/ /g, '-')
  const count = seen.get(base) ?? 0
  seen.set(base, count + 1)
  return count === 0 ? base : `${base}-${count}`
}

async function assignHeadingIdsAndScroll() {
  await nextTick()
  const container = contentRef.value
  if (!container) return
  const seen = new Map<string, number>()
  container.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach((heading) => {
    heading.id = slugify(heading.textContent ?? '', seen)
  })
  const hash = route.hash?.replace(/^#/, '')
  if (hash) {
    document.getElementById(hash)?.scrollIntoView({ block: 'start' })
  }
}

async function load() {
  loading.value = true
  notFound.value = false
  try {
    guide.value = await getGuide(props.guideId, locale.value)
    loading.value = false
    await assignHeadingIdsAndScroll()
  } catch {
    notFound.value = true
    loading.value = false
  }
}

onMounted(load)
watch(locale, load)
watch(() => props.guideId, load)
</script>

<style scoped>
.guide-view {
  max-width: 840px;
  margin: 0 auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.guide-switcher {
  display: flex;
  gap: 0.5rem;
}

.guide-switch-link {
  padding: 0.5rem 0.75rem;
  border-radius: var(--border-radius-sm);
  text-decoration: none;
  color: var(--color-text);
  background-color: var(--color-hover);
}

.guide-switch-link.active {
  background-color: var(--color-primary);
  color: var(--color-primary-text);
}

.loading,
.message-box {
  text-align: center;
  padding: 3rem 1rem;
}

.fallback-notice {
  margin: 0;
  padding: 0.75rem 1rem;
  border-radius: var(--border-radius-sm);
  background-color: var(--color-hover);
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
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  color: var(--color-primary);
  margin: 0.5rem 0 0;
  /* Clear the app's sticky header when an in-page anchor scrolls a
     heading to the top of the viewport. */
  scroll-margin-top: 4.5rem;
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

.markdown-body :deep(blockquote) {
  margin: 0;
  padding: 0.5rem 1rem;
  border-left: 3px solid var(--color-border);
  color: var(--color-text-secondary);
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--color-border);
  padding: 0.4rem 0.6rem;
  text-align: left;
}

.markdown-body :deep(pre) {
  overflow-x: auto;
  background-color: var(--color-hover);
  padding: 0.75rem;
  border-radius: var(--border-radius-sm);
}

.markdown-body :deep(img) {
  max-width: 100%;
}
</style>
