<template>
  <div class="network-fip-detail">
    <div v-if="loading" class="loading">
      <p>{{ $t('common.loading') }}</p>
    </div>

    <div v-else-if="errorState === 'disabled'" class="message-box">
      <p>{{ $t('network.disabledMessage') }}</p>
    </div>

    <div v-else-if="errorState === 'unavailable'" class="message-box">
      <p>{{ $t('network.unavailableMessage') }}</p>
      <button type="button" class="btn btn-secondary" @click="load">{{ $t('common.retry') }}</button>
    </div>

    <div v-else-if="errorState === 'not_found'" class="message-box">
      <p>{{ $t('network.notFoundMessage') }}</p>
    </div>

    <!-- 400 invalid_community_iri: the identifier itself is malformed, so a
         Retry (which re-sends the same bad IRI) could never succeed —
         distinct from `unavailable`, which is a transient upstream issue. -->
    <div v-else-if="errorState === 'invalid_iri'" class="message-box">
      <p>{{ $t('network.invalidIri') }}</p>
    </div>

    <template v-else-if="data">
      <header class="community-header">
        <h1>{{ communityLabel }}</h1>
        <dl class="community-meta">
          <dt>{{ $t('network.fipLabel') }}</dt>
          <dd>{{ fipLabel }}</dd>
          <template v-if="data.fip.created">
            <dt>{{ $t('common.created') }}</dt>
            <dd>{{ formatDate(data.fip.created) }}</dd>
          </template>
        </dl>
        <a
          v-if="data.fip.nanopubIri"
          :href="nanodashUrl(data.fip.nanopubIri)"
          target="_blank"
          rel="noopener noreferrer"
          class="nanodash-link"
        >
          {{ $t('network.viewOnNanodash') }}
        </a>

        <div v-if="data.fip.otherVersions.length > 0" class="other-versions">
          <h2>{{ $t('network.otherVersionsTitle') }}</h2>
          <ul>
            <li v-for="v in data.fip.otherVersions" :key="v.nanopubIri">
              <a :href="nanodashUrl(v.nanopubIri)" target="_blank" rel="noopener noreferrer">
                {{ otherVersionLabel(v) }}<template v-if="v.created"> ({{ formatDate(v.created) }})</template>
              </a>
            </li>
          </ul>
        </div>
      </header>

      <section class="start-form">
        <h2>{{ $t('network.useAsStartingPoint') }}</h2>
        <form @submit.prevent="onUseAsStartingPoint">
          <label class="field">
            <span>{{ $t('network.startTitleLabel') }}</span>
            <input v-model="startTitle" type="text" :placeholder="$t('network.startTitlePlaceholder')" />
          </label>
          <label class="field">
            <span>{{ $t('network.startLanguageLabel') }}</span>
            <select v-model="startLanguage">
              <option v-for="loc in SUPPORTED_LOCALES" :key="loc" :value="loc">{{ $t(`languages.${loc}`) }}</option>
            </select>
          </label>
          <VisibilitySelect v-model="startVisibility" />
          <p v-if="submitError" class="form-error">{{ submitError }}</p>
          <button type="submit" class="btn btn-primary start-submit-btn" :disabled="submitting">
            {{ submitting ? $t('network.startSubmitting') : $t('network.startSubmit') }}
          </button>
        </form>
      </section>

      <div class="sections">
        <article
          v-for="q in data.questions"
          :key="q.questionId"
          class="question-card"
          :class="{ empty: q.declarations.length === 0 }"
        >
          <div class="question-head">
            <span class="question-id">{{ q.questionId }}</span>
          </div>
          <p v-if="q.declarations.length === 0" class="no-declaration">{{ $t('network.noDeclaration') }}</p>
          <ul v-else class="declarations">
            <li v-for="(decl, i) in q.declarations" :key="i" class="declaration">
              <template v-if="decl.resource">
                <span class="declaration-label">{{ resourceLabel(decl.resource) }}</span>
                <StatusBadge v-if="decl.status" :status="decl.status" />
                <span
                  v-if="decl.resource.inCatalogue"
                  class="in-catalogue-hint"
                  :title="decl.resource.inCatalogue.ferId"
                >
                  {{ $t('network.inCatalogueHint', { matchedBy: decl.resource.inCatalogue.matchedBy }) }}
                </span>
              </template>
              <template v-else>
                <span class="declaration-label declaration-no-choice">{{ $t('network.noChoiceDeclared') }}</span>
                <!-- `decl.status` is only ever `null` here alongside `resource: null` (either a
                     genuine no-choice declaration, status "none", or the degenerate case where
                     the network returned neither a nochoice flag nor a recognised declares-*
                     predicate) — the "No choice declared" text above already covers both, so the
                     badge (which has no i18n entry for `null`) is simply omitted rather than
                     passed a value it can't render. -->
                <StatusBadge v-if="decl.status" :status="decl.status" />
              </template>
              <a
                :href="nanodashUrl(decl.nanopubIri)"
                target="_blank"
                rel="noopener noreferrer"
                class="nanodash-link declaration-nanodash-link"
              >
                {{ $t('network.viewOnNanodash') }}
              </a>
              <p v-if="decl.considerations" class="declaration-considerations">{{ decl.considerations }}</p>
            </li>
          </ul>
        </article>
      </div>

      <details v-if="data.unmapped.length > 0" class="unmapped-details">
        <summary>{{ $t('network.unmappedTitle', { count: data.unmapped.length }) }}</summary>
        <article v-for="uq in data.unmapped" :key="uq.questionIri" class="question-card">
          <div class="question-head">
            <span class="question-id">{{ uq.questionIri }}</span>
          </div>
          <p v-if="uq.declarations.length === 0" class="no-declaration">{{ $t('network.noDeclaration') }}</p>
          <ul v-else class="declarations">
            <li v-for="(decl, i) in uq.declarations" :key="i" class="declaration">
              <template v-if="decl.resource">
                <span class="declaration-label">{{ resourceLabel(decl.resource) }}</span>
                <StatusBadge v-if="decl.status" :status="decl.status" />
                <span
                  v-if="decl.resource.inCatalogue"
                  class="in-catalogue-hint"
                  :title="decl.resource.inCatalogue.ferId"
                >
                  {{ $t('network.inCatalogueHint', { matchedBy: decl.resource.inCatalogue.matchedBy }) }}
                </span>
              </template>
              <template v-else>
                <span class="declaration-label declaration-no-choice">{{ $t('network.noChoiceDeclared') }}</span>
                <!-- `decl.status` is only ever `null` here alongside `resource: null` (either a
                     genuine no-choice declaration, status "none", or the degenerate case where
                     the network returned neither a nochoice flag nor a recognised declares-*
                     predicate) — the "No choice declared" text above already covers both, so the
                     badge (which has no i18n entry for `null`) is simply omitted rather than
                     passed a value it can't render. -->
                <StatusBadge v-if="decl.status" :status="decl.status" />
              </template>
              <a
                :href="nanodashUrl(decl.nanopubIri)"
                target="_blank"
                rel="noopener noreferrer"
                class="nanodash-link declaration-nanodash-link"
              >
                {{ $t('network.viewOnNanodash') }}
              </a>
              <p v-if="decl.considerations" class="declaration-considerations">{{ decl.considerations }}</p>
            </li>
          </ul>
        </article>
      </details>
    </template>
  </div>
</template>

<script lang="ts" setup>
/**
 * spec 11 §3.5/§3.6: `/network/:communityIri`. Renders the community/FIP
 * header, the "Use as starting point" flow (§3.6), and all 21 questions in
 * declaration-list layout with `StatusBadge.vue` for status — the same
 * question-card visual language `FipRead.vue` uses for its own read-only
 * view (id badge, declarations list), reused here as CSS rather than by
 * importing `QuestionCard.vue` itself: that component is wired directly to
 * `stores/fipEditor` (editable declarations, FER search, autosave) and has
 * no foreign-data read-only mode, so importing it would mean either
 * smuggling this network payload through the *editing* store (autosave,
 * claim, patch — all wrong for data that was never `POST`ed) or a
 * significant refactor of a heavily-tested component, neither of which
 * this brief's scope covers. `StatusBadge.vue` — genuinely reusable,
 * already prop-driven — is imported and used directly, matching
 * `FipRead.vue`'s own precedent.
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ApiResponseError } from '@/api/client'
import { createFipFromNetwork, getCommunityFip } from '@/api/network'
import { setToken } from '@/lib/editTokens'
import { createFipErrorMessage } from '@/lib/fipErrors'
import { SUPPORTED_LOCALES } from '@/i18n'
import StatusBadge from '@/components/StatusBadge.vue'
import VisibilitySelect from '@/components/VisibilitySelect.vue'
import type { NetworkCommunityFipResponse, NetworkFipOtherVersion, NetworkResource } from '@/types/network'
import type { Visibility } from '@/types/api'

// `route.params.communityIri`, not `defineProps` — same convention as
// `FipRead.vue`/`FipEditor.vue`/`JoinSession.vue` (the router's own
// `props: true` is kept for consistency with those routes, but every one
// of them reads its id param via `useRoute()`).
const route = useRoute()
const router = useRouter()
const { locale, t } = useI18n()

const communityIri = computed(() => String(route.params.communityIri))

type ErrorState = 'disabled' | 'unavailable' | 'not_found' | 'invalid_iri' | null

const loading = ref(true)
const errorState = ref<ErrorState>(null)
const data = ref<NetworkCommunityFipResponse | null>(null)

const startTitle = ref('')
const startLanguage = ref(locale.value)
const startVisibility = ref<Visibility>('link')
const submitting = ref(false)
const submitError = ref<string | null>(null)

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString()
}

function nanodashUrl(nanopubIri: string): string {
  return `https://nanodash.knowledgepixels.com/explore?id=${encodeURIComponent(nanopubIri)}`
}

/** Last `/`- or `#`-separated segment of an IRI, trailing separators ignored — a readable stand-in for a missing label. */
function iriTail(iri: string): string {
  const trimmed = iri.replace(/[/#]+$/, '')
  const idx = Math.max(trimmed.lastIndexOf('#'), trimmed.lastIndexOf('/'))
  return idx >= 0 ? trimmed.slice(idx + 1) : trimmed
}

/**
 * spec 11 §3.3: several `*.label` fields come back `null` from the network
 * (a Q1/Q3 row missing its `rdfs:label` binding, or `community.label`'s
 * own best-effort lookup failing). Falls back to the item's own IRI tail
 * when one is available, then to `network.unknownLabel`.
 */
function labelOrFallback(label: string | null, iri: string | null): string {
  if (label) return label
  if (iri) return iriTail(iri)
  return t('network.unknownLabel')
}

const communityLabel = computed(() =>
  labelOrFallback(data.value?.community.label ?? null, data.value?.community.iri ?? null)
)
const fipLabel = computed(() =>
  labelOrFallback(data.value?.fip.label ?? null, data.value?.fip.nanopubIri ?? null)
)

function otherVersionLabel(v: NetworkFipOtherVersion): string {
  return labelOrFallback(v.label, v.nanopubIri)
}

function resourceLabel(resource: NetworkResource): string {
  return labelOrFallback(resource.label, resource.iri)
}

async function load() {
  loading.value = true
  errorState.value = null
  try {
    data.value = await getCommunityFip(communityIri.value)
  } catch (err) {
    if (err instanceof ApiResponseError && err.data.detail === 'network_disabled') {
      errorState.value = 'disabled'
    } else if (err instanceof ApiResponseError && err.data.detail === 'network_fip_not_found') {
      errorState.value = 'not_found'
    } else if (err instanceof ApiResponseError && err.data.detail === 'invalid_community_iri') {
      errorState.value = 'invalid_iri'
    } else {
      errorState.value = 'unavailable'
    }
    data.value = null
  } finally {
    loading.value = false
  }
}

onMounted(load)

/**
 * A facilitator deep-linking here from a session (`?session=<id>&code=
 * <joinCode>`) — both present together or neither, never one alone (a
 * partial/malformed link is treated as no link at all rather than sending
 * a half-formed session reference to the backend).
 */
function networkSessionParams(): { sessionId?: string; joinCode?: string } {
  const sessionId = route.query.session
  const joinCode = route.query.code
  if (typeof sessionId === 'string' && sessionId && typeof joinCode === 'string' && joinCode) {
    return { sessionId, joinCode }
  }
  return {}
}

// spec 11 §3.6 acceptance criterion #5: exactly one `createFipFromNetwork`
// call per click, guarded synchronously (not just via the disabled button
// attribute, which can lag a fast double-click) — the same idiom
// `FipEditor.vue`'s claim/delete actions use.
async function onUseAsStartingPoint() {
  if (submitting.value) return
  submitting.value = true
  submitError.value = null
  try {
    const result = await createFipFromNetwork({
      communityIri: communityIri.value,
      title: startTitle.value.trim() || undefined,
      language: startLanguage.value,
      visibility: startVisibility.value,
      ...networkSessionParams(),
    })
    if (result.editToken) {
      setToken(result.fip.id, result.editToken)
    }
    // The community label and the imported/skipped counts are this
    // response's only copy (spec 11 §4's persisted `networkOrigin` keeps
    // just `communityIri`, not a human label or the counts) — carried via
    // the URL to FipEditor.vue's one-time banner, which reads and then
    // strips them (same idiom as `adoptTokenFromQuery`'s `?token=`).
    await router.push({
      path: `/fips/${result.fip.id}/edit`,
      query: {
        networkCommunity: communityLabel.value,
        networkImported: String(result.imported.declarations),
        networkSkipped: String(result.skipped.length),
      },
    })
  } catch (err) {
    submitError.value = createFipErrorMessage(t, err, 'standalone')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.network-fip-detail {
  max-width: 800px;
  margin: 0 auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.loading,
.message-box {
  text-align: center;
  padding: 2rem 1rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

.community-header h1 {
  margin: 0 0 0.5rem;
  color: var(--color-primary);
}

.community-meta {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.25rem 0.75rem;
  margin: 0 0 0.5rem;
  font-size: var(--font-size-sm);
}

.community-meta dt {
  color: var(--color-text-secondary);
}

.community-meta dd {
  margin: 0;
}

.nanodash-link {
  color: var(--color-link);
  font-size: var(--font-size-sm);
}

.other-versions {
  margin-top: 0.75rem;
}

.other-versions h2 {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin: 0 0 0.35rem;
}

.other-versions ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: var(--font-size-sm);
}

.start-form {
  padding: 1rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
  background-color: var(--color-hover);
}

.start-form h2 {
  margin: 0 0 0.75rem;
}

.start-form form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  align-items: flex-start;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  width: 100%;
  max-width: 24rem;
}

.field input,
.field select {
  min-height: 44px;
  padding: 0.5rem 0.65rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  font-size: 1rem;
  font-family: inherit;
}

.form-error {
  color: var(--color-error);
  font-size: var(--font-size-sm);
  margin: 0;
}

.sections {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.question-card {
  padding: 0.75rem 1rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-md);
}

.question-card.empty {
  opacity: 0.65;
  background-color: var(--color-hover);
}

.question-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.question-id {
  font-family: monospace;
  font-size: var(--font-size-xs);
  color: var(--color-id-chip-text);
  background-color: var(--color-id-chip-bg);
  padding: 0.15rem 0.4rem;
  border-radius: var(--border-radius-sm);
}

.no-declaration {
  margin: 0.35rem 0 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  font-style: italic;
}

.declarations {
  list-style: none;
  margin: 0.35rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.declaration {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  font-size: var(--font-size-sm);
}

.in-catalogue-hint {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
}

.declaration-no-choice {
  font-style: italic;
  color: var(--color-text-secondary);
}

.declaration-nanodash-link {
  font-size: var(--font-size-xs);
}

.declaration-considerations {
  width: 100%;
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
}

.unmapped-details summary {
  cursor: pointer;
  color: var(--color-link);
  font-size: var(--font-size-sm);
  min-height: 44px;
  display: flex;
  align-items: center;
}

.unmapped-details .question-card {
  margin-top: 0.5rem;
}

.btn {
  min-height: 44px;
  padding: 0.6rem 1.2rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--color-background);
  color: var(--color-text);
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-secondary-text);
  border: none;
}

.btn-primary {
  background-color: var(--color-primary);
  color: var(--color-primary-text);
  border: none;
}

.btn:disabled {
  opacity: 0.7;
}
</style>
