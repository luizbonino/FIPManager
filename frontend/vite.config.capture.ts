// Standalone Vite config for the screenshot-capture run (scripts/capture-screenshots.mjs).
// Deliberately separate from vite.config.ts so it never touches the shared
// dev-server config another agent may be using concurrently in this checkout.
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

const backendPort = process.env.FIPM_CAPTURE_BACKEND_PORT || '8099'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: Number(process.env.FIPM_CAPTURE_FRONTEND_PORT || '5199'),
    strictPort: true,
    proxy: {
      '/api': {
        target: `http://localhost:${backendPort}`,
        changeOrigin: true,
      },
    },
  },
})
