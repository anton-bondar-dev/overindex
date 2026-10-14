/**
 * Demo mode — a self-playing, precisely-paced walkthrough used ONLY to record
 * the promo video. Gated entirely on the `?demo=<slug>` query param. When the
 * param is absent, DEMO.on is false and every call site is a no-op, so the real
 * product (what judges drive themselves) behaves exactly as before.
 *
 * Example: https://overindex.overpro.fit/?demo=patagonia
 */
export type DemoConfig = {
  on: boolean
  brand: string
  // input typing
  startHold: number
  charMs: number
  jitter: number
  holdBeforeSubmit: number
  // paced trace
  firstStepDelay: number
  runningDwell: number
  resolvedHold: number
  tvShowExtra: number
  convergeDwell: number
  counterBeat: number
  // results scroll
  legMs: number
  dwell: Record<string, number>
}

const SLUGS: Record<string, string> = {
  patagonia: 'Patagonia',
  a24: 'A24',
  'blue-bottle-coffee': 'Blue Bottle Coffee',
  'liquid-death': 'Liquid Death',
}

function read(): DemoConfig {
  let slug = ''
  try {
    slug = (new URLSearchParams(window.location.search).get('demo') || '').toLowerCase()
  } catch {
    /* no window / SSR */
  }
  const brand =
    SLUGS[slug] ||
    (slug ? slug.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : '')
  return {
    on: !!slug,
    brand,
    startHold: 1500,
    charMs: 185,
    jitter: 40,
    holdBeforeSubmit: 650,
    firstStepDelay: 700,
    runningDwell: 1000,
    resolvedHold: 750,
    tvShowExtra: 600,
    convergeDwell: 1800,
    counterBeat: 2500,
    legMs: 900,
    dwell: { persona: 2800, blindSpot: 3500, scatter: 2800, fingerprint: 1800, moves: 1800, methodology: 2500 },
  }
}

export const DEMO = read()

// Force motion ON even under prefers-reduced-motion (the capture must animate),
// and hide the OS cursor so no stray pointer shows on camera.
if (DEMO.on && typeof document !== 'undefined') {
  document.documentElement.setAttribute('data-demo', '')
  document.documentElement.style.cursor = 'none'
  // Always (re)start from the input screen, even when reloading a deep link, so a
  // re-take is just Cmd+R.
  if (window.location.hash) {
    history.replaceState(null, '', window.location.pathname + window.location.search)
  }
}

export const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))
export const jittered = (base: number, j: number) => Math.max(40, base + (Math.random() * 2 - 1) * j)
