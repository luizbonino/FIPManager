export type ApiError = {
  detail: string
  status?: number
  /** `409 content_conflict` (spec 04 §3 #9) carries the current ETag alongside `detail`. */
  etag?: string
}

type ApiRequestOptions = {
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  path: string
  // `object` (not `Record<string, unknown>`) so a plain DTO interface can be
  // passed straight through without an index-signature cast at every call site.
  body?: object | FormData
  headers?: Record<string, string>
  editToken?: string
  /** `If-Match` (spec 04 §3 #9): required on `PUT .../content`, optimistic concurrency. */
  ifMatch?: string
}

class ApiResponseError extends Error {
  constructor(
    public status: number,
    public data: ApiError,
    public originalError?: Error
  ) {
    super(`API Error ${status}: ${data.detail}`)
    this.name = 'ApiResponseError'
  }
}

const API_BASE = '/api'

function buildRequest(options: ApiRequestOptions): { url: string; config: RequestInit } {
  const { method, path, body, headers = {}, editToken, ifMatch } = options

  const requestHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    ...headers,
  }

  if (editToken) {
    requestHeaders['X-Edit-Token'] = editToken
  }
  if (ifMatch) {
    requestHeaders['If-Match'] = ifMatch
  }

  const config: RequestInit = {
    method,
    credentials: 'include',
    headers: requestHeaders,
  }

  if (body && !(body instanceof FormData)) {
    config.body = JSON.stringify(body)
  } else if (body instanceof FormData) {
    delete requestHeaders['Content-Type']
    config.body = body
  }

  return { url: `${API_BASE}${path}`, config }
}

/** Shared fetch + error-mapping, returning the raw `Response` on success (2xx). */
async function performRequest(options: ApiRequestOptions): Promise<Response> {
  const { url, config } = buildRequest(options)
  try {
    const response = await fetch(url, config)
    if (!response.ok) {
      let errorData: ApiError
      try {
        errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
      } catch {
        errorData = { detail: `HTTP ${response.status}` }
      }
      throw new ApiResponseError(response.status, errorData)
    }
    return response
  } catch (error) {
    if (error instanceof ApiResponseError) {
      throw error
    }
    throw new ApiResponseError(
      0,
      { detail: 'Network error' },
      error instanceof Error ? error : undefined
    )
  }
}

export async function apiRequest<T>(
  options: ApiRequestOptions
): Promise<T> {
  const response = await performRequest(options)
  try {
    return (await response.json()) as T
  } catch {
    return {} as T
  }
}

export interface ApiResponseWithEtag<T> {
  data: T
  /** The `ETag` response header (spec 04 §3 #3, #9), or `null` if the route doesn't set one. */
  etag: string | null
}

/**
 * Like `apiRequest`, but also surfaces the `ETag` response header —
 * `apiRequest<T>` only returns the parsed body, and the knowledge-model
 * content endpoints need the header for `If-Match` optimistic concurrency
 * (spec 04 §2/§3). Kept as a separate function rather than widening every
 * call site's return type.
 */
export async function apiRequestWithEtag<T>(
  options: ApiRequestOptions
): Promise<ApiResponseWithEtag<T>> {
  const response = await performRequest(options)
  const etag = response.headers.get('ETag')
  try {
    return { data: (await response.json()) as T, etag }
  } catch {
    return { data: {} as T, etag }
  }
}

export async function apiRequestPlain<T>(
  options: ApiRequestOptions
): Promise<T> {
  const { method, path, body, headers = {}, editToken } = options

  const requestHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    ...headers,
  }

  if (editToken) {
    requestHeaders['X-Edit-Token'] = editToken
  }

  const config: RequestInit = {
    method,
    credentials: 'include',
    headers: requestHeaders,
  }

  if (body && !(body instanceof FormData)) {
    config.body = JSON.stringify(body)
  } else if (body instanceof FormData) {
    delete requestHeaders['Content-Type']
    config.body = body
  }

  const url = `${API_BASE}${path}`

  try {
    const response = await fetch(url, config)

    if (!response.ok) {
      let errorData: ApiError
      try {
        errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
      } catch {
        errorData = { detail: `HTTP ${response.status}` }
      }
      throw new ApiResponseError(response.status, errorData)
    }

    return (await response.text()) as unknown as T
  } catch (error) {
    if (error instanceof ApiResponseError) {
      throw error
    }
    throw new ApiResponseError(
      0,
      { detail: 'Network error' },
      error instanceof Error ? error : undefined
    )
  }
}

// Convenience methods
export function get<T>(path: string, editToken?: string) {
  return apiRequest<T>({ method: 'GET', path, editToken })
}

export function post<T>(path: string, body?: object, editToken?: string) {
  return apiRequest<T>({ method: 'POST', path, body, editToken })
}

export function patch<T>(path: string, body?: object, editToken?: string) {
  return apiRequest<T>({ method: 'PATCH', path, body, editToken })
}

export function put<T>(path: string, body?: object, editToken?: string) {
  return apiRequest<T>({ method: 'PUT', path, body, editToken })
}

export function del<T>(path: string, editToken?: string) {
  return apiRequest<T>({ method: 'DELETE', path, editToken })
}

/** `GET` that also returns the `ETag` response header. */
export function getWithEtag<T>(path: string): Promise<ApiResponseWithEtag<T>> {
  return apiRequestWithEtag<T>({ method: 'GET', path })
}

/** `PUT` with a required `If-Match` header, returning the new `ETag`. */
export function putWithEtag<T>(path: string, body: object, ifMatch: string): Promise<ApiResponseWithEtag<T>> {
  return apiRequestWithEtag<T>({ method: 'PUT', path, body, ifMatch })
}

export { ApiResponseError }
