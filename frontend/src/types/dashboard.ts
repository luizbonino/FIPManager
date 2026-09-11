/**
 * Response types transcribed from spec 13 §3 (the five view contracts) and
 * §4 (similarity). Wire shape is camelCase throughout, matching
 * `types/api.ts`'s convention (spec 01 §6). The backend for these routes is
 * built in parallel (builder brief A/B) — tests mock strictly to these
 * shapes; if the shipped backend differs, that is the drift to reconcile,
 * not a reason to loosen these types.
 */

export type GroupingLevel = 'question' | 'subPrinciple' | 'principle' | 'group'

export type PopulationTermKindOut = 'session' | 'public' | 'network' | 'questionnaire' | 'area' | 'mine'

/** The envelope's `population` field (spec 13 §3). */
export interface PopulationInfo {
  hash: string
  authScope: string
  /**
   * `null` whenever any FIP in the population is one the viewer could not
   * open individually (spec 13 §2.4 k-anonymity) — the count itself would
   * disclose that FIP. Render the withheld case as text, never as `0` or a
   * missing number.
   */
  fipCount: number | null
  label?: string | null
  /** Present only for a saved population (spec 13 §6.1: "renders its label, fipCount and computedAt"). */
  computedAt?: string | null
  networkIngestedAt?: string | null
}

/** Common response envelope, spec 13 §3. */
export interface DashboardEnvelope<T> {
  population: PopulationInfo
  tier: 'live' | 'snapshot'
  computedAt: string
  degraded: boolean
  degradedReason?: 'projection_stale' | 'projection_missing' | string | null
  staleFips?: number
  etag: string
  data: T
}

// ---------------------------------------------------------------------------
// Errors (spec 13 §1.8, §2.4, §4.4, §7.3)
// ---------------------------------------------------------------------------

export type DashboardErrorCode =
  | 'dashboard_disabled'
  | 'population_too_small'
  | 'population_not_found'
  | 'projection_stale'
  | 'projection_missing'
  | 'invalid_population'
  | 'invalid_group_by'
  | 'not_found'
  | 'similarity_population_too_large'
  | 'refresh_in_progress'
  | 'admin_required'
  /** Kept though unconfirmed server-side — spec 13 §11 amendment round may still implement it. */
  | 'questionnaire_too_large'

export interface DashboardErrorBody {
  detail: DashboardErrorCode | string
  minimum?: number
  staleFips?: number
  totalFips?: number
  hint?: string
  cap?: number
}

// ---------------------------------------------------------------------------
// §3.1 Coverage
// ---------------------------------------------------------------------------

export interface CoverageCounts {
  current: number
  planned: number
  none: number
  notApplicable: number
  unanswered: number
  absent: number
}

export interface CoverageRow {
  key: string
  level: GroupingLevel
  /** `fip_cells.sub_principle` verbatim, e.g. `'A1.1'` — the row's own principle code before any rollup. */
  subPrinciple: string
  /** `fip_cells.principle`, i.e. `subPrinciple` up to the first `'.'` (spec 13 §1.3), e.g. `'A1'`. */
  principle: string
  principleGroup: string
  questions: string[]
  ferTypes: string[]
  counts: CoverageCounts
  shares: CoverageCounts
  assurance?: Record<string, number>
}

export interface CoverageData {
  rows: CoverageRow[]
  totals: { fips: number; cells: number }
  order: string[]
}

// ---------------------------------------------------------------------------
// §3.2 Adoption
// ---------------------------------------------------------------------------

export interface AdoptionRow {
  ferKey: string
  ferId: string | null
  label: string
  ferType: string | null
  status: string
  fips: number
  declarations: number
  share: number
  areas?: { areaKey: string; fips: number }[]
}

export interface AdoptionData {
  rows: AdoptionRow[]
  total: number
  truncated: boolean
}

// ---------------------------------------------------------------------------
// §3.4 Gaps
// ---------------------------------------------------------------------------

export interface GapsRow {
  questionId: string
  questionIndex: number
  subPrinciple: string | null
  principleGroup: string
  ferType: string | null
  fips: number
  unanswered: number
  noneOnly: number
  notApplicable: number
  plannedOnly: number
  coherenceFlags: number
  typeMismatches: number
}

export interface GapsData {
  rows: GapsRow[]
  total: number
  truncated: boolean
}

// ---------------------------------------------------------------------------
// §3.5 Evolution
// ---------------------------------------------------------------------------

export interface EvolutionPlannedRow {
  subPrinciple: string | null
  questionId: string
  status: string
  ferKey: string
  ferLabel?: string | null
  successorFerKey: string | null
  successorLabel?: string | null
  fips: number
}

export interface EvolutionMigrationRow {
  questionnaireId: string
  questionnaireVersion: string
  migratedFromId: string | null
  migratedFromVersion: string | null
  fips: number
}

export interface EvolutionData {
  planned: EvolutionPlannedRow[]
  migrations: EvolutionMigrationRow[]
  truncated: boolean
}

// ---------------------------------------------------------------------------
// §3.3 / §4 Similarity and convergence
// ---------------------------------------------------------------------------

export type SimilarityWeighting = 'principle' | 'question' | 'letter'
export type SimilarityStatuses = 'current' | 'currentPlanned'

export interface PairQuestionScore {
  questionId: string
  jaccard: number | null
  included: boolean
}

export interface SimilarityPairData {
  a: { id: string; label: string }
  b: { id: string; label: string }
  overall: number
  weighting: SimilarityWeighting
  statuses: SimilarityStatuses
  perPrinciple: Record<string, number>
  perQuestion: PairQuestionScore[]
}

export interface NeighbourRow {
  fipId: string
  label: string
  areaKey: string | null
  similarity: number
  sharedKeys: number
  perPrinciple: Record<string, number>
  /**
   * `label` here is misleadingly named on the wire: it carries the raw
   * convergence key itself (spec 13 §11.3 amendment) — a resource IRI or a
   * `text:<normalised free text>` string — never a resolved display name.
   * Render through `formatConvergenceKey` (lib/dashboard.ts); never present
   * a raw `text:` key to a user.
   */
  topShared: { questionId: string; ferKey: string; label: string }[]
}

export interface NeighboursData {
  fip: { id: string; label: string }
  neighbours: NeighbourRow[]
  weighting: SimilarityWeighting
  statuses: SimilarityStatuses
  candidateBudgetExhausted: boolean
  postingTruncated: boolean
  skippedPopularKeys: string[]
  keysUsed: number
  candidatesScored: number
}

export interface ClusterMember {
  fipId: string
  label: string
}

export interface ClusterRow {
  id: string
  size: number
  representative: ClusterMember
  meanSimilarity: number
  principles: string[]
  members: ClusterMember[]
}

export interface ClustersData {
  clusters: ClusterRow[]
  truncated: boolean
}

export interface HotBucket {
  size: number
  representativeFipId: string
  /**
   * May be absent or `null` (spec 13 §11 amendment in flight): a parallel
   * backend round is either computing this honestly or removing the field
   * because it was a hard-coded placeholder. Render the group's member
   * count regardless; never show a number the API did not send.
   */
  meanSimilarityEstimate?: number | null
}

export interface ConvergenceRow {
  questionId: string
  declaringFips: number
  distinctCurrent: number
  /**
   * The convergence key itself, not a resolved label (spec 13 §11.3
   * amendment) — same caveat as `NeighbourRow.topShared[].label`. Render
   * through `formatConvergenceKey`.
   */
  topKey: string | null
  topLabel: string | null
  topCount: number
  agreed: boolean
  /** spec 13 §11.3 amendment (additive, from `matrix.ts`'s `Convergence`): FIPs whose cell on this row is `notApplicable`. */
  notApplicableFips: number
}

export interface MapNode {
  id: string
  label: string
  /** spec 13 §11.3 amendment (additive): colour the scatter by this instead of deriving connected components in the browser. */
  clusterId: string
}

export interface MapEdge {
  a: string
  b: string
  similarity: number
}

export interface MapData {
  histogram: { bucket: number; from: number; to: number; count: number }[]
  principleBuckets: Record<string, number[]>
  convergence: ConvergenceRow[]
  topClusters: ClusterRow[]
  hotBuckets: HotBucket[]
  scatterAvailable: boolean
  nodes?: MapNode[]
  edges?: MapEdge[]
  /**
   * spec 13 §11.3 amendment: edges are thresholded at the cluster minimum
   * similarity, ordered by similarity, capped at a server limit
   * (`FIPM_DASHBOARD_MAP_EDGE_CAP`). `true` when the cap discarded edges —
   * the scatter must disclose this to the viewer (brief C AC 6).
   */
  edgesTruncated: boolean
}

// ---------------------------------------------------------------------------
// Populations (spec 13 §2.1, §6.1)
// ---------------------------------------------------------------------------

export interface SavedPopulation {
  hash: string
  label: string | null
  authScope: string
  /** May not be present — a parallel backend round is deciding (spec 13 §11 amendment round). Render only when present. */
  fipCount?: number | null
  createdAt?: string
  lastUsedAt?: string
}

// ---------------------------------------------------------------------------
// §3.7 FIP lookup (spec 13 §11.4) — `GET /api/dashboard/fips`, a plain,
// deliberately non-enveloped list for the neighbours panel's typeahead.
// ---------------------------------------------------------------------------

export interface FipLookupItem {
  fipId: string
  label: string
  areaKey: string | null
  answeredQuestions?: number
  questionCount?: number
  updatedAt?: string
}

export interface FipLookupResponse {
  items: FipLookupItem[]
  total?: number
  truncated?: boolean
}

export interface SavePopulationRequest {
  spec: {
    version: 1
    include: { kind: PopulationTermKindOut; id?: string; version?: string; sessionId?: string }[]
    exclude: { kind: PopulationTermKindOut; id?: string; version?: string; sessionId?: string }[]
    updatedAfter?: string | null
    updatedBefore?: string | null
  }
  label?: string | null
}

export interface RefreshRequest {
  population: string
  views: string[]
  force?: boolean
}

export interface RefreshResponse {
  status: 'computing' | 'done'
  retryAfter?: number
}
