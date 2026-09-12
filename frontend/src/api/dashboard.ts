/**
 * `GET /api/dashboard/*` (spec 13 §3, §6.1). One function per endpoint plus
 * `savePopulation`, `listPopulations`, `refreshDashboard`, and
 * `dashboardCsvUrl`. `If-None-Match` is passed through on every view call;
 * a `304` reuses the caller's cached body; a `202 snapshot_pending` returns
 * `{status:'pending', retryAfter, stalePayload, degraded}` rather than
 * throwing (spec 13 §5.3/§7's "a projected dashboard degrades to last
 * hour's numbers … never to a spinner").
 */
import { ApiResponseError } from './client'
import { isSavedPopulationHash } from '@/lib/dashboard'
import type {
  AdoptionData,
  ClustersData,
  CoverageData,
  DashboardEnvelope,
  EvolutionData,
  FipLookupResponse,
  GapsData,
  MapData,
  NeighboursData,
  RefreshRequest,
  RefreshResponse,
  SavedPopulation,
  SavePopulationRequest,
  SimilarityPairData,
} from '@/types/dashboard'

const API_BASE = '/api/dashboard'

export interface DashboardFetchOptions {
  /** The last `etag` this caller holds for the same view+params, if any. */
  ifNoneMatch?: string | null
}

export type DashboardResult<T> =
  | { status: 'ok'; envelope: DashboardEnvelope<T> }
  | { status: 'notModified' }
  | { status: 'pending'; retryAfter: number; stalePayload: T | null; degraded: boolean }

/**
 * `backend/fipm/routers/dashboard.py::_resolve_spec` takes two distinct
 * query params: `population` is the primary key of a *saved* population row
 * (`POST /populations` / `onSaved`'s `saved.hash`); `pop` is everything else
 * a caller can carry in a URL — a shorthand (`public`, `network`,
 * `session:<id>`) or an inline base64 spec (`encodePopulationParam`). Every
 * view/CSV/refresh call funnels its route `pop` value through this helper
 * rather than re-deriving the branch itself, since `pop` and `population`
 * are never both sent for the same value (spec 13 §6.1).
 */
export function populationQueryParam(pop: string): { population?: string; pop?: string } {
  if (!pop) return {}
  return isSavedPopulationHash(pop) ? { population: pop } : { pop }
}

function buildQuery(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const qs = search.toString()
  return qs ? `?${qs}` : ''
}

async function parseErrorBody(response: Response): Promise<{ detail: string; [k: string]: unknown }> {
  try {
    return await response.json()
  } catch {
    return { detail: `HTTP ${response.status}` }
  }
}

async function fetchView<T>(
  path: string,
  params: Record<string, string | number | boolean | undefined | null>,
  options: DashboardFetchOptions = {}
): Promise<DashboardResult<T>> {
  const headers: Record<string, string> = {}
  if (options.ifNoneMatch) headers['If-None-Match'] = options.ifNoneMatch

  const response = await fetch(`${API_BASE}${path}${buildQuery(params)}`, {
    method: 'GET',
    credentials: 'include',
    headers,
  })

  if (response.status === 304) return { status: 'notModified' }

  if (response.status === 202) {
    const body = await parseErrorBody(response)
    const headerRetry = Number(response.headers.get('Retry-After'))
    const retryAfter = Number.isFinite(headerRetry) && headerRetry > 0 ? headerRetry : Number(body.retryAfter) || 15
    return {
      status: 'pending',
      retryAfter,
      stalePayload: (body.stalePayload as T | undefined) ?? null,
      degraded: body.degraded === true,
    }
  }

  if (!response.ok) {
    const body = await parseErrorBody(response)
    throw new ApiResponseError(response.status, body as never)
  }

  const envelope = (await response.json()) as DashboardEnvelope<T>
  return { status: 'ok', envelope }
}

// ---------------------------------------------------------------------------
// §3.1 Coverage — always fetched at `groupBy=question` (see lib/dashboard.ts).
// ---------------------------------------------------------------------------

export interface CoverageParams {
  population: string
  scope?: 'metadata' | 'data' | 'any'
  includeAssurance?: boolean
  updatedAfter?: string
  updatedBefore?: string
}

export function getCoverage(params: CoverageParams, options?: DashboardFetchOptions) {
  return fetchView<CoverageData>(
    '/coverage',
    {
      ...populationQueryParam(params.population),
      groupBy: 'question',
      scope: params.scope,
      includeAssurance: params.includeAssurance ? 1 : undefined,
      updatedAfter: params.updatedAfter,
      updatedBefore: params.updatedBefore,
    },
    options
  )
}

export function dashboardCsvUrl(
  view: 'coverage' | 'adoption' | 'gaps' | 'evolution',
  pop: string,
  params: Record<string, string | number | boolean | undefined>
): string {
  return `${API_BASE}/${view}.csv${buildQuery({ ...populationQueryParam(pop), ...params })}`
}

// ---------------------------------------------------------------------------
// §3.2 Adoption
// ---------------------------------------------------------------------------

export interface AdoptionParams {
  population: string
  groupBy?: 'fer' | 'ferType' | 'area' | 'question'
  status?: 'current' | 'planned' | 'any'
  catalogued?: 'only' | 'exclude' | 'any'
  limit?: number
  offset?: number
  sort?: 'fips' | 'fer'
}

export function getAdoption(params: AdoptionParams, options?: DashboardFetchOptions) {
  return fetchView<AdoptionData>('/adoption', { ...params, population: undefined, ...populationQueryParam(params.population) }, options)
}

// ---------------------------------------------------------------------------
// §3.4 Gaps — always fetched at `groupBy=question`, same rollup discipline.
// ---------------------------------------------------------------------------

export interface GapsParams {
  population: string
  minShare?: number
  limit?: number
  offset?: number
}

export function getGaps(params: GapsParams, options?: DashboardFetchOptions) {
  return fetchView<GapsData>(
    '/gaps',
    { ...params, population: undefined, ...populationQueryParam(params.population), groupBy: 'question' },
    options
  )
}

// ---------------------------------------------------------------------------
// §3.5 Evolution
// ---------------------------------------------------------------------------

export interface EvolutionParams {
  population: string
  groupBy?: 'question' | 'subPrinciple'
  limit?: number
  offset?: number
}

export function getEvolution(params: EvolutionParams, options?: DashboardFetchOptions) {
  return fetchView<EvolutionData>('/evolution', { ...params, population: undefined, ...populationQueryParam(params.population) }, options)
}

// ---------------------------------------------------------------------------
// §3.3 / §4 Similarity
// ---------------------------------------------------------------------------

export interface SimilarityPairParams {
  a: string
  b: string
  weighting?: 'principle' | 'question' | 'letter'
}

export function getSimilarityPair(params: SimilarityPairParams, options?: DashboardFetchOptions) {
  return fetchView<SimilarityPairData>('/similarity/pair', { ...params }, options)
}

export interface SimilarityNeighboursParams {
  fip: string
  population: string
  limit?: number
  weighting?: 'principle' | 'question' | 'letter'
  minSimilarity?: number
}

export function getSimilarityNeighbours(params: SimilarityNeighboursParams, options?: DashboardFetchOptions) {
  return fetchView<NeighboursData>(
    '/similarity/neighbours',
    { ...params, population: undefined, ...populationQueryParam(params.population) },
    options
  )
}

export interface SimilarityClustersParams {
  population: string
  minSimilarity?: number
  limit?: number
}

export function getSimilarityClusters(params: SimilarityClustersParams, options?: DashboardFetchOptions) {
  return fetchView<ClustersData>(
    '/similarity/clusters',
    { ...params, population: undefined, ...populationQueryParam(params.population) },
    options
  )
}

export interface SimilarityMapParams {
  population: string
  buckets?: number
  weighting?: 'principle' | 'question' | 'letter'
}

export function getSimilarityMap(params: SimilarityMapParams, options?: DashboardFetchOptions) {
  return fetchView<MapData>(
    '/similarity/map',
    { ...params, population: undefined, ...populationQueryParam(params.population) },
    options
  )
}

// ---------------------------------------------------------------------------
// §3.7 FIP lookup (spec 13 §11.4) — the neighbours panel's typeahead.
// A plain, deliberately non-enveloped list: no `If-None-Match`, no tier.
// ---------------------------------------------------------------------------

export interface FipLookupParams {
  population: string
  q?: string
  /** Capped at 20 server-side; clamped here too so a caller bug never asks for more. */
  limit?: number
}

export async function getFipLookup(params: FipLookupParams): Promise<FipLookupResponse> {
  const query = buildQuery({
    ...populationQueryParam(params.population),
    q: params.q,
    limit: params.limit != null ? Math.max(1, Math.min(20, params.limit)) : undefined,
  })
  const response = await fetch(`${API_BASE}/fips${query}`, { method: 'GET', credentials: 'include' })
  if (!response.ok) {
    const errorBody = await parseErrorBody(response)
    throw new ApiResponseError(response.status, errorBody as never)
  }
  return response.json()
}

// ---------------------------------------------------------------------------
// Populations (spec 13 §2.1)
// ---------------------------------------------------------------------------

export async function savePopulation(body: SavePopulationRequest): Promise<SavedPopulation> {
  const response = await fetch(`${API_BASE}/populations`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const errorBody = await parseErrorBody(response)
    throw new ApiResponseError(response.status, errorBody as never)
  }
  return response.json()
}

export async function listPopulations(): Promise<{ items: SavedPopulation[]; networkIngestedAt: string | null }> {
  const response = await fetch(`${API_BASE}/populations`, { method: 'GET', credentials: 'include' })
  if (!response.ok) {
    const errorBody = await parseErrorBody(response)
    throw new ApiResponseError(response.status, errorBody as never)
  }
  return response.json()
}

// ---------------------------------------------------------------------------
// Refresh (spec 13 §5.3)
// ---------------------------------------------------------------------------

/**
 * Unlike the GET views, `POST /refresh` takes a single `population` body
 * field for either case: the handler tries it as a saved-population primary
 * key first and, if that misses, resolves it as a `pop` shorthand/inline
 * spec itself (`backend/fipm/routers/dashboard.py::post_refresh`). Callers
 * pass the raw route `pop` value through unchanged — no `populationQueryParam`
 * split needed here.
 */
export async function refreshDashboard(body: RefreshRequest): Promise<RefreshResponse> {
  const response = await fetch(`${API_BASE}/refresh`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const errorBody = await parseErrorBody(response)
    throw new ApiResponseError(response.status, errorBody as never)
  }
  return response.json()
}
