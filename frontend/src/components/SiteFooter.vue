<template>
  <footer class="site-footer no-print">
    <span class="footer-app-name">{{ $t('appName') }}</span>
    <router-link to="/privacy" class="footer-link">{{ $t('privacy.link') }}</router-link>
  </footer>
</template>

<script lang="ts" setup>
// spec 05 §2: rendered by App.vue under `<router-view>`, on every page.
</script>

<style scoped>
.site-footer {
  max-width: 1200px;
  margin: 0 auto;
  padding: 1.5rem 1rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  flex-wrap: wrap;
  border-top: 1px solid var(--color-border);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}

.footer-app-name {
  font-weight: var(--font-weight-medium);
}

.footer-link {
  color: var(--color-link);
}
</style>
