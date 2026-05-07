import { useEffect, useMemo, useState } from 'react'
import { GraphData } from './types'

export function useGraphData() {
  const [data, setData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [namespaceList, setNamespaceList] = useState<string[]>([])

  useEffect(() => {
    fetch('/api/graph')
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then((d: GraphData) => { setData(d); setError(null) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetch('/api/namespaces')
      .then(r => r.json())
      .then(d => setNamespaceList(d.namespaces ?? []))
      .catch(() => setNamespaceList([]))
  }, [])

  const { successors, predecessors } = useMemo(() => {
    if (!data) return { successors: new Map<string, string[]>(), predecessors: new Map<string, string[]>() }
    const succ = new Map<string, string[]>()
    const pred = new Map<string, string[]>()
    for (const e of data.edges) {
      if (!succ.has(e.source)) succ.set(e.source, [])
      succ.get(e.source)!.push(e.target)
      if (!pred.has(e.target)) pred.set(e.target, [])
      pred.get(e.target)!.push(e.source)
    }
    return { successors: succ, predecessors: pred }
  }, [data])

  return { data, loading, error, namespaceList, successors, predecessors }
}
