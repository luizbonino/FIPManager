import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import Home from '@/views/Home.vue'
import Login from '@/views/Login.vue'
import Register from '@/views/Register.vue'
import Workspace from '@/views/Workspace.vue'
import FipDetail from '@/views/FipDetail.vue'
import JoinSession from '@/views/JoinSession.vue'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Home',
    component: Home,
    meta: { requiresAuth: false },
  },
  {
    path: '/login',
    name: 'Login',
    component: Login,
    meta: { requiresAuth: false },
  },
  {
    path: '/register',
    name: 'Register',
    component: Register,
    meta: { requiresAuth: false },
  },
  {
    path: '/workspace',
    name: 'Workspace',
    component: Workspace,
    meta: { requiresAuth: true },
  },
  {
    path: '/fips/:id',
    name: 'FipDetail',
    component: FipDetail,
    meta: { requiresAuth: false },
    props: true,
  },
  {
    path: '/join/:joinCode',
    name: 'JoinSession',
    component: JoinSession,
    meta: { requiresAuth: false },
    props: true,
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

let sessionRestored = false

router.beforeEach(async (to) => {
  const authStore = useAuthStore()

  // Restore the cookie session once before the first guarded decision,
  // otherwise a returning user with a valid cookie is bounced to /login.
  if (!sessionRestored) {
    sessionRestored = true
    await authStore.restoreSession()
  }
  
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return {
      path: '/login',
      query: { redirect: to.fullPath },
    }
  }
  
  if ((to.name === 'Login' || to.name === 'Register') && authStore.isAuthenticated) {
    return { path: '/workspace' }
  }

  return true
})

export { routes }
export default router
