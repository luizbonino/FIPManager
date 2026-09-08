<template>
  <div class="qr-code" v-html="svg" />
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import { qrCodeSvg } from '@/lib/qr'

/** Inline `<svg>` QR (spec 02 §2.4) via `lib/qr.ts` — no canvas, no server round trip. */
const props = withDefaults(defineProps<{ text: string; size?: number }>(), { size: 256 })

const svg = computed(() => qrCodeSvg(props.text, { size: props.size }))
</script>

<style scoped>
.qr-code {
  display: inline-flex;
  line-height: 0;
}

.qr-code :deep(svg) {
  max-width: 100%;
  height: auto;
}
</style>
