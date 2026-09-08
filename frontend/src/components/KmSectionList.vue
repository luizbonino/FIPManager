<template>
  <div class="km-section-list">
    <div class="list-actions no-print">
      <button type="button" class="btn btn-secondary" :disabled="readOnly" @click="onAddSection">
        {{ $t('km.addSection') }}
      </button>
    </div>

    <details
      v-for="(section, index) in sections"
      :key="section.id"
      class="section"
      :open="section.id === openSectionId"
      @toggle="onToggle(section.id, $event)"
    >
      <summary class="section-summary">
        <span class="section-title">{{ resolveLang(section.title, locale) ?? section.id }}</span>
        <span class="section-count">{{ $t('km.questions', { count: section.questions.length }) }}</span>
        <div class="summary-actions no-print" @click.stop @keydown.stop>
          <MoveButtons
            :can-up="index > 0"
            :can-down="index < sections.length - 1"
            @up="applyOp((c) => moveSection(c, section.id, 'up'))"
            @down="applyOp((c) => moveSection(c, section.id, 'down'))"
          />
          <button type="button" class="ghost-btn danger" :disabled="readOnly" @click="onDeleteSection(section.id)">
            {{ $t('km.deleteQuestion') }}
          </button>
        </div>
      </summary>

      <div class="section-body">
        <KmLangTabs
          class="section-title-tabs"
          :model-value="section.title"
          :default-lang="locale"
          :disabled="readOnly"
          @change="(lang, value) => applyOp((c) => setText(c, { field: 'sectionTitle', sectionId: section.id }, lang, value))"
        />

        <KmQuestionCard
          v-for="(question, qIndex) in section.questions"
          :key="question.id"
          :question="question"
          :can-move-up="qIndex > 0"
          :can-move-down="qIndex < section.questions.length - 1"
          :fer-type-options="ferTypeOptions"
          :read-only="readOnly"
          @move-up="applyOp((c) => moveQuestion(c, question.id, 'up'))"
          @move-down="applyOp((c) => moveQuestion(c, question.id, 'down'))"
          @hide="applyOp((c) => hideQuestion(c, question.id))"
          @unhide="applyOp((c) => unhideQuestion(c, question.id))"
          @split="onSplit(question.id)"
          @delete="applyOp((c) => deleteQuestion(c, question.id))"
          @update-text="(lang, value) => applyOp((c) => setText(c, { field: 'questionText', questionId: question.id }, lang, value))"
          @update-help="(lang, value) => applyOp((c) => setText(c, { field: 'questionHelp', questionId: question.id }, lang, value))"
          @update-principle="(value) => applyOp((c) => setPrinciple(c, question.id, value))"
          @update-scope="(value) => applyOp((c) => setScope(c, question.id, value))"
          @update-fer-type="(value) => applyOp((c) => setFerType(c, question.id, value))"
          @update-required="(value) => applyOp((c) => setRequired(c, question.id, value))"
          @update-allow-multiple="(value) => applyOp((c) => setAllowMultiple(c, question.id, value))"
        />

        <button type="button" class="btn btn-secondary no-print" :disabled="readOnly" @click="onAddQuestion(section.id)">
          {{ $t('km.addQuestion') }}
        </button>
      </div>
    </details>
  </div>
</template>

<script lang="ts" setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { resolveLang } from '@/lib/lang'
import { useKmEditorStore } from '@/stores/kmEditor'
import {
  addQuestion,
  addSection,
  deleteQuestion,
  deleteSection,
  hideQuestion,
  moveQuestion,
  moveSection,
  setFerType,
  setText,
  splitQuestion,
  unhideQuestion,
  type KmContentOpError,
} from '@/lib/kmContent'
import KmQuestionCard from './KmQuestionCard.vue'
import KmLangTabs from './KmLangTabs.vue'
import MoveButtons from './MoveButtons.vue'
import type { FerType, KnowledgeModelContent, KnowledgeModelQuestion, KnowledgeModelSection } from '@/types/api'

/**
 * The sections accordion (spec 04 §5): one open section at a time, each
 * head showing title, question count, up/down and delete; inside, the
 * section-title language tabs, one `KmQuestionCard` per question and an
 * "Add question" control. Reads/writes the `kmEditor` store directly
 * (matching `QuestionCard.vue`'s established pattern for `fipEditor`).
 */
const props = defineProps<{
  sections: KnowledgeModelSection[]
  ferTypeOptions: FerType[]
  readOnly?: boolean
}>()

const { locale, t } = useI18n()
const store = useKmEditorStore()

// One section open at a time (spec §5); the first section opens by
// default (mirroring `FipEditor.vue`'s accordion), the props are already
// populated when this component mounts (its parent gates rendering on
// `store.content` being loaded).
const openSectionId = ref<string | null>(props.sections[0]?.id ?? null)

function onToggle(sectionId: string, event: Event) {
  const details = event.target as HTMLDetailsElement
  if (details.open) {
    openSectionId.value = sectionId
  } else if (openSectionId.value === sectionId) {
    openSectionId.value = null
  }
}

/** A failed op (e.g. a duplicate id from `addQuestion`/`addSection`) leaves `content` untouched. */
function applyOp(op: (content: KnowledgeModelContent) => KnowledgeModelContent) {
  try {
    store.apply(op)
  } catch (err) {
    if ((err as KmContentOpError)?.code) alert(t('km.idTaken'))
  }
}

// --- small per-field setters kept local: `lib/kmContent.ts` only exposes
// `setFerType` as a dedicated op (spec §5's named op list); principle,
// scope, required and allowMultiple are simple field replacements that
// don't warrant their own named pure function each.
function setPrinciple(content: KnowledgeModelContent, questionId: string, value: string | null): KnowledgeModelContent {
  return mapQuestion(content, questionId, (q) => ({ ...q, principle: value }))
}
function setScope(
  content: KnowledgeModelContent,
  questionId: string,
  value: 'metadata' | 'data' | null
): KnowledgeModelContent {
  return mapQuestion(content, questionId, (q) => ({ ...q, scope: value }))
}
function setRequired(content: KnowledgeModelContent, questionId: string, value: boolean): KnowledgeModelContent {
  return mapQuestion(content, questionId, (q) => ({ ...q, required: value }))
}
function setAllowMultiple(content: KnowledgeModelContent, questionId: string, value: boolean): KnowledgeModelContent {
  return mapQuestion(content, questionId, (q) => ({ ...q, allowMultiple: value }))
}
function mapQuestion(
  content: KnowledgeModelContent,
  questionId: string,
  fn: (q: KnowledgeModelQuestion) => KnowledgeModelQuestion
): KnowledgeModelContent {
  return {
    ...content,
    sections: content.sections.map((section) => ({
      ...section,
      questions: section.questions.map((q) => (q.id === questionId ? fn(q) : q)),
    })),
  }
}

function onSplit(questionId: string) {
  try {
    store.apply((c) => splitQuestion(c, questionId))
  } catch (err) {
    const code = (err as KmContentOpError)?.code
    // No dedicated i18n copy for `cannot_split`/`duplicate_question_id`
    // here (spec §5's key list has none) — the op's own message is
    // already a plain, specific sentence.
    alert(code === 'duplicate_question_id' ? t('km.idTaken') : (err as Error).message)
  }
}

function onDeleteSection(sectionId: string) {
  if (!confirm(t('km.deleteModelConfirm'))) return
  applyOp((c) => deleteSection(c, sectionId))
  if (openSectionId.value === sectionId) openSectionId.value = null
}

function onAddSection() {
  const id = prompt(t('km.sectionTitle'))
  if (!id) return
  applyOp((c) => addSection(c, { id, title: { en: id } }))
  openSectionId.value = id
}

function onAddQuestion(sectionId: string) {
  const id = prompt(t('km.questionId'))
  if (!id) return
  applyOp((c) => addQuestion(c, sectionId, { id, text: { en: id } }))
}
</script>

<style scoped>
.km-section-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.list-actions {
  display: flex;
  justify-content: flex-end;
}

.section {
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  overflow: hidden;
}

.section-summary {
  cursor: pointer;
  min-height: 44px;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  background-color: var(--color-hover);
  list-style: none;
}

.section-summary::-webkit-details-marker {
  display: none;
}

.section-title {
  font-weight: var(--font-weight-bold);
  font-size: 1.05rem;
}

.section-count {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.summary-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-left: auto;
}

.section-body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem;
}

.section-title-tabs {
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--color-border);
}

.ghost-btn {
  min-height: 44px;
  padding: 0.3rem 0.7rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.ghost-btn.danger {
  color: var(--color-error);
  border-color: var(--color-error);
}

.ghost-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn {
  min-height: 44px;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: var(--border-radius-sm);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
