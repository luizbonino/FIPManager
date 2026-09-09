<template>
  <div class="session-fip-list">
    <p v-if="reconnecting" class="reconnecting no-print">
      <span class="dot" aria-hidden="true" />
      {{ $t('sessionAdmin.reconnecting') }}
    </p>
    <p v-if="sorted.length === 0" class="empty-state">{{ $t('sessionAdmin.noFips') }}</p>
    <ul v-else class="fip-rows">
      <li v-for="fip in sorted" :key="fip.id" class="fip-row">
        <div class="fip-row-main">
          <span class="fip-name">{{ displayName(fip) }}</span>
          <span v-if="areaLabelOf(fip)" class="area-chip">{{ areaLabelOf(fip) }}</span>
          <span class="visibility-chip">{{ $t(`visibility.${fip.visibility}`) }}</span>
        </div>
        <span class="progress-wrap">
          <ProgressBar :answered="answeredCount(fip.answers)" :total="totalFor(fip)" />
        </span>
        <span class="updated">{{ $t('sessionAdmin.lastUpdate') }}: {{ relativeTime(fip.updatedAt) }}</span>
        <span class="row-links">
          <router-link :to="`/fips/${fip.id}`" class="view-link">{{ $t('common.view') }}</router-link>
          <router-link v-if="canOpen" :to="`/fips/${fip.id}/edit`" class="open-link">{{ $t('sessionAdmin.open') }}</router-link>
        </span>
      </li>
    </ul>
  </div>
</template>

<script lang="ts" setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { getKnowledgeModel } from '@/api/knowledgeModels'
import { resolveLang } from '@/lib/lang'
import { visibleQuestionCount, TOTAL_QUESTIONS, answeredCount } from '@/lib/progress'
import ProgressBar from './ProgressBar.vue'
import type { FipOut } from '@/types/api'

const { locale } = useI18n()

/**
 * `GET /api/sessions/{id}/fips` rendering (spec 02 §4.2, extended by spec 08
 * §3.2): display name, an area-label chip (multi-ref sessions only), a
 * per-FIP `answered / N` bar — `N` is that FIP's own model's visible
 * question count, fetched once per distinct `id@version` and cached, so a
 * multi-questionnaire session doesn't show every FIP against a hardcoded 21
 * — `updatedAt` as relative time, visibility, View link; sorted by `createdAt`.
 */
const props = defineProps<{ fips: FipOut[]; reconnecting?: boolean; canOpen?: boolean }>()

const sorted = computed(() => [...props.fips].sort((a, b) => a.createdAt.localeCompare(b.createdAt)))

function displayName(fip: FipOut): string {
  return fip.community?.name || fip.id
}

function areaLabelOf(fip: FipOut): string | null {
  return fip.areaLabel ? resolveLang(fip.areaLabel, locale.value) : null
}

// refKey -> visible question count, fetched lazily and kept for the
// component's lifetime — a session's questionnaire refs don't change under
// a running list.
const questionCounts = ref<Record<string, number>>({})
const pendingRefKeys = new Set<string>()

function refKeyOf(fip: FipOut): string {
  return `${fip.questionnaireId}@${fip.questionnaireVersion}`
}

function totalFor(fip: FipOut): number {
  return questionCounts.value[refKeyOf(fip)] ?? TOTAL_QUESTIONS
}

async function ensureQuestionCount(fip: FipOut): Promise<void> {
  const key = refKeyOf(fip)
  if (key in questionCounts.value || pendingRefKeys.has(key)) return
  pendingRefKeys.add(key)
  try {
    const km = await getKnowledgeModel(fip.questionnaireId, fip.questionnaireVersion)
    questionCounts.value = { ...questionCounts.value, [key]: visibleQuestionCount(km) }
  } catch {
    // Leave it out of the cache — `totalFor` falls back to TOTAL_QUESTIONS.
  } finally {
    pendingRefKeys.delete(key)
  }
}

watch(
  () => props.fips,
  (fips) => {
    for (const fip of fips) void ensureQuestionCount(fip)
  },
  { immediate: true }
)

// `Intl.RelativeTimeFormat` covers localisation natively for en/pt-PT/pt-BR
// (spec 02 §4.2's "relative time"), so no extra i18n strings are needed.
function relativeTime(iso: string): string {
  const diffMs = new Date(iso).getTime() - Date.now()
  const rtf = new Intl.RelativeTimeFormat(locale.value, { numeric: 'auto' })
  const diffMin = Math.round(diffMs / 60000)
  if (Math.abs(diffMin) < 60) return rtf.format(diffMin, 'minute')
  const diffH = Math.round(diffMin / 60)
  if (Math.abs(diffH) < 24) return rtf.format(diffH, 'hour')
  const diffD = Math.round(diffH / 24)
  return rtf.format(diffD, 'day')
}
</script>

<style scoped>
.reconnecting {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.reconnecting .dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background-color: var(--color-status-planned);
}

.empty-state {
  color: var(--color-text-secondary);
  padding: 1rem 0;
}

.fip-rows {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

/*
 * Bug fix: a fixed `2fr 1fr auto auto` grid let the progress bar's
 * nowrap text ("N of 21 questions answered") overflow its 1fr track and
 * paint over "Last update: …" once the row narrowed (e.g. at 1280px next
 * to a sidebar). Flex-wrap instead: each section carries its own
 * min-width, so a too-narrow row wraps sections onto new lines rather
 * than letting text overlap — and at very narrow widths (375px) every
 * section ends up on its own line, i.e. fully stacked.
 */
.fip-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem 1rem;
  padding: 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
}

.fip-row-main {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  flex: 1 1 220px;
  min-width: 200px;
}

.progress-wrap {
  flex: 1 1 220px;
  min-width: 200px;
}

.fip-name {
  font-weight: var(--font-weight-medium);
}

.visibility-chip {
  font-size: var(--font-size-xs);
  color: var(--color-chip-text);
  background-color: var(--color-chip-bg);
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
}

.area-chip {
  font-size: var(--font-size-xs);
  color: var(--color-primary-text);
  background-color: var(--color-primary);
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
}

.updated {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  flex: 0 1 auto;
  white-space: nowrap;
}

.row-links {
  display: flex;
  gap: 0.75rem;
  flex: 0 0 auto;
  margin-left: auto;
}

.view-link,
.open-link {
  align-self: start;
  min-height: 44px;
  display: inline-flex;
  align-items: center;
}
</style>
