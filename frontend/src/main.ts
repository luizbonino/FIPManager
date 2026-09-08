import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router/index'
import { setupI18n } from './i18n'
import './assets/styles.css'

const pinia = createPinia()
const i18n = setupI18n()

const app = createApp(App)

app.use(pinia)
app.use(router)
app.use(i18n)

app.mount('#app')
