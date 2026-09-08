/**
 * DTOs mirroring the backend Pydantic schemas (backend/fipm/schemas.py).
 * Bodies are camelCase on the wire (spec 01 §6); these types match that
 * wire shape, not the backend's snake_case Python names.
 *
 * See docs/specs/01-foundations.md §2.2/§3 and docs/specs/02-core-flows.md §5/§6.4.
 */

/** `{"en": "...", "pt-PT": "...", "pt-BR": "..."}` — never assume all three keys are present. */
export type LangMap = Record<string, string>

export type Visibility = 'private' | 'link' | 'public'
export type SessionStatus = 'open' | 'closed'
/** The three UI locales (spec 02 §5.5's `Language` schema literal). */
export type Language = 'en' | 'pt-PT' | 'pt-BR'
/** `fipm.config.DECLARATION_STATUSES` (spec 02 §1) — the UI never invents a sixth. */
export type DeclarationStatus =
  | 'current'
  | 'planned'
  | 'planned-development'
  | 'planned-replacement'
  | 'none'

export interface DmpEvidence {
  url?: string | null
  questionRef?: string | null
}

export interface Declaration {
  ferId?: string | null
  ferFreeText?: string | null
  status: DeclarationStatus
  note?: LangMap | null
  dmpEvidence?: DmpEvidence | null
}

export interface Answer {
  questionId: string
  declarations: Declaration[]
  comment?: string | null
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
}

export interface QuestionnaireRef {
  id: string
  version: string
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
}

export interface KnowledgeModelSection {
  id: string
  title: LangMap
  questions: KnowledgeModelQuestion[]
}

export interface KnowledgeModelContent {
  id: string
  version: string
  status: string
  license: string
  source: string
  title: LangMap
  description: LangMap
  changelog: Array<Record<string, unknown>>
  sections: KnowledgeModelSection[]
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
}

export interface SessionPatchRequest {
  title?: string
  status?: SessionStatus
  defaultLanguage?: string
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

export interface FipExportDeclaration {
  fer: FipExportFer | null
  ferFreeText: string | null
  status: DeclarationStatus
  note: string | null
  dmpEvidence: DmpEvidence | null
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
  }
  fips: FipExportDoc[]
}
