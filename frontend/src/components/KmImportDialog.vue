<template>
  <div class="km-import-dialog">
    <label class="field">
      <span>{{ $t('km.import') }}</span>
      <input ref="fileInput" type="file" accept="application/json,.json" @change="onFileChange" />
    </label>

    <p v-if="parseError" class="parse-error">{{ $t('km.importFailed') }}</p>

    <KmValidationList v-if="errors.length > 0" :errors="errors" />
  </div>
</template>

<script lang="ts" setup>
import { ref } from 'vue'
import KmValidationList from './KmValidationList.vue'
import type { ContentError } from '@/lib/kmContent'

/**
 * File input -> parsed JSON posted to `POST /knowledge-models/import`
 * (spec 04 §3 #6, §5). Server `errors` (content-validation failures) are
 * rendered as a list keyed by their `path`, via `KmValidationList`.
 */
defineProps<{ errors: ContentError[] }>()

const emit = defineEmits<{ import: [document: unknown] }>()

const fileInput = ref<HTMLInputElement | null>(null)
const parseError = ref(false)

function onFileChange(event: Event) {
  parseError.value = false
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    try {
      const document = JSON.parse(String(reader.result))
      emit('import', document)
    } catch {
      parseError.value = true
    }
  }
  reader.onerror = () => {
    parseError.value = true
  }
  reader.readAsText(file)
}
</script>

<style scoped>
.km-import-dialog {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.field input[type='file'] {
  min-height: 44px;
}

.parse-error {
  margin: 0;
  color: var(--color-error);
  font-size: var(--font-size-sm);
}
</style>
