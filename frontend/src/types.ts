// Mirrors the backend AnalysisResult + RunEvent contract (models.py).

export type RunEvent = {
  type: string
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

export type AnalysisResult = {
  id: string
  brand: string
  created_at: string
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
  get_tags: 'GET /v2/tags',
}

export const DOMAIN_DOT: Record<string, string> = {
  artist: '#f472b6',
  movie: '#f59e0b',
  tv_show: '#a78bfa',
  book: '#34d399',
  brand: '#60a5fa',
  place: '#22d3ee',
  podcast: '#fb7185',
  videogame: '#4ade80',
}
