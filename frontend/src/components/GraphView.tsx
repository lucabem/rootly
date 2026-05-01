import { useEffect, useMemo, useState, useCallback } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Node,
  Edge,
  Position,
  MarkerType,
} from 'reactflow'
import dagre from '@dagrejs/dagre'
import 'reactflow/dist/style.css'

interface ApiNode {
  id: string
  kind: 'job' | 'dataset'
  name: string
  namespace: string
  has_code: boolean
  has_sql: boolean
  has_column_lineage: boolean
  format: string
}

interface ApiEdge {
  source: string
  target: string
  relation: string
}

interface GraphData {
  nodes: ApiNode[]
  edges: ApiEdge[]
}

interface TraceFieldNode {
  field: string
  dataset: string
  namespace?: string
  sources: (TraceFieldNode & { transform?: string; transform_subtype?: string })[]
  cycle?: boolean
}

type Direction = 'both' | 'upstream' | 'downstream'
type Mode = 'graph' | 'column'

const NODE_WIDTH = 220
const NODE_HEIGHT = 56
const COL_NODE_WIDTH = 220
const COL_NODE_HEIGHT = 72

// ── Dataset-level graph layout ────────────────────────────────────────────────

function layoutGraph(
  apiNodes: ApiNode[],
  apiEdges: ApiEdge[],
  centralIds: Set<string>,
  expandableIds: Set<string>,
): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 80 })

  for (const n of apiNodes) g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  for (const e of apiEdges) g.setEdge(e.source, e.target)
  dagre.layout(g)

  const nodes: Node[] = apiNodes.map(n => {
    const pos = g.node(n.id)
    const isCentral = centralIds.has(n.id)
    const isExpandable = expandableIds.has(n.id)
    return {
      id: n.id,
      type: 'default',
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      data: { label: <NodeLabel node={n} isCentral={isCentral} isExpandable={isExpandable} /> },
      style: nodeStyle(n, isCentral),
    }
  })

  const edges: Edge[] = apiEdges.map((e, i) => ({
    id: `e-${i}`,
    source: e.source,
    target: e.target,
    label: e.relation,
    animated: false,
    markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: '#6b7280' },
    style: { stroke: '#6b7280', strokeWidth: 1.5 },
    labelStyle: { fill: '#9ca3af', fontSize: 10 },
    labelBgStyle: { fill: 'transparent' },
  }))

  return { nodes, edges }
}

function nodeStyle(n: ApiNode, isCentral: boolean): React.CSSProperties {
  if (isCentral) {
    return {
      background: '#1c2a1c',
      border: '2px solid #22c55e',
      borderRadius: 8,
      boxShadow: '0 0 0 3px rgba(34,197,94,0.2)',
      padding: '6px 10px',
      fontSize: 12,
      color: '#e2e8f0',
      width: NODE_WIDTH,
      minHeight: NODE_HEIGHT,
      cursor: 'pointer',
    }
  }
  if (n.kind === 'job') {
    return {
      background: '#1e293b',
      border: '1.5px solid #3b82f6',
      borderRadius: 8,
      padding: '6px 10px',
      fontSize: 12,
      color: '#e2e8f0',
      width: NODE_WIDTH,
      minHeight: NODE_HEIGHT,
      cursor: 'pointer',
    }
  }
  return {
    background: '#0f172a',
    border: '1.5px solid #334155',
    borderRadius: 8,
    padding: '6px 10px',
    fontSize: 12,
    color: '#e2e8f0',
    width: NODE_WIDTH,
    minHeight: NODE_HEIGHT,
    cursor: 'pointer',
  }
}

function NodeLabel({ node, isCentral, isExpandable }: { node: ApiNode; isCentral: boolean; isExpandable: boolean }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <span style={{ fontSize: 13 }}>{node.kind === 'job' ? '⚙' : isCentral ? '◉' : '◈'}</span>
        <span style={{ fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 118 }}>
          {node.name}
        </span>
        {isExpandable && (
          <span style={{
            marginLeft: 'auto', fontSize: 11, color: '#f59e0b', fontWeight: 700,
            flexShrink: 0, lineHeight: 1,
          }}>+</span>
        )}
      </div>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {node.kind === 'dataset' && node.format && node.format !== 'unknown' && (
          <span style={badgeStyle('#1e3a5f')}>{node.format}</span>
        )}
        {node.has_column_lineage && <span style={badgeStyle('#4a1d1d')}>col</span>}
        {node.kind === 'dataset' && node.namespace && <span style={badgeStyle('#334155')}>{node.namespace}</span>}
      </div>
    </div>
  )
}

// ── Column-level trace layout ─────────────────────────────────────────────────

type ColNodeData = { dataset: string; namespace: string; field: string; isRoot: boolean }

function collectColField(
  root: TraceFieldNode,
  seenNodes: Map<string, ColNodeData>,
  rawEdges: Array<{ source: string; target: string; label: string }>,
  seenEdgeKeys: Set<string>,
) {
  function visit(node: TraceFieldNode & { transform?: string }, parentKey: string | null) {
    const key = `${node.dataset}::${node.field}`
    if (!seenNodes.has(key)) {
      seenNodes.set(key, { dataset: node.dataset, namespace: node.namespace ?? '', field: node.field, isRoot: parentKey === null })
    }
    if (parentKey !== null) {
      const edgeKey = `${key}→${parentKey}`
      if (!seenEdgeKeys.has(edgeKey)) {
        rawEdges.push({ source: key, target: parentKey, label: node.transform ?? '' })
        seenEdgeKeys.add(edgeKey)
      }
    }
    for (const src of node.sources ?? []) visit(src, key)
  }
  visit(root, null)
}

function layoutColGraph(
  seenNodes: Map<string, ColNodeData>,
  rawEdges: Array<{ source: string; target: string; label: string }>,
): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 100 })
  for (const [k] of seenNodes) g.setNode(k, { width: COL_NODE_WIDTH, height: COL_NODE_HEIGHT })
  for (const e of rawEdges) g.setEdge(e.source, e.target)
  dagre.layout(g)

  const nodes: Node[] = [...seenNodes.entries()].map(([k, n]) => {
    const pos = g.node(k)
    return {
      id: k,
      type: 'default',
      position: { x: pos.x - COL_NODE_WIDTH / 2, y: pos.y - COL_NODE_HEIGHT / 2 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      data: { label: <ColNodeLabel dataset={n.dataset} namespace={n.namespace} field={n.field} isRoot={n.isRoot} /> },
      style: colNodeStyle(n.isRoot),
    }
  })

  const edges: Edge[] = rawEdges.map((e, i) => ({
    id: `ce-${i}`,
    source: e.source,
    target: e.target,
    label: e.label || undefined,
    animated: true,
    markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: '#8b5cf6' },
    style: { stroke: '#8b5cf6', strokeWidth: 1.5 },
    labelStyle: { fill: '#a78bfa', fontSize: 10 },
    labelBgStyle: { fill: 'rgba(15,23,42,0.85)', borderRadius: 3 },
  }))

  return { nodes, edges }
}

function ColNodeLabel({ dataset, namespace, field, isRoot }: { dataset: string; namespace: string; field: string; isRoot: boolean }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <span style={{ fontSize: 12, color: isRoot ? '#a78bfa' : '#7c3aed' }}>{isRoot ? '◉' : '◈'}</span>
        <span style={{ fontWeight: 600, fontSize: 12, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 160 }}>
          {field}
        </span>
      </div>
      <span style={{ fontSize: 11, color: '#94a3b8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {dataset}
      </span>
      {namespace && (
        <span style={{ fontSize: 10, color: '#475569', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {namespace}
        </span>
      )}
    </div>
  )
}

function colNodeStyle(isRoot: boolean): React.CSSProperties {
  if (isRoot) {
    return {
      background: '#1c1030',
      border: '2px solid #8b5cf6',
      borderRadius: 8,
      boxShadow: '0 0 0 3px rgba(139,92,246,0.2)',
      padding: '6px 10px',
      fontSize: 12,
      color: '#e2e8f0',
      width: COL_NODE_WIDTH,
      minHeight: COL_NODE_HEIGHT,
      cursor: 'default',
    }
  }
  return {
    background: '#0f0a1e',
    border: '1.5px solid #4c1d95',
    borderRadius: 8,
    padding: '6px 10px',
    fontSize: 12,
    color: '#e2e8f0',
    width: COL_NODE_WIDTH,
    minHeight: COL_NODE_HEIGHT,
    cursor: 'default',
  }
}

// ── Shared UI helpers ─────────────────────────────────────────────────────────

function badgeStyle(bg: string): React.CSSProperties {
  return {
    background: bg, borderRadius: 4, padding: '1px 5px',
    fontSize: 10, color: '#cbd5e1', letterSpacing: '0.02em',
  }
}

const inputStyle: React.CSSProperties = {
  background: 'var(--bg-card)', border: '1px solid var(--border)',
  borderRadius: 6, padding: '8px 12px', color: 'var(--text)',
  fontSize: 13, width: '100%', boxSizing: 'border-box',
}

const selectStyle: React.CSSProperties = {
  background: 'var(--bg-card)', border: '1px solid var(--border)',
  borderRadius: 6, padding: '8px 28px 8px 12px', color: 'var(--text)',
  fontSize: 13, cursor: 'pointer', appearance: 'none', WebkitAppearance: 'none',
  width: '100%', boxSizing: 'border-box',
}

function Select({ value, onChange, options }: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <div style={{ position: 'relative' }}>
      <select value={value} onChange={e => onChange(e.target.value)} style={selectStyle}>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <span style={{
        position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
        pointerEvents: 'none', color: 'var(--text-muted)', fontSize: 10,
      }}>▾</span>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function GraphView() {
  const [data, setData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Mode
  const [mode, setMode] = useState<Mode>('graph')

  // Graph-mode state
  const [filterNamespace, setFilterNamespace] = useState('')
  const [filterDataset, setFilterDataset] = useState('')
  const [filterJob, setFilterJob] = useState('')
  const [direction, setDirection] = useState<Direction>('both')

  const [applied, setApplied] = useState<{
    namespace: string; dataset: string; job: string; direction: Direction
  } | null>(null)

  const [visibleIds, setVisibleIds] = useState<Set<string>>(new Set())
  const [centralIds, setCentralIds] = useState<Set<string>>(new Set())

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  // Shared namespace + table lists (populated from API)
  const [namespaceList, setNamespaceList] = useState<string[]>([])
  const [tableList, setTableList] = useState<string[]>([])
  const [tableLoading, setTableLoading] = useState(false)

  // Column-mode state
  const [colNamespace, setColNamespace] = useState('')
  const [colTable, setColTable] = useState('')
  const [colColumn, setColColumn] = useState('')
  const [columnList, setColumnList] = useState<{ name: string; type: string }[]>([])
  const [columnLoading, setColumnLoading] = useState(false)
  const [colLoading, setColLoading] = useState(false)
  const [colError, setColError] = useState<string | null>(null)
  const [colActive, setColActive] = useState(false)
  const [colNodes, setColNodes, onColNodesChange] = useNodesState([])
  const [colEdges, setColEdges, onColEdgesChange] = useEdgesState([])
  const [colInfo, setColInfo] = useState<{ fields: number; datasets: number } | null>(null)

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

  const datasetSuggestions = useMemo(() => {
    if (!data) return []
    return data.nodes
      .filter(n => n.kind === 'dataset' && (!filterNamespace || n.namespace === filterNamespace))
      .map(n => n.name).sort()
  }, [data, filterNamespace])

  const jobSuggestions = useMemo(() => {
    if (!data) return []
    return data.nodes
      .filter(n => n.kind === 'job' && (!filterNamespace || n.namespace === filterNamespace))
      .map(n => n.name).sort()
  }, [data, filterNamespace])

  // Fetch tables and reset downstream when column-mode namespace changes
  useEffect(() => {
    setColTable('')
    setColColumn('')
    setColumnList([])
    setTableList([])
    if (!colNamespace) return
    setTableLoading(true)
    fetch(`/api/tables?namespace=${encodeURIComponent(colNamespace)}`)
      .then(r => r.json())
      .then(d => setTableList(d.tables ?? []))
      .catch(() => setTableList([]))
      .finally(() => setTableLoading(false))
  }, [colNamespace])

  // Fetch columns when table is selected
  useEffect(() => {
    if (!colTable) { setColumnList([]); setColColumn(''); return }
    setColumnLoading(true)
    const params = new URLSearchParams({ dataset: colTable })
    if (colNamespace) params.set('namespace', colNamespace)
    fetch(`/api/schema?${params}`)
      .then(r => r.json())
      .then(d => { setColumnList(d.columns ?? []); setColColumn('') })
      .catch(() => setColumnList([]))
      .finally(() => setColumnLoading(false))
  }, [colTable])

  const expandableIds = useMemo(() => {
    if (!data || visibleIds.size === 0) return new Set<string>()
    const expandable = new Set<string>()
    for (const id of visibleIds) {
      const dir = applied?.direction ?? 'both'
      const hasHiddenSucc = (dir === 'downstream' || dir === 'both')
        && (successors.get(id) ?? []).some(s => {
          const node = data.nodes.find(n => n.id === s)
          return !visibleIds.has(s) && (!applied?.namespace || node?.namespace === applied.namespace)
        })
      const hasHiddenPred = (dir === 'upstream' || dir === 'both')
        && (predecessors.get(id) ?? []).some(s => {
          const node = data.nodes.find(n => n.id === s)
          return !visibleIds.has(s) && (!applied?.namespace || node?.namespace === applied.namespace)
        })
      if (hasHiddenSucc || hasHiddenPred) expandable.add(id)
    }
    return expandable
  }, [data, visibleIds, successors, predecessors, applied])

  useEffect(() => {
    if (!data || visibleIds.size === 0) return
    const visNodes = data.nodes.filter(n => visibleIds.has(n.id))
    const visIds = new Set(visNodes.map(n => n.id))
    const visEdges = data.edges.filter(e => visIds.has(e.source) && visIds.has(e.target))
    const { nodes: ln, edges: le } = layoutGraph(visNodes, visEdges, centralIds, expandableIds)
    setNodes(ln)
    setEdges(le)
  }, [data, visibleIds, centralIds, expandableIds])

  const handleApply = useCallback(() => {
    if (!data || (!filterDataset.trim() && !filterJob.trim())) return

    const cfg = { namespace: filterNamespace, dataset: filterDataset, job: filterJob, direction }
    setApplied(cfg)

    const matches = data.nodes.filter(n =>
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
    const ns = applied.namespace

    setVisibleIds(prev => {
      const next = new Set(prev)
      if (dir === 'downstream' || dir === 'both') {
        for (const id of successors.get(node.id) ?? []) {
          const n = data.nodes.find(x => x.id === id)
          if (n && (!ns || n.namespace === ns)) next.add(id)
        }
      }
      if (dir === 'upstream' || dir === 'both') {
        for (const id of predecessors.get(node.id) ?? []) {
          const n = data.nodes.find(x => x.id === id)
          if (n && (!ns || n.namespace === ns)) next.add(id)
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

  const handleColTrace = useCallback(() => {
    if (!colTable) return
    setColLoading(true)
    setColError(null)
    setColActive(false)
    setColInfo(null)

    const params = new URLSearchParams({ dataset: colTable })
    if (colColumn) params.set('field', colColumn)
    if (colNamespace) params.set('namespace', colNamespace)

    fetch(`/api/trace?${params}`)
      .then(r => r.json().then(body => ({ ok: r.ok, body })))
      .then(({ ok, body }) => {
        if (!ok) throw new Error(body.detail ?? `HTTP error`)
        const results: Array<{ dataset: string; namespace: string; fields: TraceFieldNode[]; message?: string }> = body.results ?? []
        if (!results.length) throw new Error('Sin resultados.')

        const seenNodes = new Map<string, ColNodeData>()
        const rawEdges: Array<{ source: string; target: string; label: string }> = []
        const seenEdgeKeys = new Set<string>()
        let totalFields = 0

        for (const result of results) {
          if (!result.fields?.length) continue
          for (const fieldRoot of result.fields) {
            totalFields++
            collectColField(fieldRoot, seenNodes, rawEdges, seenEdgeKeys)
          }
        }

        if (!seenNodes.size) {
          const msg = results[0]?.message ?? 'No hay linaje de columna disponible para este dataset.'
          throw new Error(msg)
        }

        const { nodes: allNodes, edges: allEdges } = layoutColGraph(seenNodes, rawEdges)
        setColNodes(allNodes)
        setColEdges(allEdges)
        setColInfo({ fields: totalFields, datasets: new Set([...seenNodes.keys()].map(k => k.split('::')[0])).size })
        setColActive(true)
      })
      .catch((e: Error) => setColError(e.message))
      .finally(() => setColLoading(false))
  }, [colTable, colColumn])

  const handleColClear = useCallback(() => {
    setColActive(false)
    setColError(null)
    setColInfo(null)
    setColNodes([])
    setColEdges([])
    setColNamespace('')
    setColTable('')
    setColColumn('')
    setColumnList([])
  }, [])

  if (loading) return <div className="empty-state"><p>Cargando grafo…</p></div>
  if (error) return <div className="empty-state"><p style={{ color: '#f87171' }}>Error: {error}</p></div>
  if (!data || data.nodes.length === 0) return (
    <div className="empty-state">
      <h3>Sin datos en el grafo</h3>
      <p>Ejecuta Sync para cargar eventos de linaje.</p>
    </div>
  )

  const canApply = filterDataset.trim() || filterJob.trim()
  const isActive = applied && visibleIds.size > 0

  const activeNodes = mode === 'column' ? colNodes : nodes
  const activeEdges = mode === 'column' ? colEdges : edges
  const onActiveNodesChange = mode === 'column' ? onColNodesChange : onNodesChange
  const onActiveEdgesChange = mode === 'column' ? onColEdgesChange : onEdgesChange

  const showEmpty = mode === 'graph'
    ? !isActive
    : !colActive && !colLoading

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 10 }}>

      {/* Filter panel */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 8, padding: '14px 16px', flexShrink: 0,
      }}>

        {/* Mode toggle */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 12 }}>
          {(['graph', 'column'] as Mode[]).map(m => (
            <button
              key={m}
              onClick={() => setMode(m)}
              style={{
                background: mode === m ? (m === 'column' ? '#4c1d95' : '#14532d') : 'transparent',
                border: `1px solid ${mode === m ? (m === 'column' ? '#8b5cf6' : '#22c55e') : 'var(--border)'}`,
                borderRadius: 6, padding: '5px 14px',
                color: mode === m ? (m === 'column' ? '#c4b5fd' : '#86efac') : 'var(--text-muted)',
                fontSize: 12, fontWeight: mode === m ? 600 : 400, cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              {m === 'graph' ? 'Grafo de datasets' : 'Linaje de columna'}
            </button>
          ))}
        </div>

        {/* Graph mode controls */}
        {mode === 'graph' && (
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>

            <div style={{ flex: '1 1 160px' }}>
              <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Namespace</label>
              <Select
                value={filterNamespace}
                onChange={v => { setFilterNamespace(v); setFilterDataset(''); setFilterJob('') }}
                options={[
                  { value: '', label: 'Todos…' },
                  ...namespaceList.map(n => ({ value: n, label: n })),
                ]}
              />
            </div>

            <div style={{ flex: '2 1 200px' }}>
              <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
                Dataset <span style={{ color: '#22c55e' }}>◉</span> (elemento central)
              </label>
              <input
                list="dataset-suggestions"
                value={filterDataset}
                onChange={e => setFilterDataset(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleApply()}
                placeholder="Nombre del dataset…"
                style={inputStyle}
              />
              <datalist id="dataset-suggestions">
                {datasetSuggestions.map(name => <option key={name} value={name} />)}
              </datalist>
            </div>

            <div style={{ flex: '2 1 180px' }}>
              <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
                Job <span style={{ color: '#64748b' }}>(opcional)</span>
              </label>
              <input
                list="job-suggestions"
                value={filterJob}
                onChange={e => setFilterJob(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleApply()}
                placeholder="Nombre del job…"
                style={inputStyle}
              />
              <datalist id="job-suggestions">
                {jobSuggestions.map(name => <option key={name} value={name} />)}
              </datalist>
            </div>

            <div style={{ flex: '1 1 140px' }}>
              <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Dirección</label>
              <Select
                value={direction}
                onChange={v => setDirection(v as Direction)}
                options={[
                  { value: 'both', label: '↕ Ambas' },
                  { value: 'upstream', label: '↑ Upstream' },
                  { value: 'downstream', label: '↓ Downstream' },
                ]}
              />
            </div>

            <div style={{ display: 'flex', gap: 6, alignSelf: 'flex-end' }}>
              <button
                onClick={handleApply}
                disabled={!canApply}
                style={{
                  background: canApply ? '#22c55e' : '#1a3a1a',
                  border: 'none', borderRadius: 6, padding: '8px 18px',
                  color: canApply ? '#0f172a' : '#374151',
                  fontSize: 13, fontWeight: 600,
                  cursor: canApply ? 'pointer' : 'not-allowed',
                  transition: 'background 0.15s',
                }}
              >
                Visualizar
              </button>
              {applied && (
                <button
                  onClick={handleClear}
                  style={{
                    background: 'transparent', border: '1px solid var(--border)',
                    borderRadius: 6, padding: '8px 12px',
                    color: 'var(--text-muted)', fontSize: 12, cursor: 'pointer',
                  }}
                >
                  ✕ Limpiar
                </button>
              )}
            </div>
          </div>
        )}

        {/* Column mode controls */}
        {mode === 'column' && (
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>

            <div style={{ flex: '1 1 160px' }}>
              <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Namespace</label>
              <Select
                value={colNamespace}
                onChange={setColNamespace}
                options={[
                  { value: '', label: 'Todos…' },
                  ...namespaceList.map(n => ({ value: n, label: n })),
                ]}
              />
            </div>

            <div style={{ flex: '2 1 200px' }}>
              <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
                Tabla <span style={{ color: '#8b5cf6' }}>◉</span>
              </label>
              <Select
                value={colTable}
                onChange={setColTable}
                options={[
                  { value: '', label: tableLoading ? 'Cargando tablas…' : colNamespace ? 'Selecciona tabla…' : 'Selecciona namespace primero…' },
                  ...tableList.map(t => ({ value: t, label: t })),
                ]}
              />
            </div>

            <div style={{ flex: '2 1 180px' }}>
              <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
                Columna{' '}
                {columnLoading
                  ? <span style={{ color: '#64748b' }}>cargando…</span>
                  : <span style={{ color: '#64748b' }}>(opcional — vacío traza todas)</span>
                }
              </label>
              <Select
                value={colColumn}
                onChange={setColColumn}
                options={[
                  { value: '', label: colTable ? (columnLoading ? 'Cargando columnas…' : columnList.length ? 'Todas las columnas' : 'Sin columnas con linaje') : 'Selecciona tabla primero…' },
                  ...columnList.map(c => ({ value: c.name, label: c.type ? `${c.name} (${c.type})` : c.name })),
                ]}
              />
            </div>

            <div style={{ display: 'flex', gap: 6, alignSelf: 'flex-end' }}>
              <button
                onClick={handleColTrace}
                disabled={!colTable || colLoading}
                style={{
                  background: colTable && !colLoading ? '#8b5cf6' : '#2d1a4a',
                  border: 'none', borderRadius: 6, padding: '8px 18px',
                  color: colTable && !colLoading ? '#faf5ff' : '#374151',
                  fontSize: 13, fontWeight: 600,
                  cursor: colTable && !colLoading ? 'pointer' : 'not-allowed',
                  transition: 'background 0.15s',
                }}
              >
                {colLoading ? 'Trazando…' : 'Trazar'}
              </button>
              {colActive && (
                <button
                  onClick={handleColClear}
                  style={{
                    background: 'transparent', border: '1px solid var(--border)',
                    borderRadius: 6, padding: '8px 12px',
                    color: 'var(--text-muted)', fontSize: 12, cursor: 'pointer',
                  }}
                >
                  ✕ Limpiar
                </button>
              )}
            </div>

            {colError && (
              <div style={{ width: '100%', marginTop: 4, fontSize: 12, color: '#f87171' }}>
                {colError}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Graph canvas */}
      <div style={{ flex: 1, borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border)', position: 'relative' }}>

        {/* Empty state overlay */}
        {showEmpty && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 10, background: 'var(--bg)',
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12,
          }}>
            <span style={{ fontSize: 36, opacity: 0.3 }}>{mode === 'column' ? '◈' : '◈'}</span>
            {mode === 'graph' ? (
              <>
                <p style={{ color: 'var(--text-muted)', fontSize: 14, margin: 0 }}>
                  {applied ? 'Sin resultados para los filtros aplicados' : 'Utiliza los filtros para visualizar'}
                </p>
                {!applied && (
                  <p style={{ color: 'var(--text-muted)', fontSize: 12, margin: 0, opacity: 0.6 }}>
                    {data.nodes.length} nodos disponibles · introduce un dataset y pulsa Visualizar
                  </p>
                )}
              </>
            ) : (
              <>
                <p style={{ color: 'var(--text-muted)', fontSize: 14, margin: 0 }}>
                  {colLoading ? 'Trazando linaje de columna…' : 'Introduce un dataset y columna y pulsa Trazar'}
                </p>
                <p style={{ color: 'var(--text-muted)', fontSize: 12, margin: 0, opacity: 0.6 }}>
                  La columna vacía traza todas las columnas del dataset con linaje registrado
                </p>
              </>
            )}
          </div>
        )}

        {/* Info badge — graph mode */}
        {mode === 'graph' && isActive && (
          <div style={{
            position: 'absolute', top: 8, left: 8, zIndex: 10,
            background: 'rgba(15,23,42,0.9)', border: '1px solid var(--border)',
            borderRadius: 6, padding: '5px 10px', fontSize: 11, color: 'var(--text-muted)',
            pointerEvents: 'none', display: 'flex', gap: 8, alignItems: 'center',
          }}>
            <span>{visibleIds.size} nodos</span>
            <span style={{ color: '#22c55e' }}>
              {applied.direction === 'both' ? '↕' : applied.direction === 'upstream' ? '↑' : '↓'}
            </span>
            {expandableIds.size > 0 && (
              <span style={{ color: '#f59e0b' }}>
                {expandableIds.size} expandible{expandableIds.size > 1 ? 's' : ''} <span style={{ fontWeight: 700 }}>+</span>
              </span>
            )}
          </div>
        )}

        {/* Info badge — column mode */}
        {mode === 'column' && colActive && colInfo && (
          <div style={{
            position: 'absolute', top: 8, left: 8, zIndex: 10,
            background: 'rgba(15,10,30,0.9)', border: '1px solid #4c1d95',
            borderRadius: 6, padding: '5px 10px', fontSize: 11, color: '#c4b5fd',
            pointerEvents: 'none', display: 'flex', gap: 8, alignItems: 'center',
          }}>
            <span style={{ color: '#8b5cf6' }}>◈</span>
            <span>{colInfo.fields} campo{colInfo.fields !== 1 ? 's' : ''}</span>
            <span style={{ color: '#4c1d95' }}>·</span>
            <span>{colInfo.datasets} dataset{colInfo.datasets !== 1 ? 's' : ''} en el camino</span>
          </div>
        )}

        <ReactFlow
          nodes={activeNodes}
          edges={activeEdges}
          onNodesChange={onActiveNodesChange}
          onEdgesChange={onActiveEdgesChange}
          onNodeClick={mode === 'graph' ? handleNodeClick : undefined}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          minZoom={0.05}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#1e293b" gap={20} />
          <Controls style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }} />
          {mode === 'graph' && isActive && (
            <MiniMap
              nodeColor={n =>
                centralIds.has(n.id) ? '#22c55e'
                : (n.style?.border as string)?.includes('3b82f6') ? '#3b82f6'
                : '#334155'
              }
              style={{ background: '#0f172a', border: '1px solid var(--border)' }}
              maskColor="rgba(0,0,0,0.4)"
            />
          )}
          {mode === 'column' && colActive && (
            <MiniMap
              nodeColor={n =>
                (n.style?.border as string)?.includes('8b5cf6') ? '#8b5cf6' : '#4c1d95'
              }
              style={{ background: '#0f0a1e', border: '1px solid #4c1d95' }}
              maskColor="rgba(0,0,0,0.4)"
            />
          )}
        </ReactFlow>
      </div>

      {/* Legend */}
      {mode === 'graph' ? (
        <div style={{
          display: 'flex', gap: 12, padding: '0 4px', flexShrink: 0,
          fontSize: 11, color: 'var(--text-muted)', flexWrap: 'wrap',
        }}>
          <span><span style={{ color: '#22c55e' }}>◉</span> Dataset central</span>
          <span><span style={{ color: '#3b82f6' }}>■</span> Job ETL</span>
          <span><span style={{ color: '#334155' }}>■</span> Dataset</span>
          <span><span style={{ color: '#f59e0b', fontWeight: 700 }}>+</span> tiene vecinos ocultos</span>
          <span><span style={{ background: '#14532d', padding: '0 3px', borderRadius: 2 }}>py</span> código Glue</span>
          <span><span style={{ background: '#3b1f5e', padding: '0 3px', borderRadius: 2 }}>sql</span> SQL</span>
          <span><span style={{ background: '#4a1d1d', padding: '0 3px', borderRadius: 2 }}>col</span> linaje columnas</span>
          <span style={{ marginLeft: 'auto', opacity: 0.5 }}>Clic en nodo para expandir vecinos directos</span>
        </div>
      ) : (
        <div style={{
          display: 'flex', gap: 12, padding: '0 4px', flexShrink: 0,
          fontSize: 11, color: 'var(--text-muted)', flexWrap: 'wrap',
        }}>
          <span><span style={{ color: '#8b5cf6' }}>◉</span> Campo trazado (destino)</span>
          <span><span style={{ color: '#4c1d95' }}>◈</span> Campo fuente</span>
          <span><span style={{ color: '#8b5cf6' }}>──▶</span> flujo de dato + tipo transformación</span>
          <span style={{ marginLeft: 'auto', opacity: 0.5 }}>Izquierda = origen · Derecha = destino</span>
        </div>
      )}
    </div>
  )
}
