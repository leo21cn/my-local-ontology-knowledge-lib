export function token() {
  let value = localStorage.getItem('kb_token')
  if (!value) {
    value = window.prompt('请输入访问令牌') || ''
    if (value) localStorage.setItem('kb_token', value)
  }
  return value
}

async function call(path, options = {}) {
  const resp = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token()}`,
      ...(options.headers || {})
    }
  })
  if (resp.status === 401) {
    localStorage.removeItem('kb_token')
    throw new Error('令牌无效，请重新输入')
  }
  const body = await resp.json().catch(() => ({}))
  if (!resp.ok) throw new Error(body?.error?.message || resp.statusText)
  return body.data
}

export const api = {
  get: (path) => call(path),
  post: (path, payload) => call(path, { method: 'POST', body: JSON.stringify(payload) }),
  patch: (path, payload) => call(path, { method: 'PATCH', body: JSON.stringify(payload) }),
  del: (path) => call(path, { method: 'DELETE' }),
  raw: (path) => call(path).then(() => fetch(path, { headers: { Authorization: `Bearer ${token()}` } }))
}
