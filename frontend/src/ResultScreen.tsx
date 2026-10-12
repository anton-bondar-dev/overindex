import { useEffect, useState, type ReactNode } from 'react'
import { getResult } from './api'
import { DOMAIN_DOT } from './types'
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
    })()
    return () => {
      cancelled = true
    }
  }, [runId])

  if (err)
    return (
      <Centered>
        <p className="text-red-600">{err}</p>
        <HomeButton onHome={onHome} />
      </Centered>
    )
  if (!result)
    return (
      <Centered>
        <span className="inline-block h-3 w-3 animate-pulse rounded-full bg-blue-500" />
        <p className="mt-3 text-slate-500">Loading playbook…</p>
      </Centered>
    )

  const bs = result.blind_spot

  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium tracking-wide text-blue-500">OVERINDEX</div>
        <button onClick={onHome} className="text-sm text-slate-500 hover:text-blue-600">
          Run another →
        </button>
      </div>

      {/* Persona */}
      <h1 className="mt-4 text-3xl font-semibold text-slate-900 dark:text-white">
        {result.persona?.name || result.brand}
      </h1>
      <p className="mt-1 text-sm text-slate-400">Audience playbook for {result.brand}</p>
      {result.persona?.narrative && (
        <p className="mt-4 text-lg leading-relaxed text-slate-700 dark:text-slate-300">
          {result.persona.narrative}
        </p>
      )}

      {/* Blind spot — the hero */}
      {bs && (
        <div className="mt-8 rounded-2xl border border-blue-200 bg-blue-50 p-6 dark:border-blue-900 dark:bg-blue-950/40">
          <div className="text-xs font-semibold uppercase tracking-wide text-blue-600 dark:text-blue-400">
            Blind spot
          </div>
          <p className="mt-2 text-xl font-medium leading-snug text-slate-900 dark:text-white">{bs.line}</p>
          <div className="mt-3 flex items-center gap-2 text-sm text-slate-500">
            <Dot domain={bs.entity.domain} />
            {bs.entity.name} · {bs.entity.domain} · affinity {fmt(bs.entity.affinity)}
          </div>
        </div>
      )}

      {/* Opportunities (grounded) */}
      <Section title="What they quietly over-index on" tag="grounded"
        sub="High relevance, lower popularity — the ownable signals.">
        <div className="space-y-2">
          {result.opportunities.slice(0, 8).map((e) => (
            <EntityRow key={e.id + e.domain} e={e} />
          ))}
        </div>
      </Section>

      {/* Taste fingerprint by domain (grounded) */}
      <Section title="Taste fingerprint by domain" tag="grounded">
        <div className="grid gap-5 sm:grid-cols-2">
          {result.domains.map((d) => (
            <div key={d.domain}>
              <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-300">
                <Dot domain={d.domain} /> {d.domain}
              </div>
              <div className="space-y-1.5">
                {d.entities.slice(0, 5).map((e) => (
                  <MiniBar key={e.id} name={e.name} value={e.affinity} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* Collaborations (proposed) */}
      {result.collaborations.length > 0 && (
        <Section title="Collaborations to pursue" tag="proposed">
          <div className="grid gap-3 sm:grid-cols-2">
            {result.collaborations.map((c, i) => (
              <div key={i} className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 font-medium text-slate-800 dark:text-slate-200">
                    <Dot domain={c.entity.domain} /> {c.entity.name}
                  </div>
                  <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-950 dark:text-blue-300">
                    {fmt(c.arbitrage)}
                  </span>
                </div>
                <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{c.pitch}</p>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Content & channels (proposed) */}
      {(result.content_themes.length > 0 || result.channels.length > 0) && (
        <Section title="Content & channels" tag="proposed">
          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-3">
              {result.content_themes.map((t, i) => (
                <div key={i}>
                  <div className="font-medium text-slate-800 dark:text-slate-200">{t.title}</div>
                  <p className="text-sm text-slate-500">{t.rationale}</p>
                </div>
              ))}
            </div>
            <div className="space-y-2">
              {result.channels.map((ch, i) => (
                <div key={i} className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                  <div className="text-sm font-medium text-slate-800 dark:text-slate-200">{ch.name}</div>
                  <p className="text-sm text-slate-500">{ch.rationale}</p>
                </div>
              ))}
            </div>
          </div>
        </Section>
      )}

      {/* Methodology (grounded transparency) */}
      <Section title="Methodology" tag="grounded" sub={`${result.qloo_calls.length} Qloo API calls`}>
        <div className="overflow-hidden rounded-lg border border-slate-200 text-sm dark:border-slate-800">
          <table className="w-full">
            <tbody>
              {result.qloo_calls.map((q, i) => (
                <tr key={i} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
                  <td className="px-3 py-1.5 font-mono text-xs text-slate-600 dark:text-slate-400">{q.endpoint}</td>
                  <td className="px-3 py-1.5 text-right text-xs text-slate-400">{q.latency_ms ?? '–'} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <p className="mt-10 text-xs text-slate-400">
        Affinities and entities come from Qloo's Taste AI. Collaborations, content and channels are the
        agent's proposals built on top of that data.
      </p>
    </div>
  )
}

function fmt(n: number | null | undefined): string {
  return n == null ? '–' : n.toFixed(2)
}

function Dot({ domain }: { domain: string }) {
  return (
    <span
      className="inline-block h-2.5 w-2.5 rounded-full"
      style={{ background: DOMAIN_DOT[domain] || '#94a3b8' }}
    />
  )
}

function EntityRow({ e }: { e: EntityAffinity }) {
  return (
    <div className="flex items-center gap-3">
      <Dot domain={e.domain} />
      <div className="w-40 shrink-0 truncate text-sm text-slate-700 dark:text-slate-300">{e.name}</div>
      <div className="h-2 flex-1 rounded bg-slate-100 dark:bg-slate-800">
        <div className="h-2 rounded" style={{ width: `${Math.round(e.affinity * 100)}%`, background: 'var(--aff-4)' }} />
      </div>
      <div className="w-24 shrink-0 text-right text-xs text-slate-400">
        pop {e.popularity == null ? '–' : Math.round(e.popularity * 100)}
      </div>
    </div>
  )
}

function MiniBar({ name, value }: { name: string; value: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="w-28 shrink-0 truncate text-xs text-slate-600 dark:text-slate-400">{name}</div>
      <div className="h-1.5 flex-1 rounded bg-slate-100 dark:bg-slate-800">
        <div className="h-1.5 rounded" style={{ width: `${Math.round(value * 100)}%`, background: 'var(--aff-3)' }} />
      </div>
    </div>
  )
}

function Section({ title, tag, sub, children }: { title: string; tag: 'grounded' | 'proposed'; sub?: string; children: ReactNode }) {
  return (
    <section className="mt-10">
      <div className="mb-3 flex items-center gap-3">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">{title}</h2>
        <ProvenanceTag tag={tag} />
      </div>
      {sub && <p className="mb-3 -mt-2 text-sm text-slate-400">{sub}</p>}
      {children}
    </section>
  )
}

function ProvenanceTag({ tag }: { tag: 'grounded' | 'proposed' }) {
  return tag === 'grounded' ? (
    <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
      Qloo data
    </span>
  ) : (
    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-950 dark:text-amber-300">
      Agent proposal
    </span>
  )
}

function Centered({ children }: { children: ReactNode }) {
  return <div className="flex min-h-screen flex-col items-center justify-center px-4 text-center">{children}</div>
}

function HomeButton({ onHome }: { onHome: () => void }) {
  return (
    <button onClick={onHome} className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
      Start over
    </button>
  )
}
