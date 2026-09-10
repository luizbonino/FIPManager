import { apiRequestPlain, get, post } from './client'
import type {
  CreateFipFromNetworkRequest,
  CreateFipFromNetworkResponse,
  NanopubBundleIndex,
  NetworkCommunityFipResponse,
  NetworkCommunityListResponse,
  NetworkFerSearchResponse,
} from '@/types/network'

/** spec 11 §3.2: `GET /api/network/fip-communities?q=&limit=&offset=`. */
export function listCommunities(params: { q?: string; limit?: number; offset?: number } = {}) {
  const search = new URLSearchParams()
  if (params.q) search.set('q', params.q)
  if (params.limit !== undefined) search.set('limit', String(params.limit))
  if (params.offset !== undefined) search.set('offset', String(params.offset))
  const qs = search.toString()
  return get<NetworkCommunityListResponse>(`/network/fip-communities${qs ? `?${qs}` : ''}`)
}

/**
 * spec 11 §3.3: `GET /api/network/fips/{communityIri}`. `communityIri` is a
 * full IRI, `encodeURIComponent`-encoded here exactly once — FastAPI
 * decodes the path segment once on the way in.
 */
export function getCommunityFip(communityIri: string) {
  return get<NetworkCommunityFipResponse>(`/network/fips/${encodeURIComponent(communityIri)}`)
}

/** spec 11 §3.2: `GET /api/network/fers?q=&limit=` — v2 roadmap item, not wired into the FER picker for CONFOA. */
export function searchFers(params: { q?: string; limit?: number } = {}) {
  const search = new URLSearchParams()
  if (params.q) search.set('q', params.q)
  if (params.limit !== undefined) search.set('limit', String(params.limit))
  const qs = search.toString()
  return get<NetworkFerSearchResponse>(`/network/fers${qs ? `?${qs}` : ''}`)
}

/** spec 11 §3.6: `POST /api/fips/from-network` — prefills a new, fully editable FIP from a network community. */
export function createFipFromNetwork(body: CreateFipFromNetworkRequest) {
  return post<CreateFipFromNetworkResponse>('/fips/from-network', body)
}

/** spec 11 §2.7: `GET /api/fips/{id}/export/nanopubs/index.json` — the manifest alone, for the Prepare dialog. */
export function getNanopubIndex(fipId: string) {
  return get<NanopubBundleIndex>(`/fips/${fipId}/export/nanopubs/index.json`)
}

/**
 * spec 11 §2.7: `GET /api/fips/{id}/export/nanopubs/preview.trig?n=`, a
 * single nanopub's TriG text (`Content-Type: application/trig`) — plain
 * text, not JSON, hence `apiRequestPlain` rather than `get`. `n` defaults
 * server-side to the FIP nanopub (the last one) when omitted.
 */
export function getNanopubPreview(fipId: string, n?: number) {
  const qs = n !== undefined ? `?n=${n}` : ''
  return apiRequestPlain<string>({ method: 'GET', path: `/fips/${fipId}/export/nanopubs/preview.trig${qs}` })
}

/**
 * spec 11 §2.6/§2.7: `GET /api/fips/{id}/export/nanopubs.zip`, a plain `<a
 * href>` target — `Content-Disposition: attachment` is already set
 * server-side, same convention as `fipExportTtlUrl` etc. (`api/fips.ts`).
 */
export function nanopubZipUrl(fipId: string): string {
  return `/api/fips/${fipId}/export/nanopubs.zip`
}
