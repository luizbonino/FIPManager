/**
 * DTOs for the nanopublication-network read endpoints (spec 11 §3.2/§3.3)
 * and the local nanopublication-export bundle manifest (spec 11 §2.6).
 * Wire shape is camelCase throughout, same convention as `types/api.ts`.
 */

import type { DeclarationStatus, Visibility } from './api'

// ---------------------------------------------------------------------------
// spec 11 §3.2: GET /api/network/fip-communities
// ---------------------------------------------------------------------------

export interface NetworkCommunitySummary {
  iri: string
  label: string
  fipCount: number
}

export interface NetworkCommunityListResponse {
  items: NetworkCommunitySummary[]
  total: number
  cachedAt: string
  /** `settings.nanopub_query_url`, added by every `_envelope`-wrapped response (`routers/network.py`). */
  source: string
  /** Present on a stale cache hit served after an upstream failure (spec 11 §3.4). */
  stale?: boolean
}

// ---------------------------------------------------------------------------
// spec 11 §3.2: GET /api/network/fers (v2 roadmap item, shipped behind the
// same flag but not wired into the FER picker for CONFOA — spec 11 §3.2).
// ---------------------------------------------------------------------------

export interface NetworkFerSummary {
  iri: string
  /** `null` when Q4's own hit label and the Q3 enrichment both came back empty (`network.py`'s `search_fers`). */
  label: string | null
  comment: string | null
  homepage: string | null
  types: string[]
  ferTypeKey: string | null
}

export interface NetworkFerSearchResponse {
  items: NetworkFerSummary[]
  total: number
}

// ---------------------------------------------------------------------------
// spec 11 §3.3: GET /api/network/fips/{communityIri}
// ---------------------------------------------------------------------------

/** spec 11 §3.3: filled by matching the network resource against our `fers` table. */
export interface NetworkInCatalogue {
  ferId: string
  matchedBy: string
}

export interface NetworkResource {
  iri: string
  /** `null` when Q3 never returned a row for this resource IRI (`network.py`'s `_group_resources`/`get_community_fip`). */
  label: string | null
  comment: string | null
  homepage: string | null
  types: string[]
  ferTypeKey: string | null
  inCatalogue: NetworkInCatalogue | null
}

export interface NetworkDeclaration {
  nanopubIri: string
  /**
   * Inverse of `rdf.STATUS_PREDICATE`, plus `?nochoice → "none"` — same
   * vocabulary as `DeclarationStatus`. `null` when the declaration is
   * neither a no-choice declaration nor carries any of the four
   * `declares-*-use-of`/`declares-*-replacement-of`/`declares-*-development-of`
   * predicates (`network.py`'s `_status_and_resource`) — render the same
   * fallback used for `resource === null` rather than passing `null` into
   * `StatusBadge`, which has no entry for it.
   */
  status: DeclarationStatus | null
  /**
   * `null` for a "no choice" declaration (spec 11 §3.3's `?nochoice` case):
   * `{nanopubIri, status: "none", resource: null, considerations: null,
   * startDate: null, endDate: null}`. Render as `network.noChoiceDeclared`
   * rather than dereferencing `.label`.
   */
  resource: NetworkResource | null
  considerations: string | null
  startDate: string | null
  endDate: string | null
}

export interface NetworkQuestion {
  questionId: string
  questionIri: string
  declarations: NetworkDeclaration[]
}

export interface NetworkUnmappedQuestion {
  questionIri: string
  declarations: NetworkDeclaration[]
}

export interface NetworkFipOtherVersion {
  nanopubIri: string
  /** `null` when the upstream row's `?label` binding is missing (`network._val`). */
  label: string | null
  /** `null` when the upstream row's `?created` binding is missing (`network._val`). */
  created: string | null
}

export interface NetworkFipSummary {
  /** `null` when the upstream row's `?fip_np` binding is missing (`network._val`). */
  nanopubIri: string | null
  /** `null` when the upstream row's `?label` binding is missing (`network._val`). */
  label: string | null
  /** `null` when the FIP nanopub carries no `fip:has-declaration-index` (optional in Q1). */
  indexIri: string | null
  /** `null` when the upstream row's `?created` binding is missing (`network._val`). */
  created: string | null
  startDate: string | null
  endDate: string | null
  otherVersions: NetworkFipOtherVersion[]
}

export interface NetworkCommunityFipResponse {
  /** `label` is a best-effort lookup against the community list (`routers/network.py`'s `get_network_fip`) — `null` on any upstream failure or an IRI no longer in that list. */
  community: { iri: string; label: string | null }
  fip: NetworkFipSummary
  /** All 21, in `gofair-fip-mini` order, each with a possibly empty `declarations` (spec 11 §3.3). */
  questions: NetworkQuestion[]
  /** Anything not among the 21 (an `FIP-S-Question-*`, an `FSR` question, a future 22nd question). */
  unmapped: NetworkUnmappedQuestion[]
  cachedAt: string
  source: string
  stale?: boolean
}

// ---------------------------------------------------------------------------
// spec 11 §3.6: POST /api/fips/from-network
// ---------------------------------------------------------------------------

export interface CreateFipFromNetworkRequest {
  communityIri: string
  title?: string
  language?: string
  visibility?: Visibility
  /**
   * A facilitator-session deep link (`?session=<id>&code=<joinCode>` on
   * `NetworkFipDetail.vue`, spec 11 §3.6) — both present together or both
   * omitted, never one without the other.
   */
  sessionId?: string
  joinCode?: string
}

/**
 * `fip` is the normal `FipOut` payload; kept as `Record<string, unknown>`
 * here (rather than importing `FipOut`) only to avoid a circular-looking
 * import for a shape callers re-parse anyway via `getFip`/`FipOut` once
 * navigated — callers that need the typed FIP use `FipOut` from `types/api`.
 */
export interface CreateFipFromNetworkResponse {
  fip: { id: string } & Record<string, unknown>
  /** Present exactly once, for an anonymous/standalone creation (same rule as `POST /api/fips`). */
  editToken?: string
  imported: { declarations: number; fersCreated: number; fersMatched: number }
  skipped: Array<{ questionIri: string; reason: string }>
}

// ---------------------------------------------------------------------------
// spec 11 §2.6: nanopublication export bundle — index.json
// ---------------------------------------------------------------------------

export interface NanopubBundleGenerator {
  tool: string
  agent: string
  generatedAt: string
}

export interface NanopubBundleFip {
  id: string
  url: string
  title: string
  language: string
  license: string
  questionnaire: { id: string; version: string }
}

export interface NanopubEntry {
  n: number
  role: string
  file: string
  tempNanopubIri: string
  /** Explicit `null` (not omitted) for the index entry, which has no concept of its own (`nanopub_export.py`). */
  conceptIri: string | null
  introduces?: string
  referencedBy?: number[]
  questionId?: string
  questionIri?: string
  declarationIndex?: number
  status?: string
  /** Explicit `null` (not omitted) for a declaration with no resource (a no-choice declaration). */
  resourceIri: string | null
  /** Explicit `null` (not omitted) alongside `resourceIri: null`. */
  resourceOrigin: string | null
  references?: number[]
}

export interface NanopubRewrite {
  afterSigning: number
  replacePrefix: string
  withPrefix: string
  inFiles: string[]
}

export interface NanopubCounts {
  nanopubs: number
  declarations: number
  skipped: number
}

export interface NanopubSkipped {
  questionId: string
  declarationIndex: number
  reason: string
}

export interface NanopubDmpEvidenceGap {
  questionId: string
  declarationIndex: number
}

export interface NanopubNotRepresented {
  notApplicable: string[]
  answerComments: string[]
  dmpEvidence: NanopubDmpEvidenceGap[]
  relatedDmps: number
}

export interface NanopubPrerequisite {
  what: string
  detail: string
}

export interface NanopubPublishPrerequisites {
  satisfied: NanopubPrerequisite[]
  missing: NanopubPrerequisite[]
}

export interface NanopubBundleIndex {
  schema: string
  generator: NanopubBundleGenerator
  fip: NanopubBundleFip
  tempBase: string
  signed: boolean
  nanopubs: NanopubEntry[]
  signingOrder: Array<number | string>
  rewrites: NanopubRewrite[]
  counts: NanopubCounts
  skipped: NanopubSkipped[]
  notRepresented: NanopubNotRepresented
  publishPrerequisites: NanopubPublishPrerequisites
}
