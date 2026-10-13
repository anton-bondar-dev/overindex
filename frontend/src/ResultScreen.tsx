import { useEffect, useState, type ReactNode } from 'react'
import { getResult } from './api'
import { domainColor } from './types'
import type { AnalysisResult, EntityAffinity } from './types'

export function ResultScreen({ runId, onHome }: { runId: string; onHome: () => void }) {
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      for (let i = 0; i < 120 && !cancelled; i++) {
        try {
          const r = await getResult(runId)
          if (r) {
            if (!cancelled) setResult(r)
            return
          }
        } catch (e) {
          if (!cancelled) setErr(e instanceof Error ? e.message : String(e))
          return
        }
        await new Promise((res) => setTimeout(res, 2000))
      }
      if (!cancelled) setErr('This is taking longer than expected — please try again.')
    })()
    return () => {
      cancelled = true
    }
  }, [runId])

  if (err)
    return (
      <Centered>
        <p className="text-neg">{err}</p>
        <button onClick={onHome} className="mt-4 rounded-[8px] bg-accent px-4 py-2 text-sm font-medium text-text-hi">
          Start over
        </button>
      </Centered>
    )
  if (!result)
    return (
      <Centered>
        <span className="h-2.5 w-2.5 rounded-full bg-accent" style={{ animation: 'pulse-accent 1.4s infinite' }} />
        <p className="mt-3 text-text-dim">Loading playbook…</p>
      </Centered>
    )

  const bs = result.blind_spot
  const stat = `${result.domains.length} domains · ${result.domains.reduce((n, d) => n + d.entities.length, 0)} entities · ${result.qloo_calls.length} Qloo calls`
  const spine = [...result.domains].sort((a, b) => topAff(b) - topAff(a))

  return (
    <div className="mx-auto max-w-4xl px-4 pb-24">
      {/* sticky header */}
      <div className="sticky top-0 z-10 -mx-4 flex items-center justify-between border-b border-border bg-bg/85 px-4 py-3 backdrop-blur">
        <Wordmark />
        <button onClick={onHome} className="text-sm text-text-dim transition-colors hover:text-accent-hi">
          Run another →
        </button>
      </div>

      {/* persona */}
      <header className="mt-10">
        <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-text-faint">Audience playbook · {result.brand}</div>
        <h1 className="mt-2 text-4xl font-semibold tracking-[-0.02em] text-text-hi">
          {result.persona?.name || result.brand}
        </h1>
        {result.persona?.narrative && (
          <>
            <p className="mt-4 max-w-2xl text-lg leading-relaxed text-text">{result.persona.narrative}</p>
            <div className="mt-2 font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-warn">◌ the agent's reading</div>
          </>
        )}
        <div className="mono-num mt-4 text-[13px] text-text-dim">{stat}</div>
      </header>

      {result.resolution?.method === 'proxy' && result.resolution.note && (
        <div className="mt-6 rounded-[8px] border border-warn/40 bg-warn/10 px-4 py-2.5 text-sm text-text">
          <span className="font-mono text-[11px] font-semibold uppercase tracking-wide text-warn">Proxy</span>{' '}
          {result.resolution.note}
        </div>
      )}

      {/* BLIND SPOT — the hero (the one glow) */}
      {bs && (
        <div className="card glow mt-10 p-7" style={{ borderRadius: 'var(--radius-hero)' }}>
          <div className="grid gap-6 sm:grid-cols-[1fr_auto] sm:items-center">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-accent-hi">Blind spot</div>
              <p className="mt-3 text-xl font-medium leading-snug text-text-hi">{bs.line}</p>
              <div className="mt-2 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-warn">◌ agent proposal</div>
              <div className="mono-num mt-3 flex items-center gap-2 text-[13px] text-text-dim">
                <span className="text-ok" title="grounded in Qloo">●</span>
                <Dot domain={bs.entity.domain} />
                <EntityLink name={bs.entity.name} /> · {bs.entity.domain}
              </div>
            </div>
            <div className="flex flex-col items-center">
              <HeroFigure e={bs.entity} />
              <Bridge toDomain={bs.entity.domain} affinity={bs.entity.affinity} />
            </div>
          </div>
        </div>
      )}

      <AgentRecap result={result} />

      {/* OPPORTUNITIES (grounded) */}
      {result.opportunities.length > 0 && (
        <Section kind="grounded" title="What they quietly over-index on" sub="High affinity, lower reach — the ownable signals, ranked by affinity × (1 − popularity).">
          <div className="mt-4">
            <OpportunityScatter items={result.opportunities} />
          </div>
          <div className="mt-4 space-y-1.5">
            {result.opportunities.slice(0, 8).map((e) => (
              <OpportunityRow key={e.id + e.domain} e={e} maxOpp={oppScore(result.opportunities[0])} />
            ))}
          </div>
        </Section>
      )}

      {/* TASTE FINGERPRINT (grounded) */}
      {result.domains.length > 0 && (
      <Section kind="grounded" title="Taste fingerprint by domain">
        <div className="mt-3 grid gap-x-8 gap-y-5 sm:grid-cols-2">
          {spine.map((d) => (
            <div key={d.domain}>
              <div className="mb-2 flex items-center gap-2 text-sm font-medium text-text-hi">
                <Dot domain={d.domain} /> {d.domain}
              </div>
              <div className="space-y-1.5">
                {d.entities.slice(0, 5).map((e) => (
                  <AffinityBar key={e.id} e={e} compact />
                ))}
              </div>
            </div>
          ))}
        </div>
        <details className="mt-5">
          <summary className="cursor-pointer text-[13px] text-text-dim hover:text-text">Show as table</summary>
          <div className="mt-2 overflow-hidden rounded-[8px] border border-border">
            <table className="mono-num w-full text-[12px]">
              <tbody>
                {spine.flatMap((d) =>
                  d.entities.slice(0, 5).map((e) => (
                    <tr key={e.id} className="border-b border-border last:border-0">
                      <td className="px-3 py-1 text-text-dim">{e.domain}</td>
                      <td className="px-3 py-1 text-text"><EntityLink name={e.name} /></td>
                      <td className="px-3 py-1 text-right text-text-dim">{e.affinity.toFixed(2)}</td>
                      <td className="px-3 py-1 text-right text-text-faint">pop {pct(e.popularity)}</td>
                    </tr>
                  )),
                )}
              </tbody>
            </table>
          </div>
        </details>
      </Section>
      )}

      {/* COLLABORATIONS (proposed) */}
      {result.collaborations.length > 0 && (
        <Section kind="proposed" title="Collaborations to pursue">
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {result.collaborations.map((c, i) => (
              <div key={i} className="card p-4 transition-transform duration-200 hover:-translate-y-0.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 font-medium text-text-hi">
                    <Dot domain={c.entity.domain} /> <EntityLink name={c.entity.name} />
                  </div>
                  <span className="mono-num text-[12px] text-text-dim">{c.arbitrage.toFixed(2)}</span>
                </div>
                <p className="mt-2 text-sm text-text">{c.pitch}</p>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* CONTENT & CHANNELS (proposed) */}
      {(result.content_themes.length > 0 || result.channels.length > 0) && (
        <Section kind="proposed" title="Content & channels">
          <div className="mt-3 grid gap-6 sm:grid-cols-2">
            <div className="space-y-3">
              {result.content_themes.map((t, i) => (
                <div key={i}>
                  <div className="font-medium text-text-hi">{t.title}</div>
                  <p className="text-sm text-text-dim">{t.rationale}</p>
                </div>
              ))}
            </div>
            <div className="space-y-2">
              {result.channels.map((ch, i) => (
                <div key={i} className="card p-3 transition-transform duration-200 hover:-translate-y-0.5">
                  <div className="text-sm font-medium text-text-hi">{ch.name}</div>
                  <p className="text-sm text-text-dim">{ch.rationale}</p>
                </div>
              ))}
            </div>
          </div>
        </Section>
      )}

      {/* METHODOLOGY (grounded) */}
      {result.qloo_calls.length > 0 && (
      <Section kind="grounded" title="Methodology" sub={`${result.qloo_calls.length} real Qloo API calls`}>
        <div className="mt-3 overflow-hidden rounded-[8px] border border-border">
          <table className="mono-num w-full text-[12px]">
            <tbody>
              {result.qloo_calls.map((q, i) => (
                <tr key={i} className="border-b border-border last:border-0">
                  <td className="px-3 py-1.5 text-text-dim">{q.endpoint}</td>
                  <td className="px-3 py-1.5 text-right text-text-faint">{q.latency_ms ?? '–'} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
      )}

      <p className="mt-12 text-[12px] text-text-faint">
        Scores are Qloo Taste AI signals — affinity (0–100, relevance to this audience) and popularity (0–100,
        general reach). Entities and affinities are grounded in Qloo (<span className="text-ok">●</span>); collaborations,
        content and channels are the agent's proposals on top of that data (<span className="text-warn">◌</span>). Entity
        names link to a web search.
      </p>
    </div>
  )
}

/* ---------- helpers ---------- */

function topAff(d: { entities: EntityAffinity[] }): number {
  return d.entities.length ? Math.max(...d.entities.map((e) => e.affinity)) : 0
}
function pct(n?: number | null): string {
  return n == null ? '–' : String(Math.round(n * 100))
}

function searchUrl(name: string): string {
  return `https://www.google.com/search?q=${encodeURIComponent(name)}`
}

/** Entity names link out to a web search — so a curious reader (or a judge) can
 *  see what a surprising, niche or truncated title actually is. */
function EntityLink({ name, className }: { name: string; className?: string }) {
  return (
    <a
      href={searchUrl(name)}
      target="_blank"
      rel="noopener noreferrer"
      title={name}
      className={`transition-colors hover:text-accent-hi hover:underline underline-offset-2 ${className ?? ''}`}
    >
      {name}
    </a>
  )
}

function Wordmark() {
  return (
    <div className="flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.1em] text-text-dim">
      <span className="h-1.5 w-1.5 rounded-full bg-accent" />
      OVERINDEX
    </div>
  )
}

function Dot({ domain }: { domain: string }) {
  return <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: domainColor(domain) }} />
}

const ALL_DOMAINS = ['artist', 'movie', 'tv_show', 'book', 'brand', 'place', 'podcast', 'videogame']

/** Makes the agent's autonomy legible on the result page (survives a screenshot):
 *  which cultural domains it chose to scan, which it skipped, how many Qloo calls. */
function AgentRecap({ result }: { result: AnalysisResult }) {
  const scanned = new Set(result.domains.map((d) => d.domain))
  return (
    <div className="card mt-6 p-4" style={{ borderRadius: 'var(--radius-ctl)' }}>
      <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-text-faint">How the agent investigated</div>
      <p className="mt-2 text-sm text-text">
        It resolved <span className="text-text-hi">{result.brand}</span> in Qloo, then autonomously chose{' '}
        <span className="text-text-hi">{scanned.size} of {ALL_DOMAINS.length}</span> cultural domains to scan — skipping the
        rest — and stopped once the signal was clear.
      </p>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {ALL_DOMAINS.map((d) => {
          const on = scanned.has(d)
          return (
            <span
              key={d}
              className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[11px] ${on ? 'border-border-strong text-text' : 'border-border text-text-faint opacity-50'}`}
            >
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: on ? domainColor(d) : 'var(--color-text-faint)' }} />
              {d}
            </span>
          )
        })}
      </div>
      <div className="mono-num mt-3 text-[12px] text-text-dim">
        {result.qloo_calls.length} live Qloo calls · {scanned.size} domains scanned
      </div>
    </div>
  )
}

function HeroFigure({ e }: { e: EntityAffinity }) {
  // Honest magnitude: Qloo's raw 0–100 affinity (how much THIS audience is into
  // it) alongside its general popularity. The gap between the two — loved yet
  // niche — is the over-index, shown rather than reduced to a fake multiplier.
  const pop = e.popularity != null ? Math.round(e.popularity * 100) : null
  return (
    <div className="text-center">
      <div className="mono-num text-5xl font-semibold tracking-tight text-text-hi">{Math.round(e.affinity * 100)}</div>
      <div className="mt-1 text-[11px] uppercase tracking-wide text-text-faint">audience affinity</div>
      {pop != null && <div className="mono-num mt-2 text-[11px] text-text-dim">{pop} popularity</div>}
      <div className="mt-2 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-ok">● Qloo data</div>
    </div>
  )
}

function Bridge({ toDomain, affinity }: { toDomain: string; affinity: number }) {
  const w = 240
  const h = 64
  const y = h - 16
  const sw = 2 + affinity * 4
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="mt-4 w-[220px]" aria-hidden>
      <path
        d={`M 20 ${y} Q ${w / 2} 8 ${w - 20} ${y}`}
        fill="none"
        stroke="var(--color-aff-bar)"
        strokeWidth={sw}
        strokeLinecap="round"
        style={{ strokeDasharray: 360, strokeDashoffset: 360, animation: 'draw 700ms var(--ease-out) forwards' }}
      />
      <circle cx="20" cy={y} r="9" fill={domainColor('brand')} />
      <circle cx={w - 20} cy={y} r="9" fill={domainColor(toDomain)} />
    </svg>
  )
}

function AffinityBar({ e, compact }: { e: EntityAffinity; compact?: boolean }) {
  return (
    <div className={`group grid items-center gap-2.5 rounded-[6px] -mx-2 px-2 py-0.5 transition-colors hover:bg-surface-2 ${compact ? 'grid-cols-[1fr_72px_3.5ch]' : 'grid-cols-[14px_1fr_96px_4ch]'}`}>
      {!compact && <Dot domain={e.domain} />}
      <EntityLink name={e.name} className="block truncate text-sm text-text" />
      <div className="h-1.5 rounded-full" style={{ background: 'var(--color-aff-track)' }}>
        <div
          className="h-1.5 rounded-full transition-[width] duration-500"
          style={{ width: `${Math.round(e.affinity * 100)}%`, background: 'var(--color-aff-bar)' }}
        />
      </div>
      <div className="mono-num text-right text-[12px] text-text-dim">{Math.round(e.affinity * 100)}</div>
    </div>
  )
}

function oppScore(e: EntityAffinity): number {
  return e.affinity * (1 - (e.popularity ?? 0.5))
}

/** An "ownable" row: the bar encodes the OPPORTUNITY score (affinity × (1 − popularity))
 *  normalized to the top row, so the always-visible bars match the ranking; the numbers
 *  show both affinity and popularity so "high affinity, lower reach" is legible. */
function OpportunityRow({ e, maxOpp }: { e: EntityAffinity; maxOpp: number }) {
  const aff = Math.round(e.affinity * 100)
  const pop = e.popularity != null ? Math.round(e.popularity * 100) : null
  const barPct = Math.max(4, Math.round((oppScore(e) / (maxOpp || 1)) * 100))
  return (
    <div className="group grid grid-cols-[14px_1fr_90px_auto] items-center gap-2.5 rounded-[6px] -mx-2 px-2 py-0.5 transition-colors hover:bg-surface-2">
      <Dot domain={e.domain} />
      <EntityLink name={e.name} className="block truncate text-sm text-text" />
      <div className="h-1.5 rounded-full" style={{ background: 'var(--color-aff-track)' }}>
        <div className="h-1.5 rounded-full transition-[width] duration-500" style={{ width: `${barPct}%`, background: 'var(--color-aff-bar)' }} />
      </div>
      <div className="mono-num whitespace-nowrap text-right text-[11px] text-text-dim">
        <span className="text-text">aff {aff}</span> · pop {pop ?? '–'}
      </div>
    </div>
  )
}

function OpportunityScatter({ items }: { items: EntityAffinity[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const pts = items.filter((e) => e.popularity != null)
  if (pts.length < 3) return null
  const W = 480, H = 360, L = 48, R = 16, T = 16, B = 40
  // Auto-scale both axes to the data range (+pad). Qloo affinities among the top
  // opportunities cluster tightly (~0.90–0.98); on a fixed 0–1 axis every point
  // collapses into a thin strip at the top. Scaling to the actual spread makes
  // it a real scatter.
  const affs = pts.map((e) => e.affinity)
  const pops = pts.map((e) => e.popularity as number)
  const aLo = Math.min(...affs), aHi = Math.max(...affs)
  const pLo = Math.min(...pops), pHi = Math.max(...pops)
  const aPad = (aHi - aLo) * 0.15 || 0.02
  const pPad = (pHi - pLo) * 0.15 || 0.02
  const a0 = aLo - aPad, a1 = aHi + aPad
  const p0 = pLo - pPad, p1 = pHi + pPad
  const x = (pop: number) => L + ((pop - p0) / (p1 - p0)) * (W - L - R)
  const y = (aff: number) => T + (1 - (aff - a0) / (a1 - a0)) * (H - T - B)
  const ownableX = p0 + (p1 - p0) * 0.4   // low-popularity (left) zone = most ownable
  const hidden = items.length - pts.length
  const tfaint = { fill: 'var(--color-text-faint)' } as const
  // No direct per-point labels: labelling only a few points reads as a bug, and
  // labelling all of them overlaps into noise. Every point is identified the same
  // way — on hover (the tooltip below).

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        <rect x={L} y={T} width={x(ownableX) - L} height={H - B - T} fill="var(--color-aff-bar)" opacity={0.07} />
        <line x1={x(ownableX)} y1={T} x2={x(ownableX)} y2={H - B} stroke="var(--color-aff-bar)" strokeOpacity={0.25} strokeDasharray="3 3" />
        <text x={L + 6} y={T + 13} style={{ ...tfaint, fontSize: 9, letterSpacing: '0.08em' }}>OWNABLE</text>
        <line x1={L} y1={H - B} x2={W - R} y2={H - B} stroke="var(--color-border-strong)" />
        <line x1={L} y1={T} x2={L} y2={H - B} stroke="var(--color-border-strong)" />
        <text x={(L + W - R) / 2} y={H - 8} textAnchor="middle" style={{ ...tfaint, fontSize: 10 }}>popularity →</text>
        <text x={14} y={(T + H - B) / 2} textAnchor="middle" transform={`rotate(-90 14 ${(T + H - B) / 2})`} style={{ ...tfaint, fontSize: 10 }}>affinity →</text>
        {pts.map((e, i) => {
          const cx = x(e.popularity as number)
          const cy = y(e.affinity)
          return (
            <g key={e.id} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onClick={() => setHover((h) => (h === i ? null : i))} style={{ cursor: 'pointer' }}>
              <circle cx={cx} cy={cy} r={13} fill="transparent" />
              <circle cx={cx} cy={cy} r={hover === i ? 7 : 6} fill="var(--color-aff-bar)" fillOpacity={0.4 + oppScore(e) * 0.6} stroke="var(--color-ring)" strokeWidth={2} />
            </g>
          )
        })}
        {/* labels intentionally omitted — identify any point on hover (consistent for all) */}
      </svg>
      {hover != null && pts[hover] && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-[6px] border border-border bg-surface-2 px-2 py-1"
          style={{ left: `${(x(pts[hover].popularity as number) / W) * 100}%`, top: `${(y(pts[hover].affinity) / H) * 100}%`, marginTop: -6 }}
        >
          <div className="mono-num whitespace-nowrap text-[11px] text-text-hi">
            affinity {Math.round(pts[hover].affinity * 100)} · popularity {pct(pts[hover].popularity)}
          </div>
          <div className="mt-0.5 flex items-center gap-1 whitespace-nowrap text-[11px] text-text-dim">
            <Dot domain={pts[hover].domain} /> {pts[hover].name}
          </div>
        </div>
      )}
      <div className="mt-1 flex justify-between text-[11px] text-text-faint">
        <span>Tap or hover a point for detail</span>
        {hidden > 0 && <span>{hidden} with unknown reach not shown</span>}
      </div>
    </div>
  )
}

function Prov({ kind }: { kind: 'grounded' | 'proposed' }) {
  return (
    <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-text-dim">
      {kind === 'grounded' ? (
        <>
          <span className="text-ok">●</span> Qloo data
        </>
      ) : (
        <>
          <span className="text-warn">◌</span> Agent proposal
        </>
      )}
    </span>
  )
}

function Section({ kind, title, sub, children }: { kind: 'grounded' | 'proposed'; title: string; sub?: string; children: ReactNode }) {
  return (
    <section
      className="mt-12 border-l-2 pl-4"
      style={{ borderColor: kind === 'grounded' ? 'var(--color-ok)' : 'var(--color-warn)' }}
    >
      <div className="flex items-center gap-3">
        <h2 className="text-xl font-semibold tracking-tight text-text-hi">{title}</h2>
        <Prov kind={kind} />
      </div>
      {sub && <p className="mt-1 text-sm text-text-dim">{sub}</p>}
      {children}
    </section>
  )
}

function Centered({ children }: { children: ReactNode }) {
  return <div className="flex min-h-screen flex-col items-center justify-center px-4 text-center">{children}</div>
}
