import { useState } from 'react'
import { startAnalyze } from './api'

const EXAMPLES = ['Patagonia', 'A24', 'Blue Bottle Coffee', 'Liquid Death']

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
      const runId = await startAnalyze(v)
      onStart(runId)
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e))
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center px-4 py-16">
      <div className="mb-2 text-sm font-medium tracking-wide text-blue-500">OVERINDEX</div>
      <h1 className="text-3xl font-semibold leading-tight text-slate-900 sm:text-4xl dark:text-white">
        What does your audience <span className="text-blue-600 dark:text-blue-400">really</span> love?
      </h1>
      <p className="mt-3 text-slate-600 dark:text-slate-400">
        Type a brand. An AI analyst investigates its cultural audience across music, film, books,
        brands and places — live — then hands you a marketing playbook built on what they over-index on.
      </p>

      <form
        className="mt-8"
        onSubmit={(e) => {
          e.preventDefault()
          void go(brand)
        }}
      >
        <div className="flex gap-2">
          <input
            autoFocus
            value={brand}
            onChange={(e) => setBrand(e.target.value)}
            placeholder="e.g. Blue Bottle Coffee"
            disabled={loading}
            className="w-full rounded-lg border border-slate-300 bg-white px-4 py-3 text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-white dark:focus:ring-blue-900"
          />
          <button
            type="submit"
            disabled={loading}
            className="shrink-0 rounded-lg bg-blue-600 px-5 py-3 font-medium text-white transition hover:bg-blue-700 disabled:opacity-60"
          >
            {loading ? 'Starting…' : 'Analyze'}
          </button>
        </div>
      </form>

      {err && <p className="mt-3 text-sm text-red-600">{err}</p>}

      <div className="mt-6">
        <div className="mb-2 text-xs uppercase tracking-wide text-slate-400">Or try one</div>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              disabled={loading}
              onClick={() => {
                setBrand(ex)
                void go(ex)
              }}
              className="rounded-full border border-slate-300 px-3 py-1.5 text-sm text-slate-700 transition hover:border-blue-500 hover:text-blue-600 disabled:opacity-60 dark:border-slate-700 dark:text-slate-300"
            >
              {ex}
            </button>
          ))}
        </div>
      </div>

      <p className="mt-10 text-xs text-slate-400">
        Grounded in Qloo's Taste AI. Novel brands take ~30s; examples are instant.
      </p>
    </div>
  )
}
