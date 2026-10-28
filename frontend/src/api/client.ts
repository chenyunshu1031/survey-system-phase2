import { ref } from 'vue'

const TOKEN_KEY = 'survey_system_token'
export const sessionToken = ref<string | null>(sessionStorage.getItem(TOKEN_KEY))

export function readToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY)
}

export function saveToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token)
  sessionToken.value = token
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY)
  sessionToken.value = null
}

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) { super(message) }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  const token = path === '/auth/login' || path === '/auth/register' ? null : readToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`/api/v1${path}`, { ...init, headers })
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body?.detail
    const message = typeof detail === 'string'
      ? detail
      : Array.isArray(detail) ? detail.map((item: { msg?: string }) => item.msg || '输入有误').join('；') : '请求失败，请稍后重试'
    // An old request must not invalidate a session established after it started.
    if (response.status === 401 && token && readToken() === token) clearToken()
    throw new ApiError(message, response.status)
  }
  return body as T
}
