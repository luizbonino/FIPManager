<template>
  <div class="join-session-view">
    <div v-if="success" class="success-message">
      <h2>{{ $t('common.success') }}</h2>
      <p>{{ $t('session.joinSuccess') }}</p>
      <router-link to="/workspace" class="btn btn-primary">{{ $t('common.back') }}</router-link>
    </div>

    <div v-else class="join-session-form">
      <h1>{{ $t('session.joinTitle') }}</h1>
      
      <form @submit.prevent="handleSubmit" class="form">
        <div class="form-group">
          <label for="joinCode">{{ $t('session.joinCodeLabel') }}</label>
          <input
            id="joinCode"
            v-model="joinCode"
            type="text"
            :placeholder="$t('session.joinCodePlaceholder')"
            required
            @blur="validateJoinCode"
          />
          <span v-if="joinCodeError" class="error-message">{{ joinCodeError }}</span>
        </div>

        <div class="form-actions">
          <button type="submit" :disabled="isLoading" class="btn btn-primary">
            <span v-if="!isLoading">{{ $t('session.submitJoin') }}</span>
            <span v-else>{{ $t('common.loading') }}</span>
          </button>
        </div>

        <div v-if="error" class="form-error">{{ error }}</div>
      </form>

      <div class="session-info" v-if="sessionDetails">
        <h3>{{ $t('session.sessionInfo') }}</h3>
        <p><strong>{{ $t('common.name') }}:</strong> {{ sessionDetails.name }}</p>
        <p><strong>{{ $t('common.id') }}:</strong> {{ sessionDetails.id }}</p>
        <p><strong>{{ $t('common.status') }}:</strong> 
          <span :class="sessionDetails.isActive ? 'status-active' : 'status-inactive'">
            {{ sessionDetails.isActive ? $t('common.active') : $t('common.inactive') }}
          </span>
        </p>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { get, post } from '@/api/client'
import { useI18n } from 'vue-i18n'

type Session = {
  id: string
  name: string
  joinCode: string
  isActive: boolean
  createdAt: string
}

type Fip = {
  id: string
  title: string
  sessionId: string
}

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const joinCode = ref('')
const joinCodeError = ref<string | null>(null)
const error = ref<string | null>(null)
const isLoading = ref(false)
const success = ref(false)
const sessionDetails = ref<Session | null>(null)

// Get joinCode from route params
watch(() => route.params.joinCode, (newJoinCode) => {
  if (newJoinCode && typeof newJoinCode === 'string') {
    joinCode.value = newJoinCode.toUpperCase()
    validateJoinCode()
    fetchSessionDetails()
  }
}, { immediate: true })

const validateJoinCode = () => {
  if (!joinCode.value.trim()) {
    joinCodeError.value = t('validation.required')
    return false
  }
  if (joinCode.value.length < 6) {
    joinCodeError.value = t('session.invalidJoinCode')
    return false
  }
  joinCodeError.value = null
  return true
}

const fetchSessionDetails = async () => {
  if (!joinCode.value) return

  try {
    const response = await get<Session>(`/sessions/code/${joinCode.value}`)
    sessionDetails.value = response
    
    if (!response.isActive) {
      error.value = t('session.sessionClosed')
    }
  } catch (err) {
    sessionDetails.value = null
    // Don't show error yet, let the join attempt handle it
  }
}

const handleSubmit = async () => {
  if (!validateJoinCode()) return

  isLoading.value = true
  error.value = null

  try {
    const response = await post<Fip>('/fips', {
      sessionId: sessionDetails.value?.id || '',
      joinCode: joinCode.value,
    })

    success.value = true
    
    // Redirect to the FIP detail page after a brief delay
    setTimeout(() => {
      router.push(`/fips/${response.id}`)
    }, 2000)
  } catch (err) {
    error.value = t('session.invalidJoinCode')
    if (err instanceof Error && err.message.includes('closed')) {
      error.value = t('session.sessionClosed')
    }
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  if (joinCode.value) {
    validateJoinCode()
  }
})
</script>

<style scoped>
.join-session-view {
  max-width: 500px;
  margin: 2rem auto;
  padding: 1rem;
}

.join-session-view h1 {
  text-align: center;
  margin-bottom: 1.5rem;
  color: var(--color-primary);
}

.join-session-form {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
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
  text-transform: uppercase;
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

.session-info {
  margin-top: 1rem;
  padding: 1rem;
  background-color: var(--color-background);
  border: 1px solid var(--color-border);
  border-radius: 8px;
}

.session-info h3 {
  color: var(--color-primary);
  margin-bottom: 0.75rem;
  font-size: 1.125rem;
}

.session-info p {
  margin: 0.5rem 0;
  color: var(--color-text);
}

.session-info strong {
  color: var(--color-secondary);
}

.status-active {
  color: #22c55e;
  font-weight: 500;
}

.status-inactive {
  color: var(--color-error);
  font-weight: 500;
}

.success-message {
  text-align: center;
  padding: 2rem;
  color: var(--color-primary);
}

.success-message h2 {
  color: var(--color-primary);
  margin-bottom: 1rem;
}

.success-message .btn {
  margin-top: 1rem;
}

@media (max-width: 480px) {
  .join-session-view {
    margin: 1rem;
    padding: 0;
  }
}
</style>
