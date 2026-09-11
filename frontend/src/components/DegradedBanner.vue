<template>
  <div class="degraded-banner no-print" :class="{ error: variant === 'error' }" role="status">
    <p class="banner-reason">{{ reasonText }}</p>
    <p v-if="staleFips != null" class="banner-detail">
      {{ $t('dashboard.degraded.staleCount', { stale: staleFips, total: totalFips ?? staleFips }) }}
    </p>
    <p v-if="showHint && hint" class="banner-hint">
      <code>{{ hint }}</code>
    </p>
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

/**
 * Spec 13 §1.8/§2.4/§7.3: names the reason a response is degraded (a
 * `200` computed on the fly, `"degraded": true`) or refused (`409`/`403`).
 * The CLI hint (`backfill-declarations --only-stale`) renders only for an
 * admin viewer (spec 13 AC-5: "shows the CLI hint to an admin only").
 */
const props = defineProps<{
  reason: string
  variant?: 'degraded' | 'error'
  staleFips?: number | null
  totalFips?: number | null
  hint?: string | null
  isAdmin?: boolean
  minimum?: number | null
}>()

const { t } = useI18n()

const KNOWN_REASONS = new Set([
  'projection_stale',
  'projection_missing',
  'dashboard_disabled',
  'population_too_small',
  'similarity_population_too_large',
  'invalid_population',
  'questionnaire_too_large',
  'refresh_in_progress',
])

const reasonText = computed(() => {
  const key = KNOWN_REASONS.has(props.reason) ? props.reason : 'unknown'
  if (props.reason === 'population_too_small') {
    return t('dashboard.errors.population_too_small', { minimum: props.minimum ?? 5 })
  }
  return t(`dashboard.errors.${key}`)
})

const showHint = computed(() => !!props.isAdmin && !!props.hint)
</script>

<style scoped>
.degraded-banner {
  padding: 0.6rem 1rem;
  border-radius: var(--border-radius-sm);
  background-color: #fff7ed;
  border: 1px solid #fdba74;
  color: #7c2d12;
  font-size: var(--font-size-sm);
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.degraded-banner.error {
  background-color: #fef2f2;
  border-color: #fca5a5;
  color: #7f1d1d;
}

.banner-reason,
.banner-detail,
.banner-hint {
  margin: 0;
}

.banner-hint code {
  background-color: rgba(0, 0, 0, 0.06);
  padding: 0.1rem 0.4rem;
  border-radius: var(--border-radius-sm);
}
</style>
