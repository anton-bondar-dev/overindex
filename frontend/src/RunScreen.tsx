import { useEffect, useMemo, useState } from 'react'
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

function verb(tool: string, args: Record<string, unknown>): string {
  if (tool === 'resolve_entity') return `Locating ${args.name ? `"${args.name}"` : 'the brand'}`
  if (tool === 'affinity_scan') return `Scanning ${args.domain ?? 'affinities'}`
  if (tool === 'get_tags') return 'Mapping the tag vocabulary'
  return tool
}

function reason(tool: string, args: Record<string, unknown>): string {
  if (tool === 'resolve_entity') return `Pinning this brand in Qloo's taste graph…`
  if (tool === 'affinity_scan') return `Reading who over-indexes on this audience in ${args.domain ?? 'this domain'}…`
  if (tool === 'get_tags') return `Reading the tag cloud around the brand…`
  return 'Working…'
}

function endpointLine(tool: string, args: Record<string, unknown>): string {
  const ep = TOOL_ENDPOINT[tool] || 'GET'
  if (tool === 'affinity_scan') return `${tool} · ${ep} · type=urn:entity:${args.domain}`
  if (tool === 'resolve_entity') return `${tool} · ${ep} · query="${args.name ?? ''}"`
  if (tool === 'get_tags') return `${tool} · ${ep} · filter.query="${args.query ?? ''}"`
  return `${tool} · ${ep}`
}

const PLAN = ['Locate', 'Scan', 'Map', 'Assemble']
function planActive(steps: Step[], synthesizing: boolean): Set<string> {
  const a = new Set<string>()
  for (const s of steps) {
    if (s.tool === 'resolve_entity') a.add('Locate')
    if (s.tool === 'affinity_scan') a.add('Scan')
    if (s.tool === 'get_tags') a.add('Map')
  }
  if (synthesizing) a.add('Assemble')
  return a
}

export function RunScreen({ runId, onDone, onHome }: { runId: string; onDone: () => void; onHome: () => void }) {
  const { events, status, error } = useAgentStream(runId)
  const steps = useMemo(() => toSteps(events), [events])
  const synthesizing = events.some((e) => e.type === 'synthesizing')
  const brand = events.find((e) => e.type === 'run_start')?.brand ?? ''

  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (status !== 'running') return
    const t = setInterval(() => setElapsed((e) => e + 1), 1000)
    return () => clearInterval(t)
  }, [status])
  const mmss = `${String(Math.floor(elapsed / 60)).padStart(2, '0')}:${String(elapsed % 60).padStart(2, '0')}`

  useEffect(() => {
    if (status === 'done') {
      const t = setTimeout(onDone, 1100)
      return () => clearTimeout(t)
    }
  }, [status, onDone])

  const active = planActive(steps, synthesizing)
  const lastRunningIdx = steps.map((s) => s.status).lastIndexOf('running')

  return (
    <div className="mx-auto max-w-3xl px-4 pb-24">
      {/* sticky contract header */}
      <div className="sticky top-0 z-10 -mx-4 border-b border-border bg-bg/85 px-4 py-4 backdrop-blur">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.1em] text-text-dim">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" style={{ animation: 'pulse-accent 1.6s infinite' }} />
            OVERINDEX · live investigation
          </div>
          <div className="flex items-center gap-4 font-mono text-xs tabular-nums text-text-dim">
            <span>{mmss}</span>
            <span>{steps.length} / ~6 calls</span>
            <button onClick={onHome} className="transition-colors hover:text-accent-hi">↩ start over</button>
          </div>
        </div>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-text-hi">{brand || 'Analyzing…'}</h1>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {PLAN.map((p) => (
            <span
              key={p}
              className={
                'rounded-full border px-2 py-0.5 text-[11px] font-medium transition-colors ' +
                (active.has(p)
                  ? 'border-accent/40 bg-accent-dim text-accent-hi'
                  : 'border-border text-text-faint')
              }
            >
              {p}
            </span>
          ))}
        </div>
      </div>

      {status === 'error' && (
        <div className="mt-5 rounded-lg border border-err/30 bg-err/10 px-4 py-3">
          <p className="text-sm text-err">{error || 'Something went wrong with this run.'}</p>
          <button
            onClick={onHome}
            className="mt-2 rounded-[8px] bg-accent px-3 py-1.5 text-sm font-medium text-text-hi transition-opacity hover:opacity-90"
          >
            Start over
          </button>
        </div>
      )}

      {/* the rail */}
      <ol className="relative mt-8 space-y-0 pl-6">
        <span className="absolute bottom-2 left-[5px] top-2 w-px bg-border" aria-hidden />
        {steps.map((s, i) => {
          const isActive = i === lastRunningIdx
          const done = s.status !== 'running'
          return (
            <li key={i} className="relative pb-5" style={{ animation: 'drop-in 220ms var(--ease-out)' }}>
              <span
                className="absolute -left-6 top-1.5 h-[11px] w-[11px] rounded-full ring-2 ring-bg"
                style={
                  s.status === 'running'
                    ? { background: 'var(--color-accent)', animation: 'pulse-accent 1.4s infinite' }
                    : s.status === 'error'
                      ? { background: 'transparent', boxShadow: 'inset 0 0 0 2px var(--color-err)' }
                      : { background: 'var(--color-ok)' }
                }
              />
              <div className={done && !isActive ? 'opacity-55 transition-opacity' : ''}>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-sm font-medium text-text-hi">{verb(s.tool, s.args)}</span>
                  {s.latency_ms != null && (
                    <span className="font-mono text-[11px] tabular-nums text-text-faint">{(s.latency_ms / 1000).toFixed(1)}s</span>
                  )}
                </div>

                {/* running: reasoning + live endpoint strip; done: one-line result */}
                {s.status === 'running' ? (
                  <>
                    <p className="mt-1 text-sm text-text-dim">{reason(s.tool, s.args)}</p>
                    <div className="relative mt-2 overflow-hidden rounded-[6px] bg-surface-2 px-2 py-1">
                      <code className="font-mono text-[12px] text-text-dim">{endpointLine(s.tool, s.args)}</code>
                      <span
                        className="absolute inset-y-0 left-0 w-1/3"
                        style={{
                          background: 'linear-gradient(90deg, transparent, var(--color-accent-dim), transparent)',
                          animation: 'shimmer 1.2s linear infinite',
                        }}
                      />
                    </div>
                  </>
                ) : (
                  <>
                    <code className="mt-1 block font-mono text-[11px] text-text-faint">{endpointLine(s.tool, s.args)}</code>
                    {s.summary && <p className="mt-1 text-sm text-text">→ {s.summary}</p>}
                  </>
                )}
              </div>
            </li>
          )
        })}

        {/* convergence / synthesizing */}
        {(synthesizing || status === 'done') && (
          <li className="relative pb-2" style={{ animation: 'drop-in 220ms var(--ease-out)' }}>
            <span
              className="absolute -left-6 top-1.5 h-[11px] w-[11px] rounded-full ring-2 ring-bg"
              style={
                status === 'done'
                  ? { background: 'var(--color-accent)' }
                  : { background: 'transparent', boxShadow: 'inset 0 0 0 2px var(--color-accent)', animation: 'pulse-accent 1.4s infinite' }
              }
            />
            <span className="text-sm font-medium text-accent-hi">
              {status === 'done' ? 'Playbook ready — opening…' : 'Assembling the playbook…'}
            </span>
          </li>
        )}
      </ol>

      {steps.length === 0 && status === 'running' && (
        <p className="mt-6 pl-6 text-sm text-text-dim">The agent is planning its investigation…</p>
      )}
    </div>
  )
}
