/**
 * DTOs mirroring the backend Pydantic schemas (backend/fipm/schemas.py).
 * Bodies are camelCase on the wire (spec 01 §6); these types match that
 * wire shape, not the backend's snake_case Python names.
 *
 * See docs/specs/01-foundations.md §2.2/§3 and docs/specs/02-core-flows.md §5/§6.4.
 */

/** `{"en": "...", "pt-PT": "...", "pt-BR": "...", "es": "..."}` — never assume all keys are present. */
export type LangMap = Record<string, string>

export type Visibility = 'private' | 'link' | 'public'
export type SessionStatus = 'open' | 'closed'
/** The four UI locales (spec 02 §5.5's `Language` schema literal). */
export type Language = 'en' | 'pt-PT' | 'pt-BR' | 'es'
/** `fipm.config.DECLARATION_STATUSES` (spec 02 §1) — the UI never invents a sixth. */
export type DeclarationStatus =
  | 'current'
  | 'planned'
  | 'planned-development'
  | 'planned-replacement'
  | 'none'

/**
 * Stored/write shape (spec 06 §2.1): `dmpIndex` is the 0-based position of
 * the plan in this FIP's `relatedDmps`, required whenever the object is
 * present. The legacy `{url, questionRef}` shape (spec 01, never actually
 * populated in v1) is a backend-only read concern (exporters/import) and is
 * not modelled here — the editor never creates or edits it.
 */
export interface DmpEvidence {
  dmpIndex: number
  section?: string | null
  questionRef?: string | null
}

export interface Declaration {
  ferId?: string | null
  ferFreeText?: string | null
  status: DeclarationStatus
  note?: LangMap | null
  dmpEvidence?: DmpEvidence | null
  /**
   * The resource that will replace this one (spec 05 §5): at most one of
   * the two set, and both `null`/absent unless `status ===
   * 'planned-replacement'` — enforced client-side by
   * `stores/fipEditor.setDeclaration` and server-side by `_successor_rules`.
   */
  successorFerId?: string | null
  successorFreeText?: string | null
}

export interface Answer {
  questionId: string
  declarations: Declaration[]
  comment?: string | null
  /** spec 08 §2.1: mutually exclusive with `declarations` — never stored `false` (dropped from the payload). */
  notApplicable?: boolean
}

export interface DataSteward {
  orcid?: string | null
  name?: string | null
}

export interface Community {
  name?: string | null
  description?: string | null
  links: string[]
  domain?: string | null
  dataSteward?: DataSteward | null
}

export interface RelatedDmp {
  url: string
  version?: string | null
  system?: string | null
  /** Set server-side only when `system === 'FioDMP'` (spec 06 §1.1); a client-sent value is ignored. */
  dmpId?: string | null
}

export interface QuestionnaireRef {
  id: string
  version: string
}

/** spec 08 §3.1: a session's questionnaire ref plus its per-session area label. */
export interface QuestionnaireRefLabelled {
  id: string
  version: string
  label: LangMap
}

/** `SessionOut`/`SessionPublicOut`'s per-ref entry (spec 08 §3.1): the labelled ref plus the model's own title. */
export interface QuestionnaireRefWithTitle extends QuestionnaireRefLabelled {
  title: LangMap
}

// ---------------------------------------------------------------------------
// FIPs
// ---------------------------------------------------------------------------

export interface FipCreateRequest {
  questionnaireRef: QuestionnaireRef
  language?: string
  community?: Community
  answers?: Answer[]
  visibility?: Visibility
  sessionId?: string
  joinCode?: string
  relatedDmps?: RelatedDmp[]
  license?: string
}

export interface FipPatchRequest {
  community?: Community
  answers?: Answer[]
  relatedDmps?: RelatedDmp[]
  language?: string
  license?: string
  visibility?: Visibility
}

export interface FipOut {
  id: string
  ownerId: string | null
  sessionId: string | null
  visibility: Visibility
  questionnaireId: string
  questionnaireVersion: string
  title: string | null
  community: Community | null
  relatedDmps: RelatedDmp[]
  answers: Answer[]
  language: string
  license: string
  createdAt: string
  updatedAt: string
  /** Present exactly once, on the response to `POST /api/fips` for an anonymous FIP. */
  editToken?: string
  /** spec 07 §0/§4.3: the version migrated *from* on the last migration, or absent/null otherwise. */
  migratedFrom?: MigratedFrom | null
  /** spec 08 §3.2: the session ref's area label, non-null only for a FIP in a multi-ref session. */
  areaLabel?: LangMap | null
}

// ---------------------------------------------------------------------------
// Mail flows / migration (spec 07)
// ---------------------------------------------------------------------------

/** `fips.migrated_from` (spec 07 §0): `{"id","version","at"}` of the version migrated from. */
export interface MigratedFrom {
  id: string
  version: string
  at: string
}

/** `GET /api/fips/{id}/migration-targets` (spec 07 §4.3). */
export interface MigrationTargetItem {
  id: string
  version: string
  title: LangMap
  changelog: Array<Record<string, unknown>>
  publishedAt: string
}

export interface MigrationTargetsOut {
  current: { id: string; version: string }
  items: MigrationTargetItem[]
  total: number
}

export type MigrationItemStatus = 'unchanged' | 'added' | 'removed' | 'hidden' | 'split'

export interface MigrationSplitDecision {
  kind: 'splitCopies'
  options: string[]
  default: string[]
}

export interface MigrationOrphanDecision {
  kind: 'orphanReassign'
  options: string[]
  default: string | null
}

export type MigrationDecisionSpec = MigrationSplitDecision | MigrationOrphanDecision | null

/** One row of the §4.2 diff document. */
export interface MigrationDiffItem {
  status: MigrationItemStatus
  oldQuestionId: string | null
  newQuestionId: string | null
  oldText?: string | null
  newText?: string | null
  oldFerType?: string | null
  newFerType?: string | null
  /** Non-exclusive: `text-changed`, `fer-type-changed`, `scope-changed`. */
  flags: string[]
  answered: boolean
  declarationCount: number
  /** Present only on a `split` item: the two target ids it splits into. */
  splitInto?: string[]
  decision: MigrationDecisionSpec
}

export interface MigrationCounts {
  unchanged: number
  added: number
  removed: number
  hidden: number
  split: number
  textChanged: number
  ferTypeChanged: number
  answersKept: number
  answersOrphaned: number
  decisionsRequired: number
}

/** `GET /api/fips/{id}/migration-preview` (spec 07 §4.2), `diffVersion: 1`. */
export interface MigrationDiff {
  diffVersion: 1
  generatedAt: string
  from: { id: string; version: string }
  to: { id: string; version: string; changelog: Array<Record<string, unknown>> }
  counts: MigrationCounts
  items: MigrationDiffItem[]
}

/** `POST /api/fips/{id}/migrate` request body (spec 07 §4.3). */
export interface MigrateDecisions {
  splitCopies?: Record<string, string[]>
  orphanReassign?: Record<string, string>
}

export interface MigrateRequest {
  to: string
  decisions?: MigrateDecisions
}

// ---------------------------------------------------------------------------
// Knowledge models
// ---------------------------------------------------------------------------

export interface KnowledgeModelQuestion {
  id: string
  principle: string | null
  scope: 'metadata' | 'data' | null
  text: LangMap
  help: LangMap | null
  ferType: string | null
  required: boolean
  allowMultiple: boolean
  /** spec 04 §2: present (`true`) only while hidden; absent/undefined otherwise, never stored `false`. */
  hidden?: boolean
  /** spec 08 §1.1: 0..12 unique absolute IRIs, display order, resolving against `inlineFers` or the catalogue. */
  suggestedFerIds?: string[]
  /** spec 08 §1.1: default `true`; `false` hides free text and rejects `ferFreeText` server-side. */
  allowFreeText?: boolean
}

/** spec 08 §1.1: an area-specific FER a fork carries before it exists in the global catalogue. */
export interface InlineFer {
  id: string
  label: LangMap
  type: string
  homepage?: string | null
}

export interface KnowledgeModelSection {
  id: string
  title: LangMap
  questions: KnowledgeModelQuestion[]
}

/** spec 04 §1: recorded on a fork, `{id, version}` of the source model/version. */
export interface KnowledgeModelForkedFrom {
  id: string
  version: string
}

export interface KnowledgeModelContent {
  id: string
  version: string
  status: string
  license: string
  /**
   * Unlike the top-level `KnowledgeModelOut.source` (always a plain
   * string), `content` is stored server-side as an opaque JSON blob passed
   * through verbatim (spec 01 §3) — the GO FAIR system model's own
   * `content.source` is `{name, url}`, not a string. Never rendered
   * directly by this feature; kept loosely typed rather than assumed.
   */
  source?: string | { name?: string; url?: string } | null
  title: LangMap
  description: LangMap
  changelog: Array<Record<string, unknown>>
  sections: KnowledgeModelSection[]
  /** spec 04 §1: set on a fork, never user-editable. */
  forkedFrom?: KnowledgeModelForkedFrom | null
  /** spec 04 §1/spec 00 §6: the GO FAIR CC-BY-SA credit line, set automatically on such a fork. */
  attribution?: string | null
  /** spec 08 §1.1: 0..300 area-specific FERs staged before catalogue promotion. */
  inlineFers?: InlineFer[]
  /** spec 08 §1.1: the status a quick-pick checkbox assigns; default `current`. */
  defaultDeclarationStatus?: DeclarationStatus
  /** spec 08 §1.1/§1.5: collapses the status control behind "more" in the participant editor. */
  compactDeclarations?: boolean
}

export interface KnowledgeModelOut {
  id: string
  version: string
  status: string
  visibility: string
  license: string
  source: string
  title: LangMap
  description: LangMap
  changelog: Array<Record<string, unknown>>
  /** The whole knowledge-model document (spec 01 §3): sections, questions, help, ferType. */
  content: KnowledgeModelContent
  createdAt: string
  updatedAt: string
  /**
   * Not part of the JSON body: `GET`/`PUT .../content` (spec 04 §3 #3, #9)
   * also return the `ETag` response header carrying `content_sha256`;
   * `api/knowledgeModels.ts` reads it and stashes it here for the caller,
   * since `apiRequest<T>` only returns the parsed body.
   */
  etag?: string | null
}

export interface KnowledgeModelSummary {
  id: string
  version: string
  status: string
  visibility: string
  license: string
  title: LangMap
  description: LangMap
  createdAt: string
  updatedAt: string
  /** spec 04 §3 #1 additions. */
  ownerId: string | null
  isSystem: boolean
  /** Non-hidden question count, server-computed. */
  questionCount: number
  forkedFrom: KnowledgeModelForkedFrom | null
}

export interface KnowledgeModelVersionEntry {
  version: string
  status: string
  changelog: Array<Record<string, unknown>>
}

// ---------------------------------------------------------------------------
// FERs / FER types
// ---------------------------------------------------------------------------

export interface FerOut {
  id: string
  label: LangMap
  type: string
  homepage: string | null
  source: string
}

/** `GET /api/fer-types` (spec 02 §5.2) — the FIP-Ontology FER-type taxonomy. */
export interface FerType {
  key: string
  iri: string
  principle: string
  label: LangMap
  description: LangMap
}

// ---------------------------------------------------------------------------
// Sessions
// ---------------------------------------------------------------------------

export interface SessionCreateRequest {
  title: string
  questionnaireRef: QuestionnaireRef
  defaultLanguage: string
  /** spec 08 §3.1: 1..12 labelled refs; a pre-v6 client omits this and `questionnaireRef` alone still works. */
  questionnaireRefs?: QuestionnaireRefLabelled[]
}

export interface SessionPatchRequest {
  title?: string
  status?: SessionStatus
  defaultLanguage?: string
  /** spec 08 §3.1: replaceable only while the session has no FIPs yet (409 `session_has_fips` otherwise). */
  questionnaireRefs?: QuestionnaireRefLabelled[]
}

export interface SessionOut {
  id: string
  joinCode: string
  joinUrl: string
  ownerId: string
  questionnaireId: string
  questionnaireVersion: string
  defaultLanguage: string
  title: string
  status: SessionStatus
  createdAt: string
  updatedAt: string
  /** spec 08 §3.1: always populated (derived from `questionnaireRef` on a pre-v6 row) — the first entry mirrors it. */
  questionnaireRefs?: QuestionnaireRefWithTitle[]
}

/** `GET /api/sessions/by-code/{joinCode}` (spec 02 §5.1) — public, pre-join metadata. */
export interface SessionPublicOut {
  id: string
  title: string
  status: SessionStatus
  questionnaireRef: QuestionnaireRef
  defaultLanguage: string
  facilitatorName: string
  /** Additive per spec 02 §5.1: the knowledge model's `title`, so the join screen skips a KM fetch. */
  questionnaireTitle: LangMap
  /** spec 08 §3.1: present on a multi-ref session; length 1 means "no visual change" for `JoinSession.vue`. */
  questionnaireRefs?: QuestionnaireRefWithTitle[]
}

// ---------------------------------------------------------------------------
// Lists
// ---------------------------------------------------------------------------

export interface ListOut<T> {
  items: T[]
  total: number
}

// ---------------------------------------------------------------------------
// FIP export document (spec 01 §3.1), returned by GET /api/fips/{id}/export.json
// and GET /api/sessions/{id}/export.json (spec 02 §5.3)
// ---------------------------------------------------------------------------

export interface FipExportFer {
  id: string
  label: string | null
  type: string | null
  homepage: string | null
}

/**
 * `dmpEvidence` resolved at export time (spec 06 §2.4): a consumer never
 * needs the index, so `export.json` sends the plan's own URL/system/version
 * alongside `section`/`questionRef`. Distinct from the stored `DmpEvidence`
 * (index-based) that the editor reads and writes.
 */
export interface FipExportDmpEvidence {
  /** `null` once the stored index no longer resolves against `relatedDMPs` (the plan was removed/reordered). */
  dmpIndex: number | null
  /**
   * `null` when the index above didn't resolve, or (legacy `{url,...}`
   * evidence, spec 06 §2.4) when the stored URL isn't a safe `https://`
   * one — in that case the raw value is under `rawUrl` instead, never as a
   * clickable `href` (`resolve_dmp_evidence_for_export`, backend/fipm/dmp.py).
   */
  dmpUrl: string | null
  dmpSystem: string | null
  dmpVersion: string | null
  section: string | null
  questionRef: string | null
  /** Only present alongside a `dmpUrl: null` from an unsafe legacy URL. */
  rawUrl?: string
}

export interface FipExportDeclaration {
  fer: FipExportFer | null
  ferFreeText: string | null
  status: DeclarationStatus
  note: string | null
  dmpEvidence: FipExportDmpEvidence | null
  /** spec 05 §5: enriched exactly like `fer`, `null` unless a successor is set. */
  successor: FipExportFer | null
  successorFreeText: string | null
}

export interface FipExportAnswer {
  sectionId: string
  sectionTitle: string
  questionId: string
  questionText: string
  principle: string | null
  scope: string | null
  ferType: string | null
  declarations: FipExportDeclaration[]
  comment: string | null
  /** spec 08 §2.3: `true` only when the answer is marked "not applicable" — `declarations` is then always `[]`. */
  notApplicable?: boolean
}

export interface FipExportFip {
  id: string
  url: string
  language: string
  license: string
  visibility: Visibility
  createdAt: string
  updatedAt: string
  community: Community | null
  /** Sic: capitalised `DMPs`, matching `exporters.py`'s hand-built export dict verbatim. */
  relatedDMPs: RelatedDmp[]
  /** spec 07 §6: set on the last migration, otherwise `null`. */
  migratedFrom?: MigratedFrom | null
  /** spec 08 §3.3: present only inside a session export, on a FIP from a multi-ref session. */
  area?: QuestionnaireRefLabelled | null
}

/** `fips.orphaned_answers` (spec 07 §4.4), FER-enriched like `FipExportAnswer.declarations`. */
export interface FipExportOrphanedAnswer {
  questionId: string
  questionText: string
  declarations: FipExportDeclaration[]
  comment: string | null
  fromVersion: string
  at: string
}

export interface FipExportQuestionnaireRef {
  id: string
  version: string
  title: string
  source: string
}

export interface FipExportDoc {
  exportVersion: number
  generatedAt: string
  tool: { name: string; baseUrl: string }
  fip: FipExportFip
  questionnaireRef: FipExportQuestionnaireRef
  answers: FipExportAnswer[]
  /** spec 07 §6: `exportVersion: 2` only; absent on an export made before this spec. */
  orphanedAnswers?: FipExportOrphanedAnswer[]
}

// ---------------------------------------------------------------------------
// Admin (spec 05 §1)
// ---------------------------------------------------------------------------

export interface AdminUserOut {
  id: string
  email: string
  displayName: string
  role: 'user' | 'admin'
  language: string
  createdAt: string
  mustChangePassword: boolean
  privacyAcceptedVersion: string | null
  fipCount: number
  sessionCount: number
  knowledgeModelCount: number
}

/** `FerOut` plus the two admin-only fields (spec 05 §1). */
export interface AdminFerOut extends FerOut {
  ownerEmail: string | null
  usageCount: number
}

export interface AdminMergeResult {
  repointedDeclarations: number
  repointedFips: number
}

/** `GET /api/sessions/{id}/export.json` (spec 02 §5.3). */
export interface SessionExportDoc {
  exportVersion: number
  generatedAt: string
  tool: { name: string; baseUrl: string }
  session: {
    id: string
    title: string
    status: SessionStatus
    joinCode: string
    defaultLanguage: string
    questionnaireRef: QuestionnaireRef
    facilitatorName: string
    createdAt: string
    /** spec 08 §3.3: the full labelled ref list; `questionnaireRef` above stays the first entry. */
    questionnaireRefs?: QuestionnaireRefLabelled[]
  }
  fips: FipExportDoc[]
}
