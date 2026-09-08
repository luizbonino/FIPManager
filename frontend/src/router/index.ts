import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import Home from '@/views/Home.vue'
import Login from '@/views/Login.vue'
import Register from '@/views/Register.vue'
import Workspace from '@/views/Workspace.vue'
import JoinSession from '@/views/JoinSession.vue'
import FipRead from '@/views/FipRead.vue'
import FipEditor from '@/views/FipEditor.vue'
import FipNew from '@/views/FipNew.vue'
import SessionNew from '@/views/SessionNew.vue'
import SessionDetail from '@/views/SessionDetail.vue'
import SessionMatrix from '@/views/SessionMatrix.vue'
import { useAuthStore } from '@/stores/auth'
import { useFipEditorStore } from '@/stores/fipEditor'

// Spec 02 §6.1. Route `name` = component name throughout.
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
    path: '/join/:joinCode',
    name: 'JoinSession',
    component: JoinSession,
    meta: { requiresAuth: false },
    props: true,
  },
  {
    path: '/fips/:id',
    name: 'FipRead',
    component: FipRead,
    meta: { requiresAuth: false },
    props: true,
  },
  {
    // Edit rights (a stored edit token, or ownership) are checked inside
    // FipEditor.vue itself, not by this guard (spec 02 §6.1).
    path: '/fips/:id/edit',
    name: 'FipEditor',
    component: FipEditor,
    meta: { requiresAuth: false },
    props: true,
  },
  {
    path: '/workspace',
    name: 'Workspace',
    component: Workspace,
    meta: { requiresAuth: true },
  },
  {
    path: '/fips/new',
    name: 'FipNew',
    component: FipNew,
    meta: { requiresAuth: true },
  },
  {
    path: '/sessions/new',
    name: 'SessionNew',
    component: SessionNew,
    meta: { requiresAuth: true },
  },
  {
    path: '/sessions/:id',
    name: 'SessionDetail',
    component: SessionDetail,
    meta: { requiresAuth: true },
    props: true,
  },
  {
    // Reserved now: a placeholder so the link never 404s (spec 02 §4.2).
    path: '/sessions/:id/matrix',
    name: 'SessionMatrix',
    component: SessionMatrix,
    meta: { requiresAuth: true },
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

router.beforeEach(async (to, from) => {
  const authStore = useAuthStore()

  // Restore the cookie session once before the first guarded decision,
  // otherwise a returning user with a valid cookie is bounced to /login.
  if (!sessionRestored) {
    sessionRestored = true
    await authStore.restoreSession()
  }

  // FipEditor autosaves on an 800ms debounce; flush any pending save before
  // leaving so no keystroke is lost (spec 02 §6.1's "beforeRouteLeave guard").
  if (from.name === 'FipEditor' && to.name !== 'FipEditor') {
    const fipEditorStore = useFipEditorStore()
    await fipEditorStore.flush()
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
