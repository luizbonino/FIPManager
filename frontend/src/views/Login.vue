<template>
  <div class="auth-form">
    <h1>{{ $t('auth.loginTitle') }}</h1>

    <p v-if="resetOk" class="form-success">{{ $t('auth.resetOk') }}</p>

    <form @submit.prevent="handleSubmit" class="form">
      <div class="form-group">
        <label for="email">{{ $t('auth.emailLabel') }}</label>
        <input
          id="email"
          v-model="email"
          type="email"
          :placeholder="$t('auth.emailPlaceholder')"
          required
          @blur="validateEmail"
        />
        <span v-if="emailError" class="error-message">{{ emailError }}</span>
      </div>

      <div class="form-group">
        <label for="password">{{ $t('auth.passwordLabel') }}</label>
        <input
          id="password"
          v-model="password"
          type="password"
          :placeholder="$t('auth.passwordPlaceholder')"
          required
          minlength="10"
          maxlength="128"
        />
      </div>

      <div class="form-actions">
        <button type="submit" :disabled="isLoading" class="btn btn-primary">
          <span v-if="!isLoading">{{ $t('auth.submitLogin') }}</span>
          <span v-else>{{ $t('common.loading') }}</span>
        </button>
      </div>

      <div v-if="error" class="form-error">{{ error }}</div>
    </form>

    <div class="auth-footer">
      <router-link to="/forgot-password">{{ $t('auth.forgotPassword') }}</router-link>
      <router-link to="/register">{{ $t('auth.dontHaveAccount') }} {{ $t('auth.submitRegister') }}</router-link>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const email = ref('')
const password = ref('')
const emailError = ref<string | null>(null)
const error = ref<string | null>(null)
const isLoading = ref(false)

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
// spec 07 §3: ResetPassword.vue routes here with `?resetOk=1` on success.
const resetOk = !!route.query.resetOk

const validateEmail = () => {
  if (!email.value) {
    emailError.value = t('validation.required')
    return false
  }
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  if (!emailRegex.test(email.value)) {
    emailError.value = t('validation.emailInvalid')
    return false
  }
  emailError.value = null
  return true
}

const handleSubmit = async () => {
  if (!validateEmail()) return
  
  if (!password.value) {
    error.value = t('validation.required')
    return
  }

  isLoading.value = true
  error.value = null

  try {
    await authStore.login(email.value, password.value)
    const redirect = route.query.redirect as string || '/workspace'
    await router.push(redirect)
  } catch (err) {
    error.value = t('errors.invalidCredentials')
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
  margin: 0 0 1rem;
}

.form-actions {
  display: flex;
  justify-content: center;
}

.btn {
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 4px;
  background-color: var(--color-primary);
  color: var(--color-primary-text);
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.auth-footer {
  text-align: center;
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.auth-footer a {
  color: var(--color-link);
  text-decoration: none;
}

.auth-footer a:hover {
  text-decoration: underline;
}

@media (max-width: 480px) {
  .auth-form {
    margin: 1rem;
    padding: 0;
  }
}
</style>
