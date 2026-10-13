import { useEffect, useState } from 'react'
import { InputScreen } from './InputScreen'
import { RunScreen } from './RunScreen'
import { ResultScreen } from './ResultScreen'

type Route = { name: 'input' } | { name: 'run'; id: string } | { name: 'result'; id: string }

function parseHash(): Route {
  const h = window.location.hash.replace(/^#\/?/, '')
  const [a, b] = h.split('/')
  if (a === 'run' && b) return { name: 'run', id: b }
  if (a === 'r' && b) return { name: 'result', id: b }
  return { name: 'input' }
}

function nav(path: string) {
  window.location.hash = path
}

export default function App() {
  const [route, setRoute] = useState<Route>(parseHash())

  useEffect(() => {
    const on = () => setRoute(parseHash())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])

  if (route.name === 'run') {
    // navigate to the result by run id (the result is fetched via /api/result/{run_id})
    return <RunScreen key={route.id} runId={route.id} onDone={() => nav(`/r/${route.id}`)} onHome={() => nav('/')} />
  }
  if (route.name === 'result') {
    return <ResultScreen key={route.id} runId={route.id} onHome={() => nav('/')} />
  }
  return <InputScreen onStart={(runId) => nav(`/run/${runId}`)} />
}
