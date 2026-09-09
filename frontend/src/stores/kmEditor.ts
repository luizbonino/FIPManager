import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { ApiResponseError } from '@/api/client'
import { getFerTypes } from '@/api/ferTypes'
import { listFers } from '@/api/fers'
import {
  deleteKnowledgeModel,
  forkKnowledgeModel,
  getKnowledgeModel,
  newKnowledgeModelVersion,
  patchKnowledgeModel,
  publishKnowledgeModel,
  putKnowledgeModelContent,
  type ForkKnowledgeModelRequest,
  type NewKnowledgeModelVersionRequest,
  type PatchKnowledgeModelRequest,
} from '@/api/knowledgeModels'
import {
  completeness as computeCompleteness,
  validateContent as runValidateContent,
  visibleQuestionCount as computeVisibleQuestionCount,
  type ContentError,
} from '@/lib/kmContent'
import type { FerOut, KnowledgeModelContent, KnowledgeModelOut } from '@/types/api'

/** Idle debounce before an autosave `PUT .../content` (spec 04 §5: "an 2 s idle debounce"). */
export const AUTOSAVE_DEBOUNCE_MS = 2000

/** `'conflict'` is distinct from `'error'`: a 409 means the draft was edited elsewhere, not a failed request — Reload, not Retry, is the way out. */
export type SaveState = 'saved' | 'saving' | 'unsaved' | 'error' | 'conflict'

export const useKmEditorStore = defineStore('kmEditor', () => {
  const model = ref<KnowledgeModelOut | null>(null)
  const content = ref<KnowledgeModelContent | null>(null)
  const etag = ref<string | null>(null)
  const ferTypeKeys = ref<string[]>([])
  /**
   * spec 08 §1.2 rule 10/§1.4: the "picker's cached catalogue map" —
   * fetched once per `load()` like `fipEditor`'s own FER cache, used to
   * resolve suggested-FER labels before promotion and to supply
   * `validateContent`'s `knownFerIds`.
   */
  const fers = ref<Record<string, FerOut>>({})
  const knownFerIds = computed(() => new Set(Object.keys(fers.value)))

  const dirty = ref(false)
  const saving = ref(false)
  const lastSavedAt = ref<Date | null>(null)
  const saveError = ref(false)

  const loading = ref(false)
  const notFound = ref(false)
  /** Set on a `409 content_conflict` save response: "reload to see the newer version" (spec §5). */
  const conflict = ref(false)
  const conflictEtag = ref<string | null>(null)

  const errors = ref<ContentError[]>([])

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let inFlight = false

  const saveState = computed<SaveState>(() => {
    if (conflict.value) return 'conflict'
    if (saveError.value) return 'error'
    if (saving.value) return 'saving'
    if (dirty.value) return 'unsaved'
    return 'saved'
  })

  /**
   * `KnowledgeModelOut` (spec §3 #3) carries no `ownerId`, so ownership and
   * "is this the read-only system model" cannot be precomputed from the
   * loaded document alone — ownership is enforced server-side (404 for a
   * non-owner's private draft; 403 `system_model_readonly` on any write to
   * a system model). `forcedReadOnly`/`readOnlyReason` are set once such a
   * write actually fails, mirroring `stores/fipEditor.ts`'s pattern.
   */
  const forcedReadOnly = ref(false)
  const readOnlyReason = ref<'published' | 'system' | 'forbidden' | null>(null)

  /** A published version accepts only `PATCH visibility` (spec §1) — content edits are 409 `model_published`. */
  const publishedReadOnly = computed(() => model.value?.status === 'published')
  const readOnly = computed(() => publishedReadOnly.value || forcedReadOnly.value)

  const visibleQuestionCount = computed(() => (content.value ? computeVisibleQuestionCount(content.value) : 0))

  function completeness(lang: string) {
    if (!content.value) return { done: 0, total: 0 }
    return computeCompleteness(content.value, lang)
  }

  function clearTimer() {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
  }

  function scheduleSave() {
    clearTimer()
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      void save()
    }, AUTOSAVE_DEBOUNCE_MS)
  }

  function markDirty() {
    dirty.value = true
    scheduleSave()
  }

  /**
   * Applies a pure op from `lib/kmContent.ts` to `content` (spec §5's
   * `apply(op)`), e.g. `store.apply((c) => hideQuestion(c, id))`. Marks
   * dirty and schedules the debounced autosave.
   */
  function apply(op: (current: KnowledgeModelContent) => KnowledgeModelContent): void {
    if (!content.value || readOnly.value) return
    content.value = op(content.value)
    markDirty()
  }

  async function load(id: string, version: string): Promise<void> {
    clearTimer()
    loading.value = true
    notFound.value = false
    conflict.value = false
    dirty.value = false
    saveError.value = false
    forcedReadOnly.value = false
    readOnlyReason.value = null
    errors.value = []
    model.value = null
    content.value = null
    etag.value = null
    fers.value = {}

    try {
      const [loaded, ferTypesResult, fersResult] = await Promise.all([
        getKnowledgeModel(id, version),
        getFerTypes().catch(() => ({ items: [], total: 0 })),
        listFers({ limit: 500 }).catch(() => ({ items: [], total: 0 })),
      ])
      model.value = loaded
      content.value = loaded.content
      etag.value = loaded.etag ?? null
      ferTypeKeys.value = ferTypesResult.items.map((f) => f.key)
      fers.value = Object.fromEntries(fersResult.items.map((f) => [f.id, f]))
      if (loaded.status === 'published') readOnlyReason.value = 'published'
    } catch (err) {
      if (err instanceof ApiResponseError && err.status === 404) {
        notFound.value = true
      }
      throw err
    } finally {
      loading.value = false
    }
  }

  /** "Reload" after a 409 conflict, or a manual refresh — re-fetches from the server, discarding local edits. */
  async function reload(): Promise<void> {
    if (!model.value) return
    await load(model.value.id, model.value.version)
  }

  async function patchMeta(patchBody: PatchKnowledgeModelRequest): Promise<void> {
    if (!model.value) return
    try {
      const updated = await patchKnowledgeModel(model.value.id, model.value.version, patchBody)
      model.value = updated
    } catch (err) {
      applyForbiddenState(err)
      throw err
    }
  }

  function applyForbiddenState(err: unknown): void {
    if (!(err instanceof ApiResponseError) || err.status !== 403) return
    forcedReadOnly.value = true
    readOnlyReason.value = err.data.detail === 'system_model_readonly' ? 'system' : 'forbidden'
  }

  async function save(): Promise<void> {
    if (!model.value || !content.value || inFlight || !dirty.value || readOnly.value) return
    if (!etag.value) return
    inFlight = true
    saving.value = true
    saveError.value = false
    const payload = {
      sections: content.value.sections,
      title: content.value.title,
      description: content.value.description,
      // spec 08 §1.4: no dedicated endpoint — these three ride along on the
      // same whole-document PUT as everything else.
      inlineFers: content.value.inlineFers,
      defaultDeclarationStatus: content.value.defaultDeclarationStatus,
      compactDeclarations: content.value.compactDeclarations,
    }
    const sentEtag = etag.value
    dirty.value = false

    try {
      const updated = await putKnowledgeModelContent(model.value.id, model.value.version, payload, sentEtag)
      model.value = updated
      content.value = updated.content
      etag.value = updated.etag ?? etag.value
      lastSavedAt.value = new Date()
      saving.value = false
      inFlight = false
      if (dirty.value) {
        void save()
      }
    } catch (err) {
      saving.value = false
      inFlight = false
      if (err instanceof ApiResponseError && err.status === 409) {
        conflict.value = true
        conflictEtag.value = (err.data as { etag?: string }).etag ?? null
        // The draft holds this failed write locally; a fresh PUT is not
        // retried automatically — the user must Reload first (spec §5, no
        // silent merge). Put `dirty` back so `saveState` (-> 'conflict',
        // since `conflict.value` is now true) never falls through to
        // 'saved' — this write did NOT land.
        dirty.value = true
      } else if (err instanceof ApiResponseError && err.status === 403) {
        applyForbiddenState(err)
      } else {
        dirty.value = true
        saveError.value = true
      }
    }
  }

  async function flush(): Promise<void> {
    clearTimer()
    await save()
  }

  /** `publishing: true` also runs rule 13 (`no_answer_path`) — the manual "Check model" button uses it too, matching what Publish itself will enforce. */
  function validate(): ContentError[] {
    if (!content.value) return []
    errors.value = runValidateContent(content.value, ferTypeKeys.value, {
      knownFerIds: knownFerIds.value,
      publishing: true,
    })
    return errors.value
  }

  async function publish(notes: string): Promise<KnowledgeModelOut> {
    if (!model.value) throw new Error('no model loaded')
    await flush()
    try {
      const updated = await publishKnowledgeModel(model.value.id, model.value.version, notes)
      model.value = updated
      content.value = updated.content
      readOnlyReason.value = 'published'
      return updated
    } catch (err) {
      applyForbiddenState(err)
      // 400 invalid_content carries `errors` (spec §3): surface it in the
      // same validation list the manual "Check model" button uses.
      if (err instanceof ApiResponseError && Array.isArray((err.data as { errors?: unknown }).errors)) {
        errors.value = (err.data as unknown as { errors: ContentError[] }).errors
      }
      throw err
    }
  }

  async function newVersion(body?: NewKnowledgeModelVersionRequest): Promise<KnowledgeModelOut> {
    if (!model.value) throw new Error('no model loaded')
    return newKnowledgeModelVersion(model.value.id, model.value.version, body)
  }

  async function fork(id: string, version: string, body?: ForkKnowledgeModelRequest): Promise<KnowledgeModelOut> {
    return forkKnowledgeModel(id, version, body)
  }

  async function remove(): Promise<void> {
    if (!model.value) return
    await deleteKnowledgeModel(model.value.id, model.value.version)
  }

  return {
    model,
    content,
    etag,
    fers,
    knownFerIds,
    dirty,
    saving,
    lastSavedAt,
    saveState,
    loading,
    notFound,
    conflict,
    conflictEtag,
    errors,
    readOnly,
    forcedReadOnly,
    readOnlyReason,
    publishedReadOnly,
    visibleQuestionCount,
    completeness,
    load,
    reload,
    patchMeta,
    apply,
    save,
    flush,
    validate,
    publish,
    newVersion,
    fork,
    remove,
  }
})
