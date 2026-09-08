<template>
  <details class="share-box no-print" open>
    <summary>{{ $t('share.title') }}</summary>
    <div class="share-body">
      <div class="share-link-row">
        <input :value="url" type="text" readonly class="share-link-input" @click="selectAll" />
        <button type="button" class="copy-btn" @click="copy">
          {{ copied ? $t('share.copied') : $t('share.copyLink') }}
        </button>
      </div>
      <div class="share-qr">
        <QrCode :text="url" :size="160" />
        <p class="qr-hint">{{ $t('share.qrHint') }}</p>
      </div>
    </div>
  </details>
</template>

<script lang="ts" setup>
import { ref } from 'vue'
import QrCode from './QrCode.vue'

/** `<details>` labelled "Share" (spec 02 §2.4): the absolute FIP URL, copy button, QR. */
const props = defineProps<{ url: string }>()

const copied = ref(false)

function selectAll(event: Event) {
  ;(event.target as HTMLInputElement).select()
}

async function copy() {
  try {
    await navigator.clipboard.writeText(props.url)
  } catch {
    // Clipboard API unavailable: fall back to select-all so the user can Cmd/Ctrl+C.
    const input = document.querySelector<HTMLInputElement>('.share-link-input')
    input?.select()
  }
  copied.value = true
  setTimeout(() => {
    copied.value = false
  }, 2000)
}
</script>

<style scoped>
.share-box {
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  padding: 0.75rem 1rem;
  background-color: var(--color-background);
}

.share-box summary {
  cursor: pointer;
  font-weight: var(--font-weight-medium);
  min-height: 44px;
  display: flex;
  align-items: center;
}

.share-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-top: 0.75rem;
}

.share-link-row {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.share-link-input {
  flex: 1;
  min-width: 10rem;
  min-height: 44px;
  padding: 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-hover);
  color: var(--color-text);
  font-size: var(--font-size-sm);
}

.copy-btn {
  min-height: 44px;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: var(--border-radius-sm);
  background-color: var(--color-primary);
  color: var(--color-primary-text);
}

.share-qr {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.35rem;
}

.qr-hint {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}
</style>
