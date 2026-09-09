import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { get, post } from '@/api/client'

export type User = {
  id: string
  email: string
  displayName: string
  role: 'user' | 'admin'
  language: string
  createdAt: string
  updatedAt: string
  /** spec 05 §1: forces `/account/password` until cleared by a successful `POST /api/auth/password`. */
  mustChangePassword: boolean
  privacyAcceptedVersion: string | null
  /** spec 07 §2: null until `POST /api/auth/verify-email` succeeds. */
  emailVerifiedAt: string | null
}

/** `GET /api/auth/me` (spec 07 §2): `UserOut` plus the `FIPM_REQUIRE_EMAIL_VERIFICATION` setting. */
type MeOut = User & { verificationRequired: boolean }

type AuthState = {
  me: User | null
  isLoading: boolean
  error: string | null
  /** spec 07 §2: the `FIPM_REQUIRE_EMAIL_VERIFICATION` setting, read off `GET /api/auth/me`; `false` while signed out. */
  verificationRequired: boolean
}

export const useAuthStore = defineStore('auth', () => {
  const state = ref<AuthState>({
    me: null,
    isLoading: false,
    error: null,
    verificationRequired: false,
  })

  const isAuthenticated = computed(() => state.value.me !== null)
  const user = computed(() => state.value.me)
  /** spec 07 §3: Workspace's verify banner condition, `verificationRequired && !emailVerifiedAt`. */
  const needsEmailVerification = computed(
    () => state.value.verificationRequired && !state.value.me?.emailVerifiedAt
  )

  async function restoreSession() {
    state.value.isLoading = true
    state.value.error = null

    try {
      const { verificationRequired, ...userFields } = await get<MeOut>('/auth/me')
      state.value.me = userFields
      state.value.verificationRequired = verificationRequired
    } catch {
      // Not signed in is a normal state, not an error.
      state.value.me = null
      state.value.verificationRequired = false
    } finally {
      state.value.isLoading = false
    }
  }

  async function login(email: string, password: string) {
    state.value.isLoading = true
    state.value.error = null

    try {
      const response = await post<User>('/auth/login', {
        email,
        password,
      })
      state.value.me = response
      await restoreSession()
    } catch (error) {
      state.value.error = 'Invalid email or password'
      state.value.me = null
      throw error
    } finally {
      state.value.isLoading = false
    }
  }

  async function register(
    email: string,
    password: string,
    displayName: string,
    language?: string,
    privacyAcceptedVersion?: string
  ) {
    state.value.isLoading = true
    state.value.error = null

    try {
      const response = await post<User>('/auth/register', {
        email,
        password,
        displayName,
        language: language || 'en',
        // spec 05 §2: required, non-empty; a mismatch against the current
        // notice version -> `400 privacy_version_mismatch`.
        privacyAcceptedVersion,
      })
      state.value.me = response
      await restoreSession()
    } catch (error) {
      state.value.error = 'Registration failed'
      state.value.me = null
      throw error
    } finally {
      state.value.isLoading = false
    }
  }

  /** `POST /api/auth/password` (spec 01 §3, spec 05 §1): clears `mustChangePassword` on success. */
  async function changePassword(currentPassword: string, newPassword: string) {
    await post<void>('/auth/password', { currentPassword, newPassword })
    await restoreSession()
  }

  async function logout() {
    state.value.isLoading = true
    state.value.error = null

    try {
      await post<void>('/auth/logout')
      state.value.me = null
    } catch (error) {
      state.value.error = 'Failed to logout'
    } finally {
      state.value.isLoading = false
    }
  }

  return {
    state,
    isAuthenticated,
    user,
    needsEmailVerification,
    restoreSession,
    login,
    register,
    changePassword,
    logout,
  }
})
