import type { AnalysisResult } from './types'

export async function startAnalyze(brand: string): Promise<string> {
  const r = await fetch('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ brand }),
  })
  if (!r.ok) throw new Error(`Could not start analysis (${r.status})`)
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
