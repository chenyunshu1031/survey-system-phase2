import { api } from './client'

interface PendingRequest { fingerprint: string; key: string }
const prefix = 'survey_library_request_'

/** Keep an unknown-outcome request key across retries and page reloads. */
export async function idempotentApi<T>(operation: string, path: string, body?: object): Promise<T> {
  const fingerprint = JSON.stringify({ path, body: body ?? null })
  const storageKey = `${prefix}${operation}`
  let saved: PendingRequest | null = null
  try { saved = JSON.parse(sessionStorage.getItem(storageKey) || 'null') as PendingRequest | null } catch { /* replace corrupt entry */ }
  const key = saved?.fingerprint === fingerprint ? saved.key : crypto.randomUUID()
  sessionStorage.setItem(storageKey, JSON.stringify({ fingerprint, key }))
  const result = await api<T>(path, {
    method: 'POST', headers: { 'Idempotency-Key': key },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  sessionStorage.removeItem(storageKey)
  return result
}
