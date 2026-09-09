<template>
  <details v-if="!hidden" class="feedback-form no-print">
    <summary>{{ $t('feedback.title') }}</summary>
    <div class="feedback-body">
      <p class="feedback-intro">{{ $t('feedback.intro') }}</p>

      <template v-if="!submitted">
        <fieldset v-for="q in QUESTIONS" :key="q" class="likert">
          <legend>{{ $t(`feedback.${q}`) }}</legend>
          <div class="likert-scale">
            <span class="scale-label">{{ $t('feedback.scaleLow') }}</span>
            <label v-for="n in 5" :key="n" class="likert-option">
              <input v-model.number="answers[q]" type="radio" :name="`${q}-${uid}`" :value="n" />
              <span>{{ n }}</span>
            </label>
            <span class="scale-label">{{ $t('feedback.scaleHigh') }}</span>
          </div>
        </fieldset>

        <label class="comment-field">
          <span>{{ $t('feedback.comment') }}</span>
          <textarea v-model="comment" rows="3" maxlength="2000"></textarea>
        </label>

        <p v-if="error" class="form-error">{{ $t('feedback.error') }}</p>

        <button type="button" class="btn btn-primary" :disabled="!canSubmit || submitting" @click="onSubmit">
          {{ $t('feedback.submit') }}
        </button>
      </template>

      <p v-else class="thanks">{{ $t('feedback.thanks') }}</p>
    </div>
  </details>
</template>

<script lang="ts" setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ApiResponseError, get } from '@/api/client'
import { postFeedback } from '@/api/feedback'

/**
 * spec 05 §4: anonymous 3-question Likert + free-text form. Posts once per
 * browser (a `localStorage` flag keyed by `sessionId ?? fipId ?? 'global'`)
 * and stays hidden on that device afterwards; a `403 feedback_disabled`
 * hides it entirely, matching a `feedbackEnabled: false` health flag when
 * one is present.
 */
const props = defineProps<{ sessionId?: string; fipId?: string }>()

const { locale } = useI18n()

const QUESTIONS = ['q1', 'q2', 'q3'] as const
type QuestionKey = (typeof QUESTIONS)[number]

let uidCounter = 0
const uid = ++uidCounter

const answers = reactive<Record<QuestionKey, number | null>>({ q1: null, q2: null, q3: null })
const comment = ref('')
const submitting = ref(false)
const submitted = ref(false)
const error = ref(false)
/** Set on a `403 feedback_disabled` response, or a `feedbackEnabled: false` health flag. */
const disabled = ref(false)

const storageKey = computed(() => `fipm.feedback.${props.sessionId ?? props.fipId ?? 'global'}`)
const hidden = computed(() => disabled.value)

function alreadyDone(): boolean {
  try {
    return localStorage.getItem(storageKey.value) === 'done'
  } catch {
    return false
  }
}

const canSubmit = computed(() => answers.q1 !== null && answers.q2 !== null && answers.q3 !== null)

async function onSubmit() {
  if (!canSubmit.value) return
  submitting.value = true
  error.value = false
  try {
    await postFeedback({
      q1: answers.q1!,
      q2: answers.q2!,
      q3: answers.q3!,
      comment: comment.value || undefined,
      sessionId: props.sessionId,
      fipId: props.fipId,
      language: locale.value,
    })
    try {
      localStorage.setItem(storageKey.value, 'done')
    } catch {
      // Best effort only — worst case the form reappears next visit.
    }
    submitted.value = true
  } catch (err) {
    if (err instanceof ApiResponseError && err.status === 403) {
      disabled.value = true
    } else {
      error.value = true
    }
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  if (alreadyDone()) {
    submitted.value = true
    return
  }
  try {
    const health = await get<Record<string, unknown>>('/health')
    if (health.feedbackEnabled === false) {
      disabled.value = true
    }
  } catch {
    // The health check is best-effort only — assume feedback is enabled;
    // an actual 403 on submit still hides the form.
  }
})
</script>

<style scoped>
.feedback-form {
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  padding: 0;
}

.feedback-form > summary {
  cursor: pointer;
  min-height: 44px;
  display: flex;
  align-items: center;
  padding: 0.75rem 1rem;
  background-color: var(--color-hover);
  font-weight: var(--font-weight-medium);
}

.feedback-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1rem;
}

.feedback-intro {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}

.likert {
  border: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.likert legend {
  padding: 0;
  font-weight: var(--font-weight-medium);
  font-size: var(--font-size-sm);
}

.likert-scale {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.scale-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.likert-option {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  min-height: 44px;
  padding: 0 0.3rem;
}

.comment-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: var(--font-size-sm);
}

.comment-field textarea {
  padding: 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
  font-family: inherit;
  resize: vertical;
}

.form-error {
  margin: 0;
  color: var(--color-error);
  font-size: var(--font-size-sm);
}

.thanks {
  margin: 0;
  color: var(--color-success);
}

.btn {
  align-self: flex-start;
  min-height: 44px;
  padding: 0.5rem 1.2rem;
  border: none;
  border-radius: var(--border-radius-sm);
  cursor: pointer;
}

.btn-primary {
  background-color: var(--color-primary);
  color: var(--color-primary-text);
}
</style>
