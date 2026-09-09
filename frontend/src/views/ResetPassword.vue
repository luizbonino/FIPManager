<template>
  <div class="auth-form">
    <h1>{{ $t('auth.resetTitle') }}</h1>

    <div v-if="expired" class="form-error">
      <p>{{ $t('auth.resetExpired') }}</p>
      <router-link to="/forgot-password">{{ $t('auth.requestNewLink') }}</router-link>
    </div>

    <div v-else-if="invalid" class="form-error">
      <p>{{ $t('auth.verifyInvalid') }}</p>
      <router-link to="/forgot-password">{{ $t('auth.requestNewLink') }}</router-link>
    </div>

    <form v-else @submit.prevent="handleSubmit" class="form">
      <div class="form-group">
        <label for="newPassword">{{ $t('auth.passwordLabel') }}</label>
        <input
          id="newPassword"
          v-model="newPassword"
          type="password"
          minlength="10"
          maxlength="128"
          autocomplete="new-password"
          required
        />
      </div>

      <div class="form-group">
        <label for="confirmPassword">{{ $t('auth.confirmPasswordLabel') }}</label>
        <input
          id="confirmPassword"
          v-model="confirmPassword"
          type="password"
          minlength="10"
          maxlength="128"
          autocomplete="new-password"
          required
        />
      </div>
      <span v-if="confirmPassword && !passwordsMatch" class="error-message">{{ $t('validation.passwordsDontMatch') }}</span>

      <div class="form-actions">
        <button type="submit" :disabled="!canSubmit || isLoading" class="btn btn-primary">
          <span v-if="!isLoading">{{ $t('auth.resetSubmit') }}</span>
          <span v-else>{{ $t('common.loading') }}</span>
        </button>
      </div>

      <p v-if="error" class="form-error">{{ error }}</p>
    </form>
  </div>
</template>

<script lang="ts" setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ApiResponseError } from '@/api/client'
import { confirmPasswordReset } from '@/api/auth'

/**
 * spec 07 §3: reads `?token=`, new password + confirm, Submit disabled
 * until both fields match at >= 10 chars (criterion 10). On 204, routes to
 * `/login` with a flash (`resetOk` query flag, read by `Login.vue`); on 410
 * `token_expired`, links back to `/forgot-password`; any other failure
 * (unknown/used/mismatched token) renders as invalid with the same link.
 */
const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const newPassword = ref('')
const confirmPassword = ref('')
const isLoading = ref(false)
const error = ref<string | null>(null)
const expired = ref(false)
const invalid = ref(false)

const token = computed(() => String(route.query.token ?? ''))
const passwordsMatch = computed(() => newPassword.value === confirmPassword.value)
const canSubmit = computed(
  () => newPassword.value.length >= 10 && confirmPassword.value.length >= 10 && passwordsMatch.value
)

async function handleSubmit() {
  if (!canSubmit.value) return
  isLoading.value = true
  error.value = null
  try {
    await confirmPasswordReset(token.value, newPassword.value)
    await router.push({ path: '/login', query: { resetOk: '1' } })
  } catch (err) {
    if (err instanceof ApiResponseError && err.status === 410) {
      expired.value = true
    } else if (err instanceof ApiResponseError && err.status === 400) {
      invalid.value = true
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

.error-message {
  color: var(--color-error);
  font-size: 0.875rem;
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
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
</style>
