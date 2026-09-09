<template>
  <div v-if="targets.length > 0" class="migration-banner">
    <p class="migration-banner-body">{{ $t('migration.bannerBody', { version: latestVersion }) }}</p>
    <p v-if="pinned" class="migration-banner-pinned">{{ $t('migration.pinned') }}</p>
    <router-link v-else :to="`/fips/${fipId}/migrate`" class="btn btn-secondary">
      {{ $t('migration.review') }}
    </router-link>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue'
import { getFip, getMigrationTargets } from '@/api/fips'
import type { MigrationTargetItem } from '@/types/api'

/**
 * spec 07 §5: shown on `FipEditor.vue` and `FipRead.vue`, only for a caller
 * who may write and only when `GET .../migration-targets` is non-empty — the
 * server enforces "may write" itself (403/404 on that same-auth-as-write
 * endpoint), which this component simply treats as "no banner". A pinned
 * session FIP (spec §4) still gets the banner, with the pinned explanation
 * instead of a button.
 *
 * `sessionId` is normally supplied by the caller (`FipEditor.vue` already
 * has the loaded `FipOut`); when omitted (`FipRead.vue`, whose single data
 * source is the export document and carries no `sessionId`) this component
 * fetches the bare FIP once itself to learn it — the same call that would
 * 403 for a non-writer anyway, so it doubles as the write-rights probe.
 */
const props = defineProps<{
  fipId: string
  editToken?: string
  sessionId?: string | null
}>()

const targets = ref<MigrationTargetItem[]>([])
const resolvedSessionId = ref<string | null>(props.sessionId ?? null)

const pinned = computed(() => !!resolvedSessionId.value)
// `migration-targets` is documented ascending; the highest (last) version is the headline.
const latestVersion = computed(() => targets.value[targets.value.length - 1]?.version ?? '')

async function load() {
  try {
    if (props.sessionId === undefined) {
      const fip = await getFip(props.fipId, props.editToken)
      resolvedSessionId.value = fip.sessionId
    }
    const result = await getMigrationTargets(props.fipId, props.editToken)
    targets.value = result.items
  } catch {
    // Unreadable, forbidden (not a writer) or a network error: no banner.
    targets.value = []
  }
}

onMounted(load)
</script>

<style scoped>
.migration-banner {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  padding: 0.6rem 0.9rem;
  background-color: var(--color-user-info);
  color: var(--color-user-info-text);
  border-radius: var(--border-radius-sm);
  font-size: var(--font-size-sm);
}

.migration-banner-body,
.migration-banner-pinned {
  margin: 0;
}

.btn {
  min-height: 44px;
  padding: 0.4rem 0.9rem;
  border: none;
  border-radius: var(--border-radius-sm);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
}
</style>
