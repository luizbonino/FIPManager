<template>
  <div class="question-card" :id="question.id">
    <div class="question-head">
      <span class="question-id">{{ question.id }}</span>
      <span v-if="ferTypeLabel" class="question-fer-chip">{{ ferTypeLabel }}</span>
    </div>
    <p class="question-text">{{ resolvedText }}</p>

    <details v-if="resolvedHelp" class="question-help">
      <summary>{{ $t('editor.help') }}</summary>
      <p>{{ resolvedHelp }}</p>
    </details>

    <div class="declarations">
      <DeclarationEditor
        v-for="(declaration, index) in declarations"
        :key="index"
        :question-id="question.id"
        :index="index"
        :declaration="declaration"
        :options="ferOptions"
        @remove="onRemove(index)"
      />
    </div>

    <button
      v-if="!readOnly && canAddMore"
      type="button"
      class="add-declaration-btn"
      @click="onAdd"
    >
      {{ $t('editor.addDeclaration') }}
    </button>

    <label class="comment-field">
      <span>{{ $t('editor.comment') }}</span>
      <textarea
        :value="answer?.comment ?? ''"
        rows="2"
        :disabled="readOnly"
        @change="onCommentChange"
      />
    </label>
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFipEditorStore } from '@/stores/fipEditor'
import { resolveLang } from '@/lib/lang'
import DeclarationEditor from './DeclarationEditor.vue'
import type { FerOut, KnowledgeModelQuestion } from '@/types/api'

/**
 * One question of a section panel (spec 02 §2.2): id badge, resolved text,
 * FER-type chip, collapsible Help, 0..n `DeclarationEditor` rows, an "Add
 * declaration" button (hidden once `allowMultiple` is false and one
 * declaration exists), and an optional comment.
 */
const props = defineProps<{
  question: KnowledgeModelQuestion
  ferTypeLabel: string | null
}>()

const store = useFipEditorStore()
const { locale } = useI18n()

const readOnly = computed(() => store.readOnly)

const answer = computed(() => store.fip?.answers.find((a) => a.questionId === props.question.id))
const declarations = computed(() => answer.value?.declarations ?? [])

const canAddMore = computed(() => props.question.allowMultiple || declarations.value.length === 0)

const resolvedText = computed(() => resolveLang(props.question.text, locale.value) ?? props.question.id)
const resolvedHelp = computed(() => resolveLang(props.question.help, locale.value))

const ferOptions = computed<FerOut[]>(() => {
  const type = props.question.ferType
  if (!type) return []
  return Object.values(store.fers).filter((f) => f.type === type)
})

function onAdd() {
  store.addDeclaration(props.question.id, { status: 'current' })
}

function onRemove(index: number) {
  store.removeDeclaration(props.question.id, index)
}

function onCommentChange(event: Event) {
  const value = (event.target as HTMLTextAreaElement).value
  store.setComment(props.question.id, value || null)
}
</script>

<style scoped>
.question-card {
  padding: 1rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  background-color: var(--color-background);
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  scroll-margin-top: 5rem;
}

.question-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.question-id {
  font-family: monospace;
  font-size: var(--font-size-xs);
  /* Explicit chip fg/bg pair (not --color-secondary/--color-text-secondary):
     --color-secondary is overridden to a mid-tone slate by index.html's
     inline :root block, which paired with the muted gray text made this
     chip unreadable. --color-id-chip-* is dedicated to this chip only. */
  color: var(--color-id-chip-text);
  background-color: var(--color-id-chip-bg);
  padding: 0.15rem 0.4rem;
  border-radius: var(--border-radius-sm);
}

.question-fer-chip {
  font-size: var(--font-size-xs);
  color: var(--color-chip-text);
  background-color: var(--color-chip-bg);
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
}

.question-text {
  margin: 0;
  font-weight: var(--font-weight-medium);
}

.question-help summary {
  cursor: pointer;
  color: var(--color-link);
  font-size: var(--font-size-sm);
  min-height: 44px;
  display: flex;
  align-items: center;
}

.question-help p {
  margin: 0.25rem 0 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.declarations {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.add-declaration-btn {
  align-self: flex-start;
  min-height: 44px;
  padding: 0.4rem 0.9rem;
  border: 1px solid var(--color-primary);
  border-radius: var(--border-radius-sm);
  background: none;
  color: var(--color-primary);
  font-size: var(--font-size-sm);
}

.comment-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.comment-field textarea {
  padding: 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
  font-family: inherit;
  font-size: var(--font-size-sm);
  resize: vertical;
}
</style>
