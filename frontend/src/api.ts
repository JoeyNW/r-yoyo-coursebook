export class ApiError extends Error {
  status: number
  code: string
  extra: Record<string, unknown>

  constructor(
    status: number,
    code: string,
    message: string,
    extra: Record<string, unknown>,
  ) {
    super(message)
    this.status = status
    this.code = code
    this.extra = extra
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (init?.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(path, {
    ...init,
    headers,
    credentials: 'include',
  })
  if (response.status === 204) {
    return undefined as T
  }
  const text = await response.text()
  const data = text ? JSON.parse(text) : null
  if (!response.ok) {
    const detail = data?.detail
    const message =
      typeof detail === 'string' ? detail : detail?.message || '操作失败'
    const code =
      typeof detail === 'object' && detail?.code ? String(detail.code) : 'error'
    const extra =
      typeof detail === 'object' && detail ? (detail as Record<string, unknown>) : {}
    throw new ApiError(response.status, code, message, extra)
  }
  return data as T
}
