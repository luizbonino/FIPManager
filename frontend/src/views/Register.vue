<template>
  <div class="auth-form">
    <h1>{{ $t('auth.registerTitle') }}</h1>
    
    <form @submit.prevent="handleSubmit" class="form">
      <div class="form-group">
        <label for="displayName">{{ $t('auth.displayNameLabel') }}</label>
        <input
          id="displayName"
          v-model="displayName"
          type="text"
          :placeholder="$t('auth.displayNamePlaceholder')"
          required
          @blur="validateDisplayName"
        />
        <span v-if="displayNameError" class="error-message">{{ displayNameError }}</span>
      </div>

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
          @blur="validatePassword"
        />
        <span v-if="passwordError" class="error-message">{{ passwordError }}</span>
      </div>

      <div class="form-group">
        <label for="confirmPassword">{{ $t('auth.confirmPasswordLabel') }}</label>
        <input
          id="confirmPassword"
          v-model="confirmPassword"
          type="password"
          :placeholder="$t('auth.confirmPasswordPlaceholder')"
          required
          @blur="validateConfirmPassword"
        />
        <span v-if="confirmPasswordError" class="error-message">{{ confirmPasswordError }}</span>
      </div>

      <div class="form-group">
        <label for="language">{{ $t('auth.languageLabel') }}</label>
        <select id="language" v-model="language" class="language-select">
          <option v-for="locale in locales" :key="locale" :value="locale">
            {{ $t(`languages.${locale}`) }}
          </option>
        </select>
      </div>

      <div class="form-group checkbox-group">
        <label class="checkbox-label">
          <input v-model="privacyAccepted" type="checkbox" required />
          <span>{{ $t('privacy.accept') }}</span>
        </label>
        <router-link to="/privacy" target="_blank" class="privacy-inline-link">{{ $t('privacy.link') }}</router-link>
        <span v-if="privacyError" class="error-message">{{ $t('privacy.required') }}</span>
      </div>

      <div class="form-actions">
        <button type="submit" :disabled="isLoading || !canSubmit" class="btn btn-primary">
          <span v-if="!isLoading">{{ $t('auth.submitRegister') }}</span>
          <span v-else>{{ $t('common.loading') }}</span>
        </button>
      </div>

      <div v-if="error" class="form-error">{{ error }}</div>
    </form>

    <div class="auth-footer">
      <router-link to="/login">{{ $t('auth.alreadyHaveAccount') }} {{ $t('auth.submitLogin') }}</router-link>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useI18n } from 'vue-i18n'
import { SUPPORTED_LOCALES, type Locale } from '@/i18n'
import { getPrivacyNotice, type PrivacyNotice } from '@/api/privacy'

const { t, locale: uiLocale } = useI18n()

const displayName = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const language = ref<Locale>('en')
const privacyAccepted = ref(false)
const privacyError = ref(false)

const displayNameError = ref<string | null>(null)
const emailError = ref<string | null>(null)
const passwordError = ref<string | null>(null)
const confirmPasswordError = ref<string | null>(null)
const error = ref<string | null>(null)
const isLoading = ref(false)

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const locales = SUPPORTED_LOCALES

// spec 05 §2: the version sent as `privacyAcceptedVersion` comes from
// `GET /api/privacy` itself, not typed by hand, so a stale tab can never
// submit a version the server no longer recognises.
const privacyNotice = ref<PrivacyNotice | null>(null)

const canSubmit = computed(() => privacyAccepted.value && privacyNotice.value !== null)

onMounted(async () => {
  try {
    privacyNotice.value = await getPrivacyNotice(uiLocale.value)
  } catch {
    privacyNotice.value = null
  }
})

const validateDisplayName = () => {
  if (!displayName.value.trim()) {
    displayNameError.value = t('validation.displayNameRequired')
    return false
  }
  displayNameError.value = null
  return true
}

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

const validatePassword = () => {
  if (!password.value) {
    passwordError.value = t('validation.required')
    return false
  }
  if (password.value.length < 10) {
    passwordError.value = t('validation.passwordTooShort')
    return false
  }
  if (password.value.length > 128) {
    passwordError.value = t('validation.passwordTooLong')
    return false
  }
  passwordError.value = null
  return true
}

const validateConfirmPassword = () => {
  if (!confirmPassword.value) {
    confirmPasswordError.value = t('validation.required')
    return false
  }
  if (password.value !== confirmPassword.value) {
    confirmPasswordError.value = t('validation.passwordsDontMatch')
    return false
  }
  confirmPasswordError.value = null
  return true
}

const validateAll = () => {
  return (
    validateDisplayName() &&
    validateEmail() &&
    validatePassword() &&
    validateConfirmPassword()
  )
}

const handleSubmit = async () => {
  privacyError.value = !privacyAccepted.value
  if (!validateAll() || !canSubmit.value) return

  isLoading.value = true
  error.value = null

  try {
    await authStore.register(
      email.value,
      password.value,
      displayName.value,
      language.value,
      privacyNotice.value?.version
    )
    const redirect = route.query.redirect as string || '/workspace'
    await router.push(redirect)
  } catch (err) {
    error.value = t('errors.emailExists')
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

.form-group input,
.form-group select {
  padding: 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background-color: var(--color-background);
  color: var(--color-text);
  font-size: 1rem;
}

.form-group input:focus,
.form-group select:focus {
  outline: none;
  border-color: var(--color-primary);
}

.error-message {
  color: var(--color-error);
  font-size: 0.875rem;
}

.checkbox-group {
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: normal;
  min-height: 44px;
}

.checkbox-label input[type='checkbox'] {
  width: 1.2rem;
  height: 1.2rem;
}

.privacy-inline-link {
  color: var(--color-link);
  font-size: 0.9rem;
}

.form-error {
  color: var(--color-error);
  text-align: center;
  padding: 0.5rem;
  background-color: var(--color-error-bg);
  border-radius: 4px;
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
}

.auth-footer a {
  color: var(--color-link);
  text-decoration: none;
}

.auth-footer a:hover {
  text-decoration: underline;
}

.language-select {
  padding: 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background-color: var(--color-background);
  color: var(--color-text);
  font-size: 1rem;
  cursor: pointer;
}

@media (max-width: 480px) {
  .auth-form {
    margin: 1rem;
    padding: 0;
  }
}
</style>
