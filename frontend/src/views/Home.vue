<template>
  <div class="home-view">
    <template v-if="!isAuthenticated">
      <h1>{{ $t('home.heading') }}</h1>
      <p class="tagline">{{ $t('home.tagline') }}</p>

      <form class="join-form" @submit.prevent="onJoin">
        <label for="home-join-code">{{ $t('home.joinLabel') }}</label>
        <div class="join-row">
          <input
            id="home-join-code"
            v-model="joinCode"
            type="text"
            class="join-input"
            :placeholder="$t('home.joinPlaceholder')"
            autocomplete="off"
          />
          <button type="submit" class="btn btn-primary" :disabled="!joinCode.trim()">
            {{ $t('home.joinButton') }}
          </button>
        </div>
      </form>

      <div class="auth-links">
        <router-link to="/login" class="btn btn-secondary">{{ $t('auth.submitLogin') }}</router-link>
        <router-link to="/register" class="btn btn-secondary">{{ $t('auth.submitRegister') }}</router-link>
      </div>

      <!-- Spec 09: a standalone FIP needs neither a session nor an account. -->
      <div class="standalone-block">
        <h2>{{ $t('home.standaloneHeading') }}</h2>
        <p>{{ $t('home.standaloneText') }}</p>
        <router-link to="/fips/new" class="btn btn-primary">{{ $t('home.startFip') }}</router-link>
      </div>

      <div v-if="deviceFips.length > 0" class="device-fips">
        <h2>{{ $t('home.yourFipsOnDevice') }}</h2>
        <ul>
          <li v-for="fip in deviceFips" :key="fip.id">
            <router-link :to="`/fips/${fip.id}/edit`">{{ fip.title ?? fip.id }}</router-link>
          </li>
        </ul>
      </div>
    </template>

    <div v-else class="authenticated-content">
      <h2>{{ $t('common.welcome') }}, {{ user?.displayName }}!</h2>
      <router-link to="/workspace" class="btn btn-primary">{{ $t('nav.workspace') }}</router-link>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getFip } from '@/api/fips'
import { ApiResponseError } from '@/api/client'
import { clearToken, getToken, listTokenFipIds } from '@/lib/editTokens'
import { useAuthStore } from '@/stores/auth'

const MAX_DEVICE_FIPS = 10

const authStore = useAuthStore()
const router = useRouter()

const isAuthenticated = computed(() => authStore.isAuthenticated)
const user = computed(() => authStore.user)

const joinCode = ref('')

function onJoin() {
  const code = joinCode.value.trim().toUpperCase()
  if (!code) return
  router.push(`/join/${code}`)
}

// Spec 09: "FIPs on this device" — every FIP id this browser holds an edit
// token for, titled via a live fetch (the token alone carries no title). A
// FIP that no longer resolves (deleted, or the token was revoked by a
// claim elsewhere) is dropped from the list and its stale token cleared.
const deviceFips = ref<{ id: string; title: string | null }[]>([])

onMounted(async () => {
  if (authStore.isAuthenticated) return
  const ids = listTokenFipIds().slice(0, MAX_DEVICE_FIPS)
  const results = await Promise.all(
    ids.map(async (id) => {
      try {
        const fip = await getFip(id, getToken(id) ?? undefined)
        return { id, title: fip.title }
      } catch (err) {
        // Only drop the token when the API itself says it's no longer
        // valid (404 = FIP gone, 403 = token revoked by a claim
        // elsewhere). Any other failure (network error, 5xx) is
        // transient — keep the token and still show the entry, titled
        // by its id since we couldn't fetch the title.
        if (err instanceof ApiResponseError && (err.status === 404 || err.status === 403)) {
          clearToken(id)
          return null
        }
        return { id, title: null }
      }
    })
  )
  deviceFips.value = results.filter((r): r is { id: string; title: string | null } => r !== null)
})
</script>

<style scoped>
.home-view {
  max-width: 600px;
  margin: 2rem auto;
  padding: 1rem;
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.home-view h1 {
  font-size: 1.75rem;
  margin: 0;
  color: var(--color-primary);
}

.tagline {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--font-size-md);
}

.join-form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 1rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  background-color: var(--color-hover);
}

.join-form label {
  font-weight: var(--font-weight-medium);
}

.join-row {
  display: flex;
  gap: 0.5rem;
}

.join-input {
  flex: 1;
  min-height: 44px;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  font-size: 1.1rem;
  text-transform: uppercase;
  text-align: center;
  letter-spacing: 0.1em;
}

.auth-links,
.authenticated-content {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  align-items: center;
}

.standalone-block {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  align-items: center;
  padding: 1rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
}

.standalone-block h2 {
  margin: 0;
  font-size: 1.1rem;
  color: var(--color-primary);
}

.standalone-block p {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}

.device-fips {
  text-align: left;
}

.device-fips h2 {
  font-size: 1rem;
  color: var(--color-text-secondary);
  margin: 0 0 0.5rem;
}

.device-fips ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.btn {
  min-height: 44px;
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: var(--border-radius-sm);
  text-decoration: none;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.btn-primary {
  background-color: var(--color-primary);
  color: var(--color-primary-text);
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@media (max-width: 480px) {
  .home-view {
    margin: 1rem;
    padding: 0;
  }

  .join-row {
    flex-direction: column;
  }
}
</style>
