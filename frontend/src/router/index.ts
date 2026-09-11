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
import KnowledgeModelList from '@/views/KnowledgeModelList.vue'
import KnowledgeModelNew from '@/views/KnowledgeModelNew.vue'
import KnowledgeModelRead from '@/views/KnowledgeModelRead.vue'
import KnowledgeModelEditor from '@/views/KnowledgeModelEditor.vue'
import KnowledgeModelPrint from '@/views/KnowledgeModelPrint.vue'
import Admin from '@/views/Admin.vue'
import ChangePassword from '@/views/ChangePassword.vue'
import Privacy from '@/views/Privacy.vue'
import Guide from '@/views/Guide.vue'
import ForgotPassword from '@/views/ForgotPassword.vue'
import ResetPassword from '@/views/ResetPassword.vue'
import VerifyEmail from '@/views/VerifyEmail.vue'
import FipMigrate from '@/views/FipMigrate.vue'
import NetworkFipList from '@/views/NetworkFipList.vue'
import NetworkFipDetail from '@/views/NetworkFipDetail.vue'
import DashboardHome from '@/views/DashboardHome.vue'
import DashboardCoverage from '@/views/DashboardCoverage.vue'
import DashboardAdoption from '@/views/DashboardAdoption.vue'
import DashboardSimilarity from '@/views/DashboardSimilarity.vue'
import DashboardGaps from '@/views/DashboardGaps.vue'
import DashboardEvolution from '@/views/DashboardEvolution.vue'
import { useAuthStore } from '@/stores/auth'
import { useFipEditorStore } from '@/stores/fipEditor'
import { useKmEditorStore } from '@/stores/kmEditor'

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
    // spec 05 §2: public — participants have no account (A2).
    path: '/privacy',
    name: 'Privacy',
    component: Privacy,
    meta: { requiresAuth: false },
  },
  {
    // Public, no auth: participants have no account (same reasoning as
    // Privacy above), and administrators reading their guide before
    // provisioning an instance are not signed in yet either.
    path: '/guide',
    name: 'GuideParticipant',
    component: Guide,
    meta: { requiresAuth: false },
    props: { guideId: 'participant' },
  },
  {
    path: '/guide/admin',
    name: 'GuideAdmin',
    component: Guide,
    meta: { requiresAuth: false },
    props: { guideId: 'administrator' },
  },
  {
    path: '/forgot-password',
    name: 'ForgotPassword',
    component: ForgotPassword,
    meta: { requiresAuth: false },
  },
  {
    path: '/reset-password',
    name: 'ResetPassword',
    component: ResetPassword,
    meta: { requiresAuth: false },
  },
  {
    // spec 07 §2: matches the link the backend mails, `{FIPM_BASE_URL}/verify?token=…`.
    path: '/verify',
    name: 'VerifyEmail',
    component: VerifyEmail,
    meta: { requiresAuth: false },
  },
  {
    // spec 05 §1: the view itself renders `common.notFound` for a
    // signed-in non-admin and calls no `/api/admin/*` route.
    path: '/admin',
    name: 'Admin',
    component: Admin,
    meta: { requiresAuth: true },
  },
  {
    // spec 05 §1: reached either voluntarily or via the `mustChangePassword`
    // redirect below; `requiresAuth` so an anonymous visit bounces to /login first.
    path: '/account/password',
    name: 'ChangePassword',
    component: ChangePassword,
    meta: { requiresAuth: true },
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
    // spec 07 §5: write rights checked inside the view, like FipEditor.
    path: '/fips/:id/migrate',
    name: 'FipMigrate',
    component: FipMigrate,
    meta: { requiresAuth: false },
    props: true,
  },
  {
    // spec 09: anyone can start a standalone FIP without an account;
    // `POST /api/fips` itself grants edit rights via an edit token in that case.
    path: '/fips/new',
    name: 'FipNew',
    component: FipNew,
    meta: { requiresAuth: false },
  },
  {
    // spec 11 §3.5: unauthenticated, read-only — hidden from the nav when
    // `GET /api/health`'s `networkEnabled` is false (App.vue).
    path: '/network',
    name: 'NetworkFipList',
    component: NetworkFipList,
    meta: { requiresAuth: false },
    props: true,
  },
  {
    path: '/network/:communityIri',
    name: 'NetworkFipDetail',
    component: NetworkFipDetail,
    meta: { requiresAuth: false },
    props: true,
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
    // Anonymous sees public + system models (spec 04 §5).
    path: '/knowledge-models',
    name: 'KnowledgeModelList',
    component: KnowledgeModelList,
    meta: { requiresAuth: false },
  },
  {
    path: '/knowledge-models/new',
    name: 'KnowledgeModelNew',
    component: KnowledgeModelNew,
    meta: { requiresAuth: true },
  },
  {
    path: '/knowledge-models/:id/:version',
    name: 'KnowledgeModelRead',
    component: KnowledgeModelRead,
    meta: { requiresAuth: false },
    props: true,
  },
  {
    // Ownership and `status === "draft"` are checked inside the view
    // (spec 04 §5), which renders `common.notFound` on 404 and a
    // read-only banner on a published version.
    path: '/knowledge-models/:id/:version/edit',
    name: 'KnowledgeModelEditor',
    component: KnowledgeModelEditor,
    meta: { requiresAuth: true },
    props: true,
  },
  {
    // spec 05 §3: the paper-fallback questionnaire; 404 renders
    // `common.notFound` from inside the view itself, like KnowledgeModelRead.
    path: '/knowledge-models/:id/:version/print',
    name: 'KnowledgeModelPrint',
    component: KnowledgeModelPrint,
    meta: { requiresAuth: false },
    props: true,
  },
  {
    // spec 13 §6.1: anonymous viewers get the public/network populations,
    // so this route (and its five children below) never require auth.
    path: '/dashboard',
    name: 'DashboardHome',
    component: DashboardHome,
    meta: { requiresAuth: false },
    props: true,
  },
  {
    path: '/dashboard/coverage',
    name: 'DashboardCoverage',
    component: DashboardCoverage,
    meta: { requiresAuth: false },
    props: true,
  },
  {
    path: '/dashboard/adoption',
    name: 'DashboardAdoption',
    component: DashboardAdoption,
    meta: { requiresAuth: false },
    props: true,
  },
  {
    path: '/dashboard/similarity',
    name: 'DashboardSimilarity',
    component: DashboardSimilarity,
    meta: { requiresAuth: false },
    props: true,
  },
  {
    path: '/dashboard/gaps',
    name: 'DashboardGaps',
    component: DashboardGaps,
    meta: { requiresAuth: false },
    props: true,
  },
  {
    path: '/dashboard/evolution',
    name: 'DashboardEvolution',
    component: DashboardEvolution,
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

  // Same guard for the knowledge-model editor's 2s idle debounce (spec 04 §5).
  if (from.name === 'KnowledgeModelEditor' && to.name !== 'KnowledgeModelEditor') {
    const kmEditorStore = useKmEditorStore()
    await kmEditorStore.flush()
  }

  // spec 05 §1: an admin-set temporary password forces every authenticated
  // navigation except ChangePassword itself to /account/password, until a
  // successful `POST /api/auth/password` clears the flag. A handful of
  // routes stay reachable regardless: ChangePassword's own dependencies
  // (Privacy, whose notice it may need to re-read) and the account-recovery
  // flow (ForgotPassword/ResetPassword/VerifyEmail) — none of them let the
  // caller do anything but read the privacy notice, reset a password, or
  // verify an email, so forcing them through the temporary-password gate
  // first would just lock a still-verifying or -recovering account out.
  const MUST_CHANGE_PASSWORD_EXEMPT = new Set([
    'ChangePassword',
    'Privacy',
    'GuideParticipant',
    'GuideAdmin',
    'ForgotPassword',
    'ResetPassword',
    'VerifyEmail',
  ])
  if (
    authStore.isAuthenticated &&
    authStore.user?.mustChangePassword &&
    !MUST_CHANGE_PASSWORD_EXEMPT.has(String(to.name))
  ) {
    return { path: '/account/password', query: { redirect: to.fullPath } }
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
