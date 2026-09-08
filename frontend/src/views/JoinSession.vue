<template>
  <div class="join-session-view">
    <div v-if="loading" class="loading">
      <p>{{ $t('common.loading') }}</p>
    </div>

    <div v-else-if="notFound" class="message-box">
      <p>{{ $t('join.invalidCode') }}</p>
    </div>

    <div v-else-if="session" class="join-content">
      <header class="join-header">
        <p class="eyebrow">{{ $t('join.sessionTitle') }}</p>
        <h1>{{ session.title }}</h1>
        <p class="questionnaire-title">{{ $t('join.questionnaire') }}: {{ questionnaireTitle }}</p>
        <p class="facilitator">{{ $t('join.facilitator') }}: {{ session.facilitatorName }}</p>
        <LanguageSwitcher />
      </header>

      <div v-if="session.status === 'closed'" class="message-box closed">
        <p>{{ $t('join.closed') }}</p>
        <router-link v-if="knownFipId" :to="`/fips/${knownFipId}`" class="btn btn-secondary">
          {{ $t('common.view') }}
        </router-link>
      </div>

      <template v-else>
        <router-link v-if="knownFipId" :to="`/fips/${knownFipId}/edit`" class="btn btn-primary continue-btn">
          {{ $t('join.continueFip') }}
        </router-link>

        <form class="community-form" @submit.prevent="onSubmit">
          <h2>{{ $t('community.heading') }}</h2>

          <label class="field">
            <span>{{ $t('community.name') }} *</span>
            <input v-model="community.name" type="text" required :placeholder="$t('community.namePlaceholder')" />
          </label>

          <label class="field">
            <span>{{ $t('community.description') }}</span>
            <textarea v-model="community.description" rows="3" />
          </label>

          <label class="field">
            <span>{{ $t('community.domain') }}</span>
            <input v-model="community.domain" type="text" :placeholder="$t('community.domainPlaceholder')" />
          </label>

          <label class="field">
            <span>{{ $t('community.dataSteward') }}</span>
            <input
              v-model="orcid"
              type="text"
              :placeholder="$t('community.dataStewardPlaceholder')"
              @blur="validateOrcid"
            />
            <span v-if="orcidError" class="field-error">{{ $t('community.orcidInvalid') }}</span>
          </label>

          <p v-if="submitError" class="form-error">{{ submitError }}</p>

          <button type="submit" class="btn btn-primary" :disabled="submitting">
            {{ $t('join.startFip') }}
          </button>
        </form>
      </template>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ApiResponseError } from '@/api/client'
import { createFip } from '@/api/fips'
import { getSessionFip, rememberSessionFip, setToken } from '@/lib/editTokens'
import { resolveLang } from '@/lib/lang'
import { SUPPORTED_LOCALES } from '@/i18n'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import { useSessionStore } from '@/stores/session'
import type { SessionPublicOut } from '@/types/api'

// Spec 02 §2.1: replaces the JoinSession scaffold.
const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const sessionStore = useSessionStore()

const loading = ref(true)
const notFound = ref(false)
const submitting = ref(false)
const submitError = ref<string | null>(null)
const orcidError = ref(false)

const community = ref({ name: '', description: '', domain: '' })
const orcid = ref('')

const session = computed<SessionPublicOut | null>(() => sessionStore.publicSession)

const questionnaireTitle = computed(() =>
  session.value ? resolveLang(session.value.questionnaireTitle, locale.value) ?? '' : ''
)

const knownFipId = computed(() => {
  const s = session.value
  return s ? getSessionFip(s.id) : null
})

const ORCID_PATTERN = /^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$/

function validateOrcid() {
  orcidError.value = orcid.value.trim() !== '' && !ORCID_PATTERN.test(orcid.value.trim())
}

async function load() {
  loading.value = true
  notFound.value = false
  const joinCode = String(route.params.joinCode ?? '').toUpperCase()
  try {
    await sessionStore.loadByCode(joinCode)
    // §2.1 step 2: if no stored preference, adopt the session's default
    // language before rendering its content; a stored preference or the
    // switcher always wins.
    let stored: string | null = null
    try {
      stored = localStorage.getItem('fip-language')
    } catch {
      stored = null
    }
    const defaultLang = sessionStore.publicSession?.defaultLanguage
    if (!stored && defaultLang && (SUPPORTED_LOCALES as string[]).includes(defaultLang)) {
      locale.value = defaultLang as (typeof SUPPORTED_LOCALES)[number]
    }
  } catch (err) {
    if (err instanceof ApiResponseError && err.status === 404) {
      notFound.value = true
    } else {
      notFound.value = true
    }
  } finally {
    loading.value = false
  }
}

async function onSubmit() {
  validateOrcid()
  const s = session.value
  if (!s) return
  submitting.value = true
  submitError.value = null
  const joinCode = String(route.params.joinCode ?? '').toUpperCase()

  try {
    const created = await createFip({
      questionnaireRef: s.questionnaireRef,
      sessionId: s.id,
      joinCode,
      language: locale.value,
      community: {
        name: community.value.name,
        description: community.value.description || null,
        domain: community.value.domain || null,
        links: [],
        dataSteward: orcid.value.trim() ? { orcid: orcid.value.trim() } : null,
      },
      answers: [],
    })
    // The edit token is returned exactly once — store it before navigating (spec 02 §2.1).
    if (created.editToken) {
      setToken(created.id, created.editToken)
    }
    rememberSessionFip(s.id, created.id)
    await router.replace(`/fips/${created.id}/edit`)
  } catch (err) {
    if (err instanceof ApiResponseError && err.status === 409) {
      submitError.value = t('join.closed')
    } else if (err instanceof ApiResponseError && err.status === 403) {
      submitError.value = t('join.invalidCode')
    } else {
      submitError.value = t('errors.serverError')
    }
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.join-session-view {
  max-width: 640px;
  margin: 0 auto;
  padding: 1rem;
}

.loading,
.message-box {
  text-align: center;
  padding: 2rem 1rem;
}

.message-box.closed {
  background-color: var(--color-hover);
  border-radius: var(--border-radius-md);
}

.join-header {
  text-align: center;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 1.5rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.35rem;
}

.eyebrow {
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.join-header h1 {
  margin: 0;
  color: var(--color-primary);
}

.questionnaire-title,
.facilitator {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}

.continue-btn {
  display: block;
  text-align: center;
  margin-bottom: 1.5rem;
}

.community-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.field input,
.field textarea {
  min-height: 44px;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  font-size: 1rem;
  font-family: inherit;
}

.field-error,
.form-error {
  color: var(--color-error);
  font-size: var(--font-size-sm);
}

.btn {
  min-height: 44px;
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: var(--border-radius-sm);
  font-size: 1rem;
  font-weight: 500;
  text-decoration: none;
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
  opacity: 0.7;
}
</style>
