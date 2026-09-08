<template>
  <div class="app-container">
    <header class="app-header">
      <div class="header-content">
        <h1 class="app-title">{{ $t('appName') }}</h1>
        <nav class="app-nav">
          <router-link to="/" class="nav-link">{{ $t('nav.home') }}</router-link>
          <router-link v-if="!isAuthenticated" to="/login" class="nav-link">{{ $t('nav.login') }}</router-link>
          <router-link v-if="!isAuthenticated" to="/register" class="nav-link">{{ $t('nav.register') }}</router-link>
          <router-link v-if="isAuthenticated" to="/workspace" class="nav-link">{{ $t('nav.workspace') }}</router-link>
          <button v-if="isAuthenticated" @click="handleLogout" class="nav-link logout-btn">{{ $t('nav.logout') }}</button>
        </nav>
        <div class="language-switcher">
          <select v-model="currentLocale" @change="changeLanguage" class="language-select">
            <option v-for="locale in locales" :key="locale" :value="locale">
              {{ $t(`languages.${locale}`) }}
            </option>
          </select>
        </div>
      </div>
    </header>
    
    <div v-if="isAuthenticated" class="user-info">
      <span>{{ $t('common.welcome') }}, {{ user?.displayName }}!</span>
    </div>
    
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<script lang="ts" setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useI18n } from 'vue-i18n'
import { SUPPORTED_LOCALES, type Locale } from '@/i18n'

const { locale } = useI18n()
const authStore = useAuthStore()
const router = useRouter()

const currentLocale = ref<Locale>(locale.value as Locale)
const locales = SUPPORTED_LOCALES

const isAuthenticated = computed(() => authStore.isAuthenticated)
const user = computed(() => authStore.user)

watch(locale, (newLocale) => {
  currentLocale.value = newLocale as Locale
})

const changeLanguage = () => {
  locale.value = currentLocale.value
  localStorage.setItem('fip-language', currentLocale.value)
}

const handleLogout = async () => {
  try {
    await authStore.logout()
    await router.push('/')
  } catch (error) {
    console.error('Logout failed:', error)
  }
}
</script>

<style scoped>
.app-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background-color: var(--color-background);
  color: var(--color-text);
}

.app-header {
  background-color: var(--color-header);
  border-bottom: 1px solid var(--color-border);
  padding: 1rem 2rem;
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
  gap: 1rem;
}

.app-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--color-primary);
  margin: 0;
  flex-shrink: 0;
}

.app-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: center;
}

.nav-link {
  padding: 0.5rem 1rem;
  border: none;
  background: none;
  color: var(--color-text);
  text-decoration: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 1rem;
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

.language-switcher {
  display: flex;
  align-items: center;
}

.language-select {
  padding: 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background-color: var(--color-background);
  color: var(--color-text);
  cursor: pointer;
  font-size: 1rem;
}

.language-select:hover,
.language-select:focus {
  outline: none;
  border-color: var(--color-primary);
}

.user-info {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0.5rem 2rem;
  background-color: var(--color-user-info);
  border-bottom: 1px solid var(--color-border);
  color: var(--color-user-info-text);
  font-size: 0.9rem;
}

.app-main {
  flex: 1;
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
  width: 100%;
}

@media (max-width: 768px) {
  .header-content {
    flex-direction: column;
    align-items: stretch;
  }

  .app-nav {
    justify-content: center;
  }

  .app-main {
    padding: 1rem;
  }

  .user-info {
    padding: 0.5rem 1rem;
  }
}
</style>
