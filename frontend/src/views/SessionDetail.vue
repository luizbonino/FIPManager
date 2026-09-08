<template>
  <div class="session-detail-view">
    <div v-if="store.loading" class="loading">
      <p>{{ $t('common.loading') }}</p>
    </div>

    <template v-else-if="session">
      <div class="projector-block">
        <p class="join-code">{{ session.joinCode }}</p>
        <p class="join-url">{{ session.joinUrl }}</p>
        <QrCode :text="session.joinUrl" :size="256" />
        <span v-if="session.status === 'closed'" class="closed-chip">{{ $t('sessionAdmin.closed') }}</span>
      </div>

      <button type="button" class="btn btn-secondary projector-toggle" @click="toggleProjector">
        {{ $t('sessionAdmin.hideChrome') }}
      </button>

      <h1>{{ session.title }}</h1>

      <h2>{{ $t('sessionAdmin.fips') }}</h2>
      <SessionFipList :fips="store.fips" :reconnecting="store.reconnecting" />

      <div class="actions">
        <button v-if="session.status !== 'closed'" type="button" class="btn btn-danger" @click="onClose">
          {{ $t('sessionAdmin.close') }}
        </button>
        <a class="btn btn-secondary" :href="sessionExportJsonUrl(session.id)">{{ $t('fip.exportJson') }}</a>
        <a class="btn btn-secondary" :href="sessionExportCsvUrl(session.id)">{{ $t('fip.exportCsv') }}</a>
        <span class="export-all-label">{{ $t('sessionAdmin.exportAll') }}</span>
        <router-link :to="`/sessions/${session.id}/matrix`" class="btn btn-secondary">
          {{ $t('sessionAdmin.matrix') }}
        </router-link>
      </div>
    </template>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useSessionStore } from '@/stores/session'
import { sessionExportCsvUrl, sessionExportJsonUrl } from '@/api/sessions'
import QrCode from '@/components/QrCode.vue'
import SessionFipList from '@/components/SessionFipList.vue'

// Spec 02 §4.2.
const route = useRoute()
const { t } = useI18n()
const store = useSessionStore()

const session = computed(() => store.session)
const projectorMode = ref(false)

function toggleProjector() {
  projectorMode.value = !projectorMode.value
  document.body.classList.toggle('projector-mode', projectorMode.value)
}

async function onClose() {
  if (!confirm(t('sessionAdmin.closeConfirm'))) return
  await store.close()
}

onMounted(async () => {
  await store.load(String(route.params.id))
  await store.loadFips()
  store.startPolling()
})

onUnmounted(() => {
  store.stopPolling()
  document.body.classList.remove('projector-mode')
})
</script>

<style scoped>
.session-detail-view {
  max-width: 900px;
  margin: 0 auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.loading {
  text-align: center;
  padding: 3rem 1rem;
}

.projector-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 2rem 1rem;
  text-align: center;
}

.join-code {
  margin: 0;
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-variant-numeric: tabular-nums;
  font-size: clamp(3rem, 14vw, 8rem);
  letter-spacing: 0.12em;
  line-height: 1;
  color: var(--color-primary);
}

.join-url {
  margin: 0;
  font-size: clamp(1rem, 3vw, 2rem);
  color: var(--color-text-secondary);
  word-break: break-all;
}

.closed-chip {
  display: inline-block;
  margin-top: 0.5rem;
  padding: 0.3rem 0.9rem;
  border-radius: 999px;
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
  font-weight: var(--font-weight-medium);
}

.projector-toggle {
  align-self: center;
}

.actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.export-all-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.btn {
  min-height: 44px;
  padding: 0.6rem 1.2rem;
  border: none;
  border-radius: var(--border-radius-sm);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
}

.btn-danger {
  background-color: var(--color-error);
  color: #fff;
}
</style>
