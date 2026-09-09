<template>
  <div class="auth-form">
    <h1>{{ $t('auth.forgotTitle') }}</h1>

    <div v-if="submitted" class="form-success" data-testid="forgot-sent">
      <p>{{ $t('auth.forgotSent') }}</p>
      <router-link to="/login">{{ $t('auth.backToLogin') }}</router-link>
    </div>

    <form v-else @submit.prevent="handleSubmit" class="form">
      <div class="form-group">
        <label for="email">{{ $t('auth.emailLabel') }}</label>
        <input
          id="email"
          v-model="email"
          type="email"
          :placeholder="$t('auth.emailPlaceholder')"
          required
        />
      </div>

      <div class="form-actions">
        <button type="submit" :disabled="isLoading" class="btn btn-primary">
          <span v-if="!isLoading">{{ $t('auth.forgotSubmit') }}</span>
          <span v-else>{{ $t('common.loading') }}</span>
        </button>
      </div>
    </form>
  </div>
</template>

<script lang="ts" setup>
import { ref } from 'vue'
import { requestPasswordReset } from '@/api/auth'

/**
 * spec 07 §3: `POST /api/auth/password-reset/request` is always 202,
 * whether the address exists, is malformed or is over its rate limit — the
 * UI mirrors that: the same "check your inbox" panel is shown regardless of
 * the outcome, on submit, never conditioned on the response (criterion 10).
 */
const email = ref('')
const isLoading = ref(false)
const submitted = ref(false)

async function handleSubmit() {
  isLoading.value = true
  try {
    await requestPasswordReset(email.value)
  } catch {
    // Best-effort: the server contract is "always 202"; a network failure
    // here still shows the same panel, never an error that could hint
    // whether the address exists.
  } finally {
    isLoading.value = false
    submitted.value = true
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
  margin-bottom: 1.5rem;
  color: var(--color-primary);
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

.form-success {
  text-align: center;
  padding: 0.75rem;
  background-color: var(--color-success-bg);
  color: var(--color-success);
  border-radius: 4px;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
</style>
