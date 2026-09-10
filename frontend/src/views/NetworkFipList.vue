<template>
  <div class="network-fip-list">
    <h1>{{ $t('network.listTitle') }}</h1>

    <label class="search-field">
      <span>{{ $t('network.searchLabel') }}</span>
      <input v-model="query" type="search" :placeholder="$t('network.searchPlaceholder')" />
    </label>

    <div v-if="loading" class="loading">
      <p>{{ $t('common.loading') }}</p>
    </div>

    <div v-else-if="errorState === 'disabled'" class="message-box">
      <p>{{ $t('network.disabledMessage') }}</p>
    </div>

    <div v-else-if="errorState === 'unavailable'" class="message-box">
      <p>{{ $t('network.unavailableMessage') }}</p>
      <button type="button" class="btn btn-secondary" @click="load">{{ $t('common.retry') }}</button>
    </div>

    <div v-else-if="items.length === 0" class="message-box">
      <p>{{ $t('network.noResults', { query }) }}</p>
    </div>

    <template v-else>
      <table class="community-table">
        <thead>
          <tr>
            <th scope="col">{{ $t('network.communityLabel') }}</th>
            <th scope="col">{{ $t('network.fipCount') }}</th>
            <th scope="col"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.iri">
            <td :data-label="$t('network.communityLabel')">{{ item.label }}</td>
            <td :data-label="$t('network.fipCount')">{{ item.fipCount }}</td>
            <td>
              <router-link :to="`/network/${encodeURIComponent(item.iri)}`" class="view-link">
                {{ $t('common.view') }}
              </router-link>
            </td>
          </tr>
        </tbody>
      </table>

      <div class="list-footer">
        <p class="shown-of-total">{{ $t('network.shownOfTotal', { shown: items.length, total }) }}</p>
        <button
          v-if="hasMore"
          type="button"
          class="btn btn-secondary"
          :disabled="loadingMore"
          @click="loadMore"
        >
          {{ $t('network.loadMore') }}
        </button>
      </div>
    </template>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref, watch } from 'vue'
import { listCommunities } from '@/api/network'
import { ApiResponseError } from '@/api/client'
import type { NetworkCommunitySummary } from '@/types/network'

/**
 * spec 11 §3.5: `/network` — search is server-side (debounced 300 ms,
 * passing `q` to `GET /api/network/fip-communities`; an empty field lists
 * without `q`), paged 50 at a time via `limit`/`offset`, with a "Load
 * more" button appending the next page while `total > items.length`.
 * Three distinct empty states: no results for the typed query,
 * `network_disabled` (no retry — nothing will change until the deployment
 * reconfigures it), and `network_unavailable` (Retry, which re-runs the
 * same fetch from the start).
 */
const PAGE_SIZE = 50

type ErrorState = 'disabled' | 'unavailable' | null

const items = ref<NetworkCommunitySummary[]>([])
const total = ref(0)
const loading = ref(true)
const loadingMore = ref(false)
const errorState = ref<ErrorState>(null)
const query = ref('')

let debounceTimer: ReturnType<typeof setTimeout> | null = null

function scheduleDebounce() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    load()
  }, 300)
}

const hasMore = computed(() => total.value > items.value.length)

async function load() {
  if (debounceTimer) {
    clearTimeout(debounceTimer)
    debounceTimer = null
  }
  loading.value = true
  errorState.value = null
  try {
    const q = query.value.trim()
    const result = await listCommunities({ q: q || undefined, limit: PAGE_SIZE })
    items.value = result.items
    total.value = result.total
  } catch (err) {
    if (err instanceof ApiResponseError && err.data.detail === 'network_disabled') {
      errorState.value = 'disabled'
    } else {
      errorState.value = 'unavailable'
    }
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (loadingMore.value || !hasMore.value) return
  loadingMore.value = true
  try {
    const q = query.value.trim()
    const result = await listCommunities({ q: q || undefined, limit: PAGE_SIZE, offset: items.value.length })
    items.value = [...items.value, ...result.items]
    total.value = result.total
  } catch {
    // Load more failing leaves the already-fetched page visible; the user
    // can retry by clicking again (same idiom as the initial-load Retry,
    // scoped to not wipe out what already loaded successfully).
  } finally {
    loadingMore.value = false
  }
}

onMounted(load)

watch(query, scheduleDebounce)
</script>

<style scoped>
.network-fip-list {
  max-width: 800px;
  margin: 0 auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.search-field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.search-field input {
  min-height: 44px;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  font-size: 1rem;
  font-family: inherit;
}

.loading,
.message-box {
  text-align: center;
  padding: 2rem 1rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

.community-table {
  width: 100%;
  border-collapse: collapse;
}

.community-table th,
.community-table td {
  text-align: left;
  padding: 0.6rem 0.5rem;
  border-bottom: 1px solid var(--color-border);
}

.view-link {
  color: var(--color-link);
}

.list-footer {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.shown-of-total {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}

.btn {
  min-height: 44px;
  padding: 0.6rem 1.2rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
  border: none;
}

.btn:disabled {
  opacity: 0.7;
}
</style>
