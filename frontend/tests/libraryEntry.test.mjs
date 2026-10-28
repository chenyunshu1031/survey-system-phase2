import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import ts from 'typescript'

const storage = new Map()
globalThis.sessionStorage = {
  getItem: (key) => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, value),
  removeItem: (key) => storage.delete(key),
}

function moduleUrl(path, replacements = {}) {
  let source = readFileSync(new URL(path, import.meta.url), 'utf8')
  for (const [name, url] of Object.entries({ vue: import.meta.resolve('vue'), ...replacements })) {
    source = source.replaceAll(`from '${name}'`, `from '${url}'`)
  }
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  return `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
}

const clientUrl = moduleUrl('../src/api/client.ts')
const { ApiError } = await import(clientUrl)
const { idempotentApi } = await import(moduleUrl('../src/api/idempotency.ts', { './client': clientUrl }))
const { canManageLibrary, canSelectLibraryQuestion, aggregateMetric } = await import(moduleUrl('../src/utils/libraryPresentation.ts'))

test('bank and version retries reuse the same Idempotency-Key after an unknown outcome', async () => {
  storage.clear()
  const keys = []
  let fail = true
  globalThis.fetch = async (url, init) => {
    assert.equal(url, '/api/v1/library/questions/q/versions')
    assert.equal(init.method, 'POST')
    keys.push(init.headers.get('Idempotency-Key'))
    if (fail) { fail = false; throw new TypeError('network disconnected after send') }
    return Response.json({ id: 'version-2' })
  }
  const body = { parentVersionId: 'version-1', type: 'text', title: '新版', options: [], validation: {} }
  await assert.rejects(idempotentApi('create-version:q', '/library/questions/q/versions', body))
  assert.deepEqual(await idempotentApi('create-version:q', '/library/questions/q/versions', body), { id: 'version-2' })
  assert.equal(keys[0], keys[1])
  assert.ok(keys[0].length >= 8)
  assert.equal(storage.size, 0)
})

test('a changed draft receives a new key; successful requests clear the pending key', async () => {
  storage.clear()
  const keys = []
  let attempt = 0
  globalThis.fetch = async (_url, init) => {
    keys.push(init.headers.get('Idempotency-Key'))
    attempt += 1
    if (attempt < 3) throw new TypeError('unknown outcome')
    return Response.json({ id: 'bank' })
  }
  await assert.rejects(idempotentApi('create-bank', '/question-banks', { name: '甲' }))
  await assert.rejects(idempotentApi('create-bank', '/question-banks', { name: '乙' }))
  await idempotentApi('create-bank', '/question-banks', { name: '乙' })
  assert.notEqual(keys[0], keys[1])
  assert.equal(keys[1], keys[2])
  await idempotentApi('create-bank', '/question-banks', { name: '乙' })
  assert.notEqual(keys[2], keys[3])
})

test('API status remains available so a statistics 409 can request refresh', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: '统计期间提交已变化' }), { status: 409 })
  await assert.rejects(idempotentApi('restore:q:v1', '/library/questions/q/versions/v1/restore'), (error) => {
    assert.ok(error instanceof ApiError)
    assert.equal(error.status, 409)
    return true
  })
})

test('permissions hide owner controls and published selection; suppressed values never display as zero', () => {
  assert.equal(canManageLibrary('owner', undefined), false)
  assert.equal(canManageLibrary('owner', 'recipient'), false)
  assert.equal(canManageLibrary('owner', 'owner'), true)
  assert.equal(canSelectLibraryQuestion('draft'), true)
  assert.equal(canSelectLibraryQuestion('published'), false)
  assert.equal(canSelectLibraryQuestion('closed'), false)
  assert.equal(aggregateMetric(null, true), '样本不足')
  assert.equal(aggregateMetric(0, false), '0')
})
