<template>
  <article class="cluster-card">
    <header class="cc-header">
      <h3 class="cc-size">{{ $t('dashboard.similarity.clusterSize', { size: cluster.size }) }}</h3>
      <span class="cc-mean">{{ $t('dashboard.similarity.meanSimilarity', { value: formatShare(cluster.meanSimilarity) }) }}</span>
    </header>
    <p class="cc-representative">
      {{ $t('dashboard.similarity.representative') }}:
      <router-link :to="`/fips/${cluster.representative.fipId}`">{{ cluster.representative.label }}</router-link>
    </p>
    <ul class="cc-principles">
      <li v-for="p in cluster.principles" :key="p" class="cc-principle-chip">{{ p }}</li>
    </ul>
    <button type="button" class="cc-toggle" @click="expanded = !expanded">
      {{ expanded ? $t('dashboard.similarity.hideMembers') : $t('dashboard.similarity.showMembers', { count: cluster.members.length }) }}
    </button>
    <ul v-if="expanded" class="cc-members">
      <li v-for="member in cluster.members" :key="member.fipId">
        <router-link :to="`/fips/${member.fipId}`">{{ member.label }}</router-link>
      </li>
    </ul>
  </article>
</template>

<script lang="ts" setup>
import { ref } from 'vue'
import { formatShare } from '@/lib/dashboard'
import type { ClusterRow } from '@/types/dashboard'

/**
 * Spec 13 §4.4/§6.2: size, representative, mean intra-similarity, the
 * principle codes that hold it together, expandable to up to 10 named
 * members (already filtered by `readable_individually` server-side).
 */
defineProps<{ cluster: ClusterRow }>()

const expanded = ref(false)
</script>

<style scoped>
.cluster-card {
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  padding: 0.75rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.cc-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.5rem;
}

.cc-size {
  margin: 0;
  font-size: var(--font-size-md);
}

.cc-mean {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.cc-representative {
  margin: 0;
  font-size: var(--font-size-sm);
}

.cc-principles {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
}

.cc-principle-chip {
  font-size: var(--font-size-xs);
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  background-color: var(--color-chip-bg, var(--color-secondary));
  color: var(--color-chip-text, var(--color-secondary-text));
}

.cc-toggle {
  align-self: flex-start;
  border: none;
  background: none;
  color: var(--color-link);
  cursor: pointer;
  padding: 0;
  font-size: var(--font-size-sm);
  min-height: 44px;
}

.cc-members {
  margin: 0;
  padding-left: 1.1rem;
  font-size: var(--font-size-sm);
}
</style>
