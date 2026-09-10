<template>
  <div class="km-suggested-phrases">
    <div class="field-label-row">
      <span class="field-label">{{ $t('km.suggestedPhrases') }}</span>
      <span class="suggested-count">{{ phrases.length }}/{{ MAX_SUGGESTED_PHRASES }}</span>
    </div>

    <ul v-if="phrases.length > 0" class="phrase-list">
      <li v-for="(phrase, index) in phrases" :key="index" class="phrase-item">
        <KmLangTabs
          :model-value="phrase.text"
          :default-lang="locale"
          :disabled="readOnly"
          @change="(lang, value) => $emit('updateText', index, lang, value)"
        />
        <div class="phrase-item-actions">
          <MoveButtons
            :can-up="!readOnly && index > 0"
            :can-down="!readOnly && index < phrases.length - 1"
            @up="$emit('move', index, 'up')"
            @down="$emit('move', index, 'down')"
          />
          <button type="button" class="chip-remove" :disabled="readOnly" @click="$emit('remove', index)">
            <span aria-hidden="true">&times;</span>
            <span class="sr-only">{{ $t('km.removeSuggested') }}</span>
          </button>
        </div>
      </li>
    </ul>

    <button
      type="button"
      class="btn btn-secondary"
      :disabled="readOnly || phrases.length >= MAX_SUGGESTED_PHRASES"
      @click="$emit('add')"
    >
      {{ $t('km.addPhrase') }}
    </button>
    <p v-if="phrases.length >= MAX_SUGGESTED_PHRASES" class="hint">{{ $t('km.phrasesMax') }}</p>
  </div>
</template>

<script lang="ts" setup>
import { useI18n } from 'vue-i18n'
import { MAX_SUGGESTED_PHRASES, type MoveDirection } from '@/lib/kmContent'
import MoveButtons from './MoveButtons.vue'
import KmLangTabs from './KmLangTabs.vue'
import type { SuggestedPhrase } from '@/types/api'

/**
 * The "Suggested phrases" block under a question's `KmSuggestedFers` (spec
 * 08 §1.4, extended for free-text quick-pick options rather than catalogue
 * FERs — the co-facilitator's document's generic answer options that are
 * not FERs): current phrases as reorderable rows, each edited through
 * `KmLangTabs` (the same multilingual-text pattern `KmQuestionCard.vue`
 * uses for `question.text`/`help`), a counter and an "Add phrase" button
 * disabled at the 12 cap with a hint. Mirrors `KmSuggestedFers.vue`'s
 * add/remove/move UX; emits bubble up to `KmSectionList.vue`'s `applyOp`
 * exactly like `addSuggested`/`removeSuggested`/`moveSuggested`, so
 * autosave and validation run the same way.
 */
defineProps<{
  phrases: SuggestedPhrase[]
  readOnly?: boolean
}>()

defineEmits<{
  add: []
  remove: [index: number]
  move: [index: number, direction: MoveDirection]
  updateText: [index: number, lang: string, value: string]
}>()

const { locale } = useI18n()
</script>

<style scoped>
.km-suggested-phrases {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-hover);
}

.field-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.field-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
}

.suggested-count {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.phrase-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.phrase-item {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
}

.phrase-item-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
}

.chip-remove {
  min-width: 44px;
  min-height: 44px;
  border: 1px solid var(--color-error);
  border-radius: var(--border-radius-sm);
  background: none;
  color: var(--color-error);
  font-size: 1.1rem;
}

.hint {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.btn {
  min-height: 44px;
  padding: 0.4rem 1rem;
  border: none;
  border-radius: var(--border-radius-sm);
  font-size: var(--font-size-sm);
  cursor: pointer;
  align-self: flex-start;
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
