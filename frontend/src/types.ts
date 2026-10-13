// Mirrors the backend AnalysisResult + RunEvent contract (models.py).

export type RunEvent = {
  type: string
  id?: string
  tool?: string
  args?: Record<string, unknown>
  summary?: string
  latency_ms?: number
  status?: string
  text?: string
  brand?: string
  note?: string
  count?: number
  message?: string
  result_id?: string
}

export type EntityAffinity = {
  id: string
  name: string
  domain: string
  affinity: number
  popularity?: number | null
  lift?: number | null
  image?: string | null
  tags?: string[]
}

export type DomainAffinities = { domain: string; entities: EntityAffinity[] }
export type BlindSpot = { entity: EntityAffinity; line: string }
export type Collaboration = {
  entity: EntityAffinity
  arbitrage: number
  cross_domain: boolean
  pitch: string
}
export type ContentTheme = { title: string; rationale: string; angles?: string[] }
export type Channel = { name: string; fit?: number | null; rationale: string }
export type Persona = { name: string; narrative: string; defining_tastes: EntityAffinity[] }
export type QlooCall = {
  endpoint: string
  params: Record<string, unknown>
  latency_ms?: number | null
}

export type Resolution = {
  query: string
  resolved_name?: string | null
  method: string // "direct" | "proxy"
  note?: string | null
}

export type AnalysisResult = {
  id: string
  brand: string
  created_at: string
  resolution?: Resolution | null
  persona?: Persona | null
  blind_spot?: BlindSpot | null
  domains: DomainAffinities[]
  opportunities: EntityAffinity[]
  collaborations: Collaboration[]
  content_themes: ContentTheme[]
  channels: Channel[]
  qloo_calls: QlooCall[]
}

// Which Qloo endpoint each agent tool maps to — for the "real call" chip.
export const TOOL_ENDPOINT: Record<string, string> = {
  resolve_entity: 'GET /search',
  affinity_scan: 'GET /v2/insights',
}

// Domain identity is a text-paired dot ONLY, never a data mark. [light, dark].
// CVD-validated 8-slot set (tv_show = teal; slate failed the validator).
export const DOMAIN_COLOR: Record<string, [string, string]> = {
  brand: ['#2a78d6', '#3987e5'],
  artist: ['#eb6834', '#d95926'],
  book: ['#1baf7a', '#199e70'],
  movie: ['#eda100', '#c98500'],
  place: ['#e87ba4', '#d55181'],
  videogame: ['#008300', '#008300'],
  tv_show: ['#0d8ba3', '#0aa6c4'],
  podcast: ['#e34948', '#e66767'],
}

/** Dark-mode dot color for a domain (we ship dark). */
export function domainColor(domain: string): string {
  return (DOMAIN_COLOR[domain] ?? ['#8a8f98', '#8a8f98'])[1]
}
