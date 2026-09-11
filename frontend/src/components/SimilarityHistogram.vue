<template>
  <div class="similarity-histogram">
    <svg
      :viewBox="`0 0 ${width} ${height}`"
      class="histogram-svg"
      role="img"
      :aria-label="$t('dashboard.similarity.histogramLabel')"
    >
      <g v-for="(bar, i) in bars" :key="i">
        <rect
          :x="bar.x"
          :y="bar.y"
          :width="barWidth"
          :height="bar.barHeight"
          class="histogram-bar"
          :aria-label="barAriaLabel(bar)"
        />
        <text :x="bar.x + barWidth / 2" :y="height - 4" class="histogram-axis-label" text-anchor="middle">
          {{ bar.bucket.from.toFixed(1) }}
        </text>
      </g>
    </svg>
    <ul class="histogram-numbers sr-only">
      <li v-for="(bucket, i) in histogram" :key="i">{{ bucket.from }}–{{ bucket.to }}: {{ bucket.count }}</li>
    </ul>
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatCount } from '@/lib/dashboard'
import type { MapData } from '@/types/dashboard'

/**
 * The similarity-score distribution from `…/map` (spec 13 §4.4/§6.2): a
 * server-bucketed histogram, hand-rolled SVG bars (no chart library, per
 * builder brief C's read-first list). ≤20 bars regardless of population.
 * Every bar carries a number (via the axis + an `aria-label`, and a
 * screen-reader-only list) — colour is never the only signal (spec 02 §4.3).
 */
const props = defineProps<{ histogram: MapData['histogram'] }>()

const { t } = useI18n()

const width = 480
const height = 160
const padding = 20

const maxCount = computed(() => Math.max(1, ...props.histogram.map((b) => b.count)))
const barWidth = computed(() => (props.histogram.length > 0 ? (width - padding * 2) / props.histogram.length - 4 : 0))

const bars = computed(() =>
  props.histogram.map((bucket, i) => {
    const barHeight = ((height - padding - 16) * bucket.count) / maxCount.value
    return {
      bucket,
      x: padding + i * ((width - padding * 2) / props.histogram.length),
      y: height - 16 - barHeight,
      barHeight,
    }
  })
)

function barAriaLabel(bar: (typeof bars.value)[number]): string {
  return t('dashboard.similarity.histogramBarLabel', {
    from: bar.bucket.from,
    to: bar.bucket.to,
    count: formatCount(bar.bucket.count),
  })
}
</script>

<style scoped>
.similarity-histogram {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.histogram-svg {
  width: 100%;
  height: auto;
  max-height: 200px;
}

.histogram-bar {
  fill: var(--color-primary);
}

.histogram-axis-label {
  font-size: 8px;
  fill: var(--color-text-secondary);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
}
</style>
