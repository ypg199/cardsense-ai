/**
 * api.js — All fetch calls in one place.
 * Base URL is read from VITE_API_URL (default: empty string → proxied by Vite).
 */

const BASE = import.meta.env.VITE_API_URL || ''

async function request(method, path, body, isFormData = false) {
  const opts = {
    method,
    headers: isFormData ? {} : { 'Content-Type': 'application/json' },
    body: isFormData ? body : body ? JSON.stringify(body) : undefined,
  }
  const res = await fetch(`${BASE}${path}`, opts)
  const data = await res.json()
  if (!res.ok) throw Object.assign(new Error(data.detail || 'Request failed'), { status: res.status, data })
  return data
}

// ── Cards ────────────────────────────────────────────────────────────────────
export const getCards = (params = {}) => {
  const q = new URLSearchParams(params).toString()
  return request('GET', `/cards${q ? '?' + q : ''}`)
}
export const searchCards = (q) => request('GET', `/cards/search?q=${encodeURIComponent(q)}`)
export const getCard = (id) => request('GET', `/cards/${id}`)

// ── Sessions ─────────────────────────────────────────────────────────────────
export const startSession = (formData) => request('POST', '/session/start', formData, true)
export const submitPassword = (sessionId, payload) => request('POST', `/session/${sessionId}/password`, payload)
export const submitAnswer = (sessionId, payload) => request('POST', `/session/${sessionId}/answer`, payload)
export const getSessionStatus = (sessionId) => request('GET', `/session/${sessionId}/status`)
export const getSpendSummary = (sessionId, cardId) =>
  request('GET', `/session/${sessionId}/spend${cardId ? `?card_id=${encodeURIComponent(cardId)}` : ''}`)
export const addCard = (sessionId, formData) => request('POST', `/session/${sessionId}/add_card`, formData, true)

// ── Crawl (admin) ─────────────────────────────────────────────────────────────
export const triggerCrawl = (payload) => request('POST', '/crawl', payload)
export const getCrawlJobs = () => request('GET', '/crawl/jobs')
