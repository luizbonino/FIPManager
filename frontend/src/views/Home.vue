<template>
  <div class="home-view">
    <h1 v-if="!isAuthenticated">{{ $t('appName') }}</h1>
    <p v-if="!isAuthenticated" class="welcome-message">{{ $t('common.welcome') }}</p>
    
    <div v-if="!isAuthenticated" class="auth-links">
      <router-link to="/login" class="btn btn-primary">{{ $t('auth.submitLogin') }}</router-link>
      <router-link to="/register" class="btn btn-secondary">{{ $t('auth.submitRegister') }}</router-link>
    </div>
    
    <div v-else class="authenticated-content">
      <h2>{{ $t('common.welcome') }}, {{ user?.displayName }}!</h2>
      <p>{{ $t('workspace.title') }}</p>
      <router-link to="/workspace" class="btn btn-primary">{{ $t('nav.workspace') }}</router-link>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

const isAuthenticated = computed(() => authStore.isAuthenticated)
const user = computed(() => authStore.user)
</script>

<style scoped>
.home-view {
  max-width: 600px;
  margin: 2rem auto;
  padding: 1rem;
  text-align: center;
}

.home-view h1 {
  font-size: 2rem;
  margin-bottom: 1rem;
  color: var(--color-primary);
}

.welcome-message {
  font-size: 1.2rem;
  margin-bottom: 2rem;
  color: var(--color-text);
}

.auth-links,
.authenticated-content {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  align-items: center;
}

.btn {
  padding: 0.75rem 1.5rem;
  border-radius: 4px;
  text-decoration: none;
  font-weight: 500;
  transition: background-color 0.2s ease;
}

.btn-primary {
  background-color: var(--color-primary);
  color: var(--color-primary-text);
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
}

@media (max-width: 480px) {
  .home-view {
    margin: 1rem;
    padding: 0;
  }
}
</style>
