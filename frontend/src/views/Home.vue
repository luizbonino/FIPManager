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
    </template>

    <div v-else class="authenticated-content">
      <h2>{{ $t('common.welcome') }}, {{ user?.displayName }}!</h2>
      <router-link to="/workspace" class="btn btn-primary">{{ $t('nav.workspace') }}</router-link>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

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
