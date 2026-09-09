<template>
  <div class="auth-form">
    <h1>{{ $t('password.mustChangeTitle') }}</h1>
    <p class="hint">{{ $t('password.mustChangeHint') }}</p>

    <form @submit.prevent="handleSubmit" class="form">
      <div class="form-group">
        <label for="currentPassword">{{ $t('password.current') }}</label>
        <input
          id="currentPassword"
          v-model="currentPassword"
          type="password"
          required
          autocomplete="current-password"
        />
      </div>

      <div class="form-group">
        <label for="newPassword">{{ $t('password.new') }}</label>
        <input
          id="newPassword"
          v-model="newPassword"
          type="password"
          required
          minlength="10"
          maxlength="128"
          autocomplete="new-password"
        />
      </div>

      <div class="form-actions">
        <button type="submit" :disabled="isLoading" class="btn btn-primary">
          <span v-if="!isLoading">{{ $t('password.submit') }}</span>
          <span v-else>{{ $t('common.loading') }}</span>
        </button>
      </div>

      <p v-if="done" class="form-success">{{ $t('password.changed') }}</p>
      <p v-if="error" class="form-error">{{ error }}</p>
    </form>
  </div>
</template>

<script lang="ts" setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ApiResponseError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

// spec 05 §1: reused for both the voluntary "change my password" flow
// (not yet linked from elsewhere in v1) and the forced
// `mustChangePassword` redirect installed in `router/index.ts` — the
// temporary password an admin set is what the user types as "current".
const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()

const currentPassword = ref('')
const newPassword = ref('')
const isLoading = ref(false)
const done = ref(false)
const error = ref<string | null>(null)

async function handleSubmit() {
  isLoading.value = true
  error.value = null
  done.value = false
  try {
    await authStore.changePassword(currentPassword.value, newPassword.value)
    done.value = true
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/workspace'
    await router.replace(redirect)
  } catch (err) {
    if (err instanceof ApiResponseError && err.status === 401) {
      error.value = t('errors.invalidCredentials')
    } else {
      error.value = t('errors.serverError')
    }
  } finally {
    isLoading.value = false
  }
}
</script>

<style scoped>
.auth-form {
  max-width: 400px;
  margin: 2rem auto;
  padding: 1rem;
}

.auth-form h1 {
  text-align: center;
  margin-bottom: 0.5rem;
  color: var(--color-primary);
}

.hint {
  text-align: center;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  margin-bottom: 1.5rem;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-group label {
  font-weight: 500;
  color: var(--color-text);
}

.form-group input {
  padding: 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background-color: var(--color-background);
  color: var(--color-text);
  font-size: 1rem;
}

.form-group input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.form-actions {
  display: flex;
  justify-content: center;
}

.btn {
  min-height: 44px;
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 4px;
  background-color: var(--color-primary);
  color: var(--color-primary-text);
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
}

.btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.form-error {
  color: var(--color-error);
  text-align: center;
  padding: 0.5rem;
  background-color: var(--color-error-bg);
  border-radius: 4px;
}

.form-success {
  color: var(--color-success);
  text-align: center;
  padding: 0.5rem;
  background-color: var(--color-success-bg);
  border-radius: 4px;
}
</style>
