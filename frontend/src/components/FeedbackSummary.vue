<template>
  <div class="feedback-summary no-print">
    <h2>{{ $t('feedback.summaryTitle') }}</h2>

    <p v-if="!summary || summary.responses === 0" class="empty-state">{{ $t('feedback.noResponses') }}</p>

    <template v-else>
      <p class="responses-count">{{ $t('feedback.responses', { count: summary.responses }) }}</p>

      <div v-for="q in summary.questions" :key="q.key" class="question-summary">
        <h3>{{ $t(`feedback.${q.key}`) }}</h3>
        <p v-if="q.mean !== null" class="mean">{{ $t('feedback.mean', { mean: q.mean }) }}</p>
        <div class="bar-row">
          <div v-for="score in SCORES" :key="score" class="bar-item">
            <span class="bar-score">{{ score }}</span>
            <div class="bar-track">
              <div class="bar-fill" :style="{ width: barWidth(q, score) + '%' }"></div>
            </div>
            <span class="bar-count">{{ q.counts[String(score)] ?? 0 }}</span>
          </div>
        </div>
      </div>

      <div v-if="summary.comments.length > 0" class="comments">
        <h3>{{ $t('feedback.comments') }}</h3>
        <ul>
          <li v-for="(c, i) in summary.comments" :key="i">{{ c.text }}</li>
        </ul>
      </div>
    </template>

    <a class="export-link" :href="csvUrl">{{ $t('feedback.exportCsv') }}</a>
  </div>
</template>

<script lang="ts" setup>
import { onMounted, ref } from 'vue'
import { getSessionFeedback, sessionFeedbackCsvUrl } from '@/api/feedback'
import type { FeedbackSummary as FeedbackSummaryType } from '@/api/feedback'

/** Facilitator aggregate view (spec 05 §4): `SessionDetail.vue` only, owner/admin only. */
const props = defineProps<{ sessionId: string }>()

const summary = ref<FeedbackSummaryType | null>(null)
const csvUrl = sessionFeedbackCsvUrl(props.sessionId)
const SCORES = [1, 2, 3, 4, 5]

function barWidth(q: FeedbackSummaryType['questions'][number], score: number): number {
  const total = Object.values(q.counts).reduce((a, b) => a + b, 0)
  if (total === 0) return 0
  return ((q.counts[String(score)] ?? 0) / total) * 100
}

onMounted(async () => {
  try {
    summary.value = await getSessionFeedback(props.sessionId)
  } catch {
    summary.value = null
  }
})
</script>

<style scoped>
.feedback-summary {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.feedback-summary h2 {
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 0.4rem;
}

.empty-state {
  color: var(--color-text-secondary);
}

.responses-count {
  margin: 0;
  font-weight: var(--font-weight-medium);
}

.question-summary {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.question-summary h3 {
  margin: 0;
  font-size: var(--font-size-md);
}

.mean {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.bar-row {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.bar-item {
  display: grid;
  grid-template-columns: 1rem 1fr 2rem;
  align-items: center;
  gap: 0.4rem;
  font-size: var(--font-size-xs);
}

.bar-track {
  height: 0.6rem;
  background-color: var(--color-hover);
  border-radius: 999px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background-color: var(--color-primary);
}

.bar-count {
  text-align: right;
  color: var(--color-text-secondary);
}

.comments ul {
  margin: 0;
  padding-left: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  font-size: var(--font-size-sm);
}

.export-link {
  align-self: flex-start;
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  padding: 0.4rem 0.9rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
}
</style>
