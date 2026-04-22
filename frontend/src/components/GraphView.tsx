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

type Direction = 'both' | 'upstream' | 'downstream'

const NODE_WIDTH = 220
const NODE_HEIGHT = 56

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

export function GraphView() {
  const [data, setData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [filterNamespace, setFilterNamespace] = useState('')
  const [filterDataset, setFilterDataset] = useState('')
  const [filterJob, setFilterJob] = useState('')
  const [direction, setDirection] = useState<Direction>('both')

  const [applied, setApplied] = useState<{
    namespace: string; dataset: string; job: string; direction: Direction
  } | null>(null)

  // IDs currently rendered in the canvas
  const [visibleIds, setVisibleIds] = useState<Set<string>>(new Set())
  // IDs of the original central nodes (from filters)
  const [centralIds, setCentralIds] = useState<Set<string>>(new Set())

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  useEffect(() => {
    fetch('/api/graph')
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then((d: GraphData) => { setData(d); setError(null) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
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

  const namespaceOptions = useMemo(() => {
    if (!data) return [{ value: '', label: 'Todos los namespaces' }]
    const ns = [...new Set(data.nodes.map(n => n.namespace).filter(Boolean))].sort()
    return [{ value: '', label: 'Todos los namespaces' }, ...ns.map(n => ({ value: n, label: n }))]
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

  // Nodes with hidden neighbors (show "+" indicator)
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

  // Recompute layout whenever visible set changes
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 10 }}>

      {/* Filter panel */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 8, padding: '14px 16px', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>

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
      </div>

      {/* Graph canvas */}
      <div style={{ flex: 1, borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border)', position: 'relative' }}>

        {/* Empty state overlay */}
        {!isActive && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 10, background: 'var(--bg)',
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12,
          }}>
            <span style={{ fontSize: 36, opacity: 0.3 }}>◈</span>
            <p style={{ color: 'var(--text-muted)', fontSize: 14, margin: 0 }}>
              {applied ? 'Sin resultados para los filtros aplicados' : 'Utiliza los filtros para visualizar'}
            </p>
            {!applied && (
              <p style={{ color: 'var(--text-muted)', fontSize: 12, margin: 0, opacity: 0.6 }}>
                {data.nodes.length} nodos disponibles · introduce un dataset y pulsa Visualizar
              </p>
            )}
          </div>
        )}

        {/* Info badge */}
        {isActive && (
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

        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          minZoom={0.05}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#1e293b" gap={20} />
          <Controls style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }} />
          {isActive && (
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
        </ReactFlow>
      </div>

      {/* Legend */}
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
    </div>
  )
}
