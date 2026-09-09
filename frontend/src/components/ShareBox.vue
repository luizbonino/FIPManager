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
      <div v-if="editToken" class="share-edit-link">
        <p class="edit-link-label">{{ $t('share.editLink') }}</p>
        <div class="share-link-row">
          <input :value="editLinkUrl" type="text" readonly class="share-link-input edit-link-input" @click="selectEditLink" />
          <button type="button" class="copy-btn" @click="copyEditLink">
            {{ editLinkCopied ? $t('share.copied') : $t('share.copyLink') }}
          </button>
        </div>
        <p class="edit-link-warning">{{ $t('share.editLinkWarning') }}</p>
      </div>
      <div class="share-qr">
        <QrCode :text="url" :size="160" />
        <p class="qr-hint">{{ $t('share.qrHint') }}</p>
      </div>
      <div class="share-embed">
        <p class="embed-label">{{ $t('share.embed') }}</p>
        <div class="embed-row">
          <textarea
            readonly
            rows="2"
            class="embed-snippet"
            :value="embedSnippet"
            @click="selectEmbed"
          ></textarea>
          <button type="button" class="copy-btn" @click="copyEmbed">
            {{ embedCopied ? $t('share.copied') : $t('share.copyEmbed') }}
          </button>
        </div>
      </div>
    </div>
  </details>
</template>

<script lang="ts" setup>
import { computed, ref } from 'vue'
import QrCode from './QrCode.vue'

/**
 * `<details>` labelled "Share" (spec 02 §2.4): the absolute FIP URL, copy
 * button, QR, and (spec 06 §3) an "Embed" item with the `<iframe>` snippet
 * for `GET /fips/{id}/embed`.
 *
 * `editToken` (spec 09 follow-up) is optional and set only by
 * FipEditor.vue, which alone knows this device's edit token — when
 * present, an extra "Edit link" row lets a participant carry edit rights
 * to another device or hand them to a colleague (today the token only
 * ever lived in this browser's localStorage).
 */
const props = defineProps<{ url: string; fipId: string; editToken?: string }>()

const copied = ref(false)
const embedCopied = ref(false)
const editLinkCopied = ref(false)

const embedUrl = computed(() => `${location.origin}/fips/${props.fipId}/embed`)
const embedSnippet = computed(
  () => `<iframe src="${embedUrl.value}" width="100%" height="600" loading="lazy" title="FIP"></iframe>`
)
const editLinkUrl = computed(
  () => `${location.origin}/fips/${props.fipId}/edit?token=${encodeURIComponent(props.editToken ?? '')}`
)

function selectAll(event: Event) {
  ;(event.target as HTMLInputElement).select()
}

function selectEmbed(event: Event) {
  ;(event.target as HTMLTextAreaElement).select()
}

function selectEditLink(event: Event) {
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

async function copyEditLink() {
  try {
    await navigator.clipboard.writeText(editLinkUrl.value)
  } catch {
    const input = document.querySelector<HTMLInputElement>('.edit-link-input')
    input?.select()
  }
  editLinkCopied.value = true
  setTimeout(() => {
    editLinkCopied.value = false
  }, 2000)
}

async function copyEmbed() {
  try {
    await navigator.clipboard.writeText(embedSnippet.value)
  } catch {
    const textarea = document.querySelector<HTMLTextAreaElement>('.embed-snippet')
    textarea?.select()
  }
  embedCopied.value = true
  setTimeout(() => {
    embedCopied.value = false
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

.share-edit-link {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.edit-link-label {
  margin: 0;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.edit-link-warning {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
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

.share-embed {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.embed-label {
  margin: 0;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.embed-row {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.embed-snippet {
  flex: 1;
  min-width: 10rem;
  padding: 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-hover);
  color: var(--color-text);
  font-family: monospace;
  font-size: var(--font-size-xs);
  resize: vertical;
}
</style>
