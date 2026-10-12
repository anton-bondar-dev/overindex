import { useEffect, useRef, useState } from 'react'
import type { RunEvent } from './types'
import { getResult, streamUrl } from './api'

export type StreamStatus = 'running' | 'done' | 'error'
export type StreamState = {
  events: RunEvent[]
  status: StreamStatus
  resultId?: string
  error?: string
}

/** Opens the SSE trace for a run and reduces events into state. If the stream
 *  drops, falls back to polling GET /api/result (the backend safety net). */
export function useAgentStream(runId: string): StreamState {
  const [state, setState] = useState<StreamState>({ events: [], status: 'running' })
  const endedRef = useRef(false)

  useEffect(() => {
    endedRef.current = false
    setState({ events: [], status: 'running' })
    const es = new EventSource(streamUrl(runId))

    es.onmessage = (m) => {
      let ev: RunEvent
      try {
        ev = JSON.parse(m.data)
      } catch {
        return
      }
      if (ev.type === 'end') {
        endedRef.current = true
        es.close()
        setState((s) => ({
          ...s,
          status: (ev.status as StreamStatus) || 'done',
          resultId: ev.result_id || runId,
        }))
        return
      }
      if (ev.type === 'error') {
        endedRef.current = true
        setState((s) => ({ ...s, status: 'error', error: ev.message }))
        return
      }
      setState((s) => ({ ...s, events: [...s.events, ev] }))
    }

    es.onerror = () => {
      if (endedRef.current) return
      es.close()
      // SSE dropped before completion — poll the result instead.
      void pollResult()
    }

    async function pollResult() {
      for (let i = 0; i < 100 && !endedRef.current; i++) {
        try {
          const res = await getResult(runId)
          if (res) {
            endedRef.current = true
            setState((s) => ({ ...s, status: 'done', resultId: runId }))
            return
          }
        } catch (e) {
          endedRef.current = true
          setState((s) => ({ ...s, status: 'error', error: String(e) }))
          return
        }
        await new Promise((r) => setTimeout(r, 3000))
      }
    }

    return () => {
      endedRef.current = true
      es.close()
    }
  }, [runId])

  return state
}
