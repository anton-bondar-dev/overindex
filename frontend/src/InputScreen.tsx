import { useState } from 'react'
import { startAnalyze } from './api'
import { domainColor } from './types'

const EXAMPLES: Array<[string, string]> = [
  ['Patagonia', 'place'],
  ['A24', 'movie'],
  ['Blue Bottle Coffee', 'brand'],
  ['Liquid Death', 'artist'],
]

export function InputScreen({ onStart }: { onStart: (runId: string) => void }) {
  const [brand, setBrand] = useState('')
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  async function go(value: string) {
    const v = value.trim()
    if (v.length < 2) {
      setErr('Enter a brand name.')
      return
    }
    setLoading(true)
    setErr('')
    try {
      onStart(await startAnalyze(v))
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center px-4 py-16">
      <div className="flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.1em] text-text-dim">
        <span className="h-1.5 w-1.5 rounded-full bg-accent" />
        OVERINDEX
      </div>

      <h1 className="mt-6 text-4xl font-semibold leading-[1.1] tracking-[-0.02em] text-text-hi sm:text-5xl">
        What does your audience <span className="text-accent">really</span> love?
      </h1>
      <p className="mt-4 max-w-xl text-text-dim">
        Type a brand. An AI analyst investigates its cultural audience across music, film, books, brands and
        places — live — then hands you a marketing playbook built on what they over-index on.
      </p>

      <form
        className="mt-8 flex flex-col gap-2 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault()
          void go(brand)
        }}
      >
        <input
          autoFocus
          value={brand}
          onChange={(e) => setBrand(e.target.value)}
          placeholder="e.g. Blue Bottle Coffee"
          disabled={loading}
          className="card focus-accent w-full px-4 py-3 text-text-hi placeholder:text-text-faint disabled:opacity-60"
          style={{ borderRadius: 'var(--radius-ctl)' }}
        />
        <button
          type="submit"
          disabled={loading}
          className="shrink-0 bg-accent px-5 py-3 font-medium text-text-hi transition-opacity hover:opacity-90 disabled:opacity-60"
          style={{ borderRadius: 'var(--radius-ctl)' }}
        >
          {loading ? 'Starting…' : 'Analyze'}
        </button>
      </form>

      {err && (
        <p className="mt-3 text-sm text-neg">
          {err} <span className="text-text-dim">— or try a ready example below, they open instantly.</span>
        </p>
      )}

      <div className="mt-6">
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-text-faint">Or try one</div>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map(([label, domain]) => (
            <button
              key={label}
              disabled={loading}
              onClick={() => {
                setBrand(label)
                void go(label)
              }}
              className="flex items-center gap-2 rounded-full border border-border px-3 py-1.5 font-mono text-[13px] text-text transition-colors hover:border-border-strong disabled:opacity-60"
            >
              <span className="h-2 w-2 rounded-full" style={{ background: domainColor(domain) }} />
              {label}
            </button>
          ))}
        </div>
      </div>

      <p className="mt-12 text-[11px] uppercase tracking-[0.08em] text-text-faint">
        Grounded in Qloo's Taste AI · novel brands ~30s
      </p>
    </div>
  )
}
