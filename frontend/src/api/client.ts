export type ApiError = {
  detail: string
  status?: number
}

type ApiRequestOptions = {
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  path: string
  body?: Record<string, unknown> | FormData
  headers?: Record<string, string>
  editToken?: string
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

export async function apiRequest<T>(
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

    try {
      return (await response.json()) as T
    } catch {
      return {} as T
    }
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

export function post<T>(path: string, body?: Record<string, unknown>, editToken?: string) {
  return apiRequest<T>({ method: 'POST', path, body, editToken })
}

export function patch<T>(path: string, body?: Record<string, unknown>, editToken?: string) {
  return apiRequest<T>({ method: 'PATCH', path, body, editToken })
}

export function put<T>(path: string, body?: Record<string, unknown>, editToken?: string) {
  return apiRequest<T>({ method: 'PUT', path, body, editToken })
}

export function del<T>(path: string, editToken?: string) {
  return apiRequest<T>({ method: 'DELETE', path, editToken })
}

export { ApiResponseError }
