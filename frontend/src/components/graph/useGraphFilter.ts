import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNodesState, useEdgesState, Node } from 'reactflow'
import { ApiNode, ContextMenuState, Direction, GraphData } from './types'
import { layoutGraph } from './layout'

interface AppliedFilter {
  namespace: string
  dataset: string
  job: string
  direction: Direction
}

export function useGraphFilter(
  data: GraphData | null,
  successors: Map<string, string[]>,
  predecessors: Map<string, string[]>,
) {
  const [filterNamespace, setFilterNamespace] = useState('')
  const [filterDataset, setFilterDataset] = useState('')
  const [filterJob, setFilterJob] = useState('')
  const [direction, setDirection] = useState<Direction>('both')
  const [applied, setApplied] = useState<AppliedFilter | null>(null)
  const [visibleIds, setVisibleIds] = useState<Set<string>>(new Set())
  const [centralIds, setCentralIds] = useState<Set<string>>(new Set())
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null)
  const [tableList, setTableList] = useState<string[]>([])
  const [tableLoading, setTableLoading] = useState(false)

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  useEffect(() => {
    setTableList([])
    if (!filterNamespace) return
    setTableLoading(true)
    fetch(`/api/tables?namespace=${encodeURIComponent(filterNamespace)}`)
      .then(r => r.json())
      .then(d => setTableList(d.tables ?? []))
      .catch(() => setTableList([]))
      .finally(() => setTableLoading(false))
  }, [filterNamespace])

  const jobSuggestions = useMemo(() => {
    if (!data) return []
    return data.nodes
      .filter(n => n.kind === 'job' && (!filterNamespace || n.namespace === filterNamespace))
      .map(n => n.name).sort()
  }, [data, filterNamespace])

  const expandableIds = useMemo(() => {
    if (!data || visibleIds.size === 0) return new Set<string>()
    const expandable = new Set<string>()
    for (const id of visibleIds) {
      const dir = applied?.direction ?? 'both'
      const hasHiddenSucc = (dir === 'downstream' || dir === 'both')
        && (successors.get(id) ?? []).some(s => !visibleIds.has(s))
      const hasHiddenPred = (dir === 'upstream' || dir === 'both')
        && (predecessors.get(id) ?? []).some(s => !visibleIds.has(s))
      if (hasHiddenSucc || hasHiddenPred) expandable.add(id)
    }
    return expandable
  }, [data, visibleIds, successors, predecessors, applied])

  const handleDotsClick = useCallback((e: React.MouseEvent, apiNode: ApiNode) => {
    const menuW = 240, menuH = 90
    setContextMenu({
      x: Math.min(e.clientX, window.innerWidth - menuW - 8),
      y: Math.min(e.clientY, window.innerHeight - menuH - 8),
      node: apiNode,
    })
  }, [])

  useEffect(() => {
    if (!data || visibleIds.size === 0) return
    const visNodes = data.nodes.filter(n => visibleIds.has(n.id))
    const visIds = new Set(visNodes.map(n => n.id))
    const visEdges = data.edges.filter(e => visIds.has(e.source) && visIds.has(e.target))
    const { nodes: ln, edges: le } = layoutGraph(visNodes, visEdges, centralIds, expandableIds, handleDotsClick)
    setNodes(ln)
    setEdges(le)
  }, [data, visibleIds, centralIds, expandableIds])

  const handleApply = useCallback(() => {
    if (!data || (!filterDataset.trim() && !filterJob.trim() && !filterNamespace)) return

    const cfg = { namespace: filterNamespace, dataset: filterDataset, job: filterJob, direction }
    setApplied(cfg)

    const namespaceOnly = !filterDataset.trim() && !filterJob.trim() && filterNamespace
    const matches = namespaceOnly
      ? data.nodes.filter(n => n.kind === 'dataset' && n.namespace === filterNamespace)
      : data.nodes.filter(n =>
          (
            (n.kind === 'dataset' && filterDataset.trim() && n.name.toLowerCase() === filterDataset.toLowerCase()) ||
            (n.kind === 'job' && filterJob.trim() && n.name.toLowerCase() === filterJob.toLowerCase())
          ) && (!filterNamespace || n.namespace === filterNamespace)
        )

    const ids = new Set(matches.map(n => n.id))
    setCentralIds(new Set(ids))
    setVisibleIds(new Set(ids))
  }, [data, filterNamespace, filterDataset, filterJob, direction])

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    if (!data || !applied) return
    const dir = applied.direction
    setVisibleIds(prev => {
      const next = new Set(prev)
      if (dir === 'downstream' || dir === 'both') {
        for (const id of successors.get(node.id) ?? []) {
          if (data.nodes.find(x => x.id === id)) next.add(id)
        }
      }
      if (dir === 'upstream' || dir === 'both') {
        for (const id of predecessors.get(node.id) ?? []) {
          if (data.nodes.find(x => x.id === id)) next.add(id)
        }
      }
      return next
    })
  }, [data, applied, successors, predecessors])

  const handleClear = useCallback(() => {
    setApplied(null)
    setVisibleIds(new Set())
    setCentralIds(new Set())
    setFilterDataset('')
    setFilterJob('')
    setNodes([])
    setEdges([])
  }, [])

  const canApply = !!(filterDataset.trim() || filterJob.trim() || filterNamespace)
  const isActive = applied !== null && visibleIds.size > 0

  return {
    filterNamespace, setFilterNamespace,
    filterDataset, setFilterDataset,
    filterJob, setFilterJob,
    direction, setDirection,
    applied, visibleIds, expandableIds,
    nodes, edges, onNodesChange, onEdgesChange,
    contextMenu, setContextMenu,
    tableList, tableLoading, jobSuggestions,
    canApply, isActive,
    handleApply, handleNodeClick, handleDotsClick, handleClear,
  }
}
