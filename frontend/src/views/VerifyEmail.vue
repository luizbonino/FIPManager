<template>
  <div class="auth-form">
    <h1>{{ $t('auth.verifyTitle') }}</h1>

    <div v-if="isLoading" class="loading">
      <p>{{ $t('common.loading') }}</p>
    </div>

    <div v-else-if="ok" class="form-success">
      <p>{{ $t('auth.verifyOk') }}</p>
      <router-link to="/workspace">{{ $t('auth.backToWorkspace') }}</router-link>
    </div>

    <div v-else-if="expired" class="form-error">
      <p>{{ $t('auth.verifyExpired') }}</p>
      <router-link :to="authStore.isAuthenticated ? '/workspace' : '/login'">
        {{ authStore.isAuthenticated ? $t('auth.backToWorkspace') : $t('auth.backToLogin') }}
      </router-link>
    </div>

    <div v-else class="form-error">
      <p>{{ $t('auth.verifyInvalid') }}</p>
      <router-link :to="authStore.isAuthenticated ? '/workspace' : '/login'">
        {{ authStore.isAuthenticated ? $t('auth.backToWorkspace') : $t('auth.backToLogin') }}
      </router-link>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { verifyEmail } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { ApiResponseError } from '@/api/client'

/** spec 07 §3: posts `?token=` on mount, renders success / expired / invalid. */
const route = useRoute()
const authStore = useAuthStore()

const isLoading = ref(true)
const ok = ref(false)
const expired = ref(false)

onMounted(async () => {
  const token = String(route.query.token ?? '')
  try {
    await verifyEmail(token)
    ok.value = true
    // Refresh `emailVerifiedAt`/`verificationRequired` so the Workspace
    // banner clears immediately for an already-signed-in visitor.
    if (authStore.isAuthenticated) {
      await authStore.restoreSession()
    }
  } catch (err) {
    if (err instanceof ApiResponseError && err.status === 410) {
      expired.value = true
    }
    // 400 (unknown/used/mismatched token), or a network error: falls
    // through to the generic "invalid" panel.
  } finally {
    isLoading.value = false
  }
})
</script>

<style scoped>
.auth-form {
  max-width: 400px;
  margin: 2rem auto;
  padding: 1rem;
  text-align: center;
}

.auth-form h1 {
  margin-bottom: 1.5rem;
  color: var(--color-primary);
}

.loading {
  padding: 2rem 0;
}

.form-success,
.form-error {
  padding: 0.75rem;
  border-radius: 4px;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.form-success {
  background-color: var(--color-success-bg);
  color: var(--color-success);
}

.form-error {
  background-color: var(--color-error-bg);
  color: var(--color-error);
}
</style>
