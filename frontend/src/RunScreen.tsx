import { useEffect, useMemo } from 'react'
import { useAgentStream } from './useAgentStream'
import { TOOL_ENDPOINT } from './types'
import type { RunEvent } from './types'

type Step = {
  tool: string
  args: Record<string, unknown>
  summary?: string
  latency_ms?: number
  status: 'running' | 'ok' | 'error'
}

function toSteps(events: RunEvent[]): Step[] {
  const steps: Step[] = []
  for (const ev of events) {
    if (ev.type === 'step_start') {
      steps.push({ tool: ev.tool || '?', args: ev.args || {}, status: 'running' })
    } else if (ev.type === 'step_result') {
      // attach to the last running step of the same tool
      for (let i = steps.length - 1; i >= 0; i--) {
        if (steps[i].tool === ev.tool && steps[i].status === 'running') {
          steps[i].summary = ev.summary
          steps[i].latency_ms = ev.latency_ms
          steps[i].status = ev.status === 'error' ? 'error' : 'ok'
          break
        }
      }
    }
  }
  return steps
}

function argLine(tool: string, args: Record<string, unknown>): string {
  if (tool === 'affinity_scan') return `signal=${String(args.entity_id ?? '').slice(0, 14)}… · type=urn:entity:${args.domain}`
  if (tool === 'resolve_entity') return `query="${args.name}"${args.type ? ` · types=urn:entity:${args.type}` : ''}`
  if (tool === 'get_tags') return `filter.query="${args.query}"`
  return JSON.stringify(args)
}

export function RunScreen({ runId, brand, onDone }: { runId: string; brand?: string; onDone: (resultId: string) => void }) {
  const { events, status, resultId, error } = useAgentStream(runId)
  const steps = useMemo(() => toSteps(events), [events])
  const brandName = brand || (events.find((e) => e.type === 'run_start')?.brand ?? '')

  useEffect(() => {
    if (status === 'done' && resultId) {
      const t = setTimeout(() => onDone(resultId), 900)
      return () => clearTimeout(t)
    }
  }, [status, resultId, onDone])

  const done = steps.filter((s) => s.status !== 'running').length
  const synthesizing = events.some((e) => e.type === 'synthesizing')

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <div className="mb-1 text-sm font-medium tracking-wide text-blue-500">OVERINDEX · live investigation</div>
      <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">{brandName || 'Analyzing…'}</h1>

      <div className="mt-2 flex items-center gap-4 text-sm text-slate-500">
        <span>{steps.length} Qloo calls</span>
        <span>·</span>
        <span>
          {status === 'running'
            ? synthesizing
              ? 'synthesizing playbook…'
              : 'investigating…'
            : status === 'error'
              ? 'failed'
              : 'done'}
        </span>
        {status === 'running' && (
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-blue-500" />
        )}
      </div>

      {error && <p className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      <ol className="mt-8 space-y-3">
        {steps.map((s, i) => (
          <li
            key={i}
            className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <StatusDot status={s.status} />
                <span className="font-medium text-slate-800 dark:text-slate-200">{s.tool}</span>
              </div>
              {s.latency_ms != null && (
                <span className="text-xs text-slate-400">{s.latency_ms} ms</span>
              )}
            </div>
            <code className="mt-2 block rounded bg-slate-100 px-2 py-1 font-mono text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-400">
              {TOOL_ENDPOINT[s.tool] || 'GET'} · {argLine(s.tool, s.args)}
            </code>
            {s.summary && (
              <div className="mt-1.5 text-sm text-slate-600 dark:text-slate-400">→ {s.summary}</div>
            )}
          </li>
        ))}
        {synthesizing && (
          <li className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-700 dark:border-blue-900 dark:bg-blue-950/40 dark:text-blue-300">
            Synthesizing the audience playbook…
          </li>
        )}
      </ol>

      {steps.length === 0 && status === 'running' && (
        <p className="mt-8 text-sm text-slate-400">The agent is planning its investigation…</p>
      )}
      {status === 'done' && (
        <p className="mt-6 text-sm text-slate-500">Playbook ready — opening…</p>
      )}
      <p className="sr-only">processed {done} steps</p>
    </div>
  )
}

function StatusDot({ status }: { status: Step['status'] }) {
  if (status === 'running')
    return <span className="inline-block h-2.5 w-2.5 animate-pulse rounded-full bg-blue-500" />
  if (status === 'error') return <span className="inline-block h-2.5 w-2.5 rounded-full bg-red-500" />
  return <span className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-500" />
}
