<template>
  <div class="app-container">
    <header class="app-header">
      <div class="header-content">
        <h1 class="app-title">{{ $t('appName') }}</h1>
        <div class="header-actions">
          <nav class="app-nav">
            <router-link to="/" class="nav-link">{{ $t('nav.home') }}</router-link>
            <router-link to="/knowledge-models" class="nav-link">{{ $t('nav.knowledgeModels') }}</router-link>
            <router-link v-if="networkEnabled" to="/network" class="nav-link">{{ $t('network.navLabel') }}</router-link>
            <router-link v-if="dashboardEnabled" to="/dashboard" class="nav-link">{{ $t('dashboard.navLabel') }}</router-link>
            <router-link v-if="!isAuthenticated" to="/login" class="nav-link">{{ $t('nav.login') }}</router-link>
            <router-link v-if="!isAuthenticated" to="/register" class="nav-link">{{ $t('nav.register') }}</router-link>
            <router-link v-if="isAuthenticated" to="/workspace" class="nav-link">{{ $t('nav.workspace') }}</router-link>
            <router-link v-if="isAdmin" to="/admin" class="nav-link">{{ $t('nav.admin') }}</router-link>
            <button v-if="isAuthenticated" @click="handleLogout" class="nav-link logout-btn">{{ $t('nav.logout') }}</button>
          </nav>
          <LanguageSwitcher />
        </div>
      </div>
    </header>

    <main class="app-main">
      <router-view />
    </main>

    <SiteFooter />
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { get } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import SiteFooter from '@/components/SiteFooter.vue'

const authStore = useAuthStore()
const router = useRouter()

const isAuthenticated = computed(() => authStore.isAuthenticated)

// spec 11 §3.4/§3.5: the Network FIPs nav entry is hidden when
// `GET /api/health`'s `networkEnabled` is false. Optimistically shown
// (like FeedbackForm.vue's `feedbackEnabled` check) until the health
// check says otherwise — a failed/slow health check should not flicker
// or permanently hide navigation the deployment actually offers.
const networkEnabled = ref(true)
// spec 13 §7.3: the Dashboard nav entry is hidden when `GET /api/health`
// reports `dashboardEnabled: false` — same optimistic-until-known idiom.
const dashboardEnabled = ref(true)
// spec 05 §1: the "Admin" nav link — and only that link — reflects role;
// the /admin route itself still renders `common.notFound` for anyone else.
const isAdmin = computed(() => authStore.user?.role === 'admin')

const handleLogout = async () => {
  try {
    await authStore.logout()
    await router.push('/')
  } catch (error) {
    console.error('Logout failed:', error)
  }
}

onMounted(async () => {
  try {
    const health = await get<Record<string, unknown>>('/health')
    if (health.networkEnabled === false) {
      networkEnabled.value = false
    }
    if (health.dashboardEnabled === false) {
      dashboardEnabled.value = false
    }
  } catch {
    // Best-effort only, like FeedbackForm.vue's own health check — leave
    // the nav entry shown; the Network FIPs pages themselves render
    // `network_disabled` if the deployment really has it off.
  }
})
</script>

<style scoped>
.app-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background-color: var(--color-background);
  color: var(--color-text);
}

/* Mobile-first: one compact row (title left, nav + language switcher
   right), wrapping to a second row only if it doesn't fit. Keeps the
   header height low on narrow phones (target <= 96px at 375px). */
.app-header {
  background-color: var(--color-header);
  border-bottom: 1px solid var(--color-border);
  padding: 0.5rem 1rem;
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-content {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.4rem;
}

.app-title {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--color-primary);
  margin: 0;
  flex-shrink: 0;
}

.header-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 0.4rem;
  flex: 1 1 auto;
  min-width: 0;
}

.app-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  align-items: center;
}

.nav-link {
  padding: 0 0.5rem;
  border: none;
  background: none;
  color: var(--color-text);
  text-decoration: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.8rem;
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  transition: background-color 0.2s ease, color 0.2s ease;
}

.nav-link:hover {
  background-color: var(--color-hover);
  color: var(--color-primary);
}

.nav-link.router-link-exact-active {
  background-color: var(--color-primary);
  color: var(--color-primary-text);
}

.logout-btn {
  background: none;
  border: none;
  cursor: pointer;
  font: inherit;
}

.user-info {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0.5rem 1rem;
  background-color: var(--color-user-info);
  border-bottom: 1px solid var(--color-border);
  color: var(--color-user-info-text);
  font-size: 0.9rem;
}

.app-main {
  flex: 1;
  max-width: 1200px;
  margin: 0 auto;
  padding: 1rem;
  width: 100%;
}

/* The language switcher is a separate component (owned elsewhere); style
   its internal select from here so it matches the compact mobile header
   without editing that file. Long option text is ellipsized on narrow
   screens instead of forcing the select (and header) wide. */
:deep(.language-select) {
  width: auto;
  max-width: 6.2rem;
  min-height: 44px;
  padding: 0 0.4rem;
  font-size: 0.8rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (min-width: 640px) {
  .app-header {
    padding: 1rem 2rem;
  }

  .app-title {
    font-size: 1.5rem;
  }

  .app-nav {
    gap: 1rem;
  }

  .nav-link {
    padding: 0.5rem 1rem;
    font-size: 1rem;
  }

  .header-actions {
    gap: 1rem;
  }

  :deep(.language-select) {
    max-width: none;
    padding: 0.5rem;
    font-size: 1rem;
  }

  .user-info {
    padding: 0.5rem 2rem;
  }

  .app-main {
    padding: 2rem;
  }
}
</style>
