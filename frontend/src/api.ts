import type { AnalysisResult } from './types'

export async function startAnalyze(brand: string): Promise<string> {
  const r = await fetch('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ brand }),
  })
  if (!r.ok) {
    // Surface the backend's friendly detail (e.g. the rate-limit message) instead
    // of a bare status code, so a busy/limited run reads as graceful.
    let msg = `Could not start analysis (${r.status})`
    try {
      const e = await r.json()
      if (e && typeof e.detail === 'string') msg = e.detail
    } catch {
      /* non-JSON error body */
    }
    throw new Error(msg)
  }
  const d = await r.json()
  return d.run_id as string
}

/** Returns the result, or null if the run is still in progress (HTTP 202). */
export async function getResult(runId: string): Promise<AnalysisResult | null> {
  const r = await fetch(`/api/result/${runId}`)
  if (r.status === 202) return null
  if (!r.ok) throw new Error(`Could not load result (${r.status})`)
  return (await r.json()) as AnalysisResult
}

export function streamUrl(runId: string): string {
  return `/api/analyze/${runId}/stream`
}
