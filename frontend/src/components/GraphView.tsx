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

const NODE_WIDTH = 180
const NODE_HEIGHT = 56

function layoutGraph(apiNodes: ApiNode[], apiEdges: ApiEdge[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 80 })

  for (const n of apiNodes) {
    g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  }
  for (const e of apiEdges) {
    g.setEdge(e.source, e.target)
  }

  dagre.layout(g)

  const nodes: Node[] = apiNodes.map(n => {
    const pos = g.node(n.id)
    return {
      id: n.id,
      type: 'default',
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      data: { label: <NodeLabel node={n} /> },
      style: nodeStyle(n),
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

function nodeStyle(n: ApiNode): React.CSSProperties {
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
  }
}

function NodeLabel({ node }: { node: ApiNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <span style={{ fontSize: 13 }}>{node.kind === 'job' ? '⚙' : '◈'}</span>
        <span style={{ fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 130 }}>
          {node.name}
        </span>
      </div>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {node.kind === 'dataset' && node.format && node.format !== 'unknown' && (
          <span style={badgeStyle('#1e3a5f')}>{node.format}</span>
        )}
        {node.has_code && <span style={badgeStyle('#14532d')}>py</span>}
        {node.has_sql && <span style={badgeStyle('#3b1f5e')}>sql</span>}
        {node.has_column_lineage && <span style={badgeStyle('#4a1d1d')}>col</span>}
      </div>
    </div>
  )
}

function badgeStyle(bg: string): React.CSSProperties {
  return {
    background: bg,
    borderRadius: 4,
    padding: '1px 5px',
    fontSize: 10,
    color: '#cbd5e1',
    letterSpacing: '0.02em',
  }
}

const selectStyle: React.CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  padding: '6px 8px',
  color: 'var(--text)',
  fontSize: 12,
  cursor: 'pointer',
  appearance: 'none',
  WebkitAppearance: 'none',
  paddingRight: 24,
}

function Select({
  value,
  onChange,
  options,
  style,
}: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
  style?: React.CSSProperties
}) {
  return (
    <div style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{ ...selectStyle, ...style }}
      >
        {options.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <span style={{
        position: 'absolute', right: 6, pointerEvents: 'none',
        color: 'var(--text-muted)', fontSize: 10,
      }}>▾</span>
    </div>
  )
}

function bfs(start: Set<string>, adj: Map<string, string[]>): Set<string> {
  const visited = new Set<string>(start)
  const queue = [...start]
  while (queue.length > 0) {
    const node = queue.shift()!
    for (const neighbor of adj.get(node) ?? []) {
      if (!visited.has(neighbor)) {
        visited.add(neighbor)
        queue.push(neighbor)
      }
    }
  }
  return visited
}

export function GraphView() {
  const [data, setData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [filterKind, setFilterKind] = useState('all')
  const [filterNamespace, setFilterNamespace] = useState('')
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  useEffect(() => {
    setLoading(true)
    fetch('/api/graph')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((d: GraphData) => { setData(d); setError(null) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  // Adjacency maps over full dataset
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

  // Unique namespaces for dropdown
  const namespaceOptions = useMemo(() => {
    if (!data) return [{ value: '', label: 'Todos los namespaces' }]
    const ns = [...new Set(data.nodes.map(n => n.namespace).filter(Boolean))].sort()
    return [{ value: '', label: 'Todos los namespaces' }, ...ns.map(n => ({ value: n, label: n }))]
  }, [data])

  // Lineage of the selected node:
  // - dataset: all ancestors up to roots, stopping at the node
  // - job: same, plus its direct output datasets (one level downstream)
  const selectedFlow = useMemo((): Set<string> | null => {
    if (!selectedNodeId || !data) return null
    const upstream = bfs(new Set([selectedNodeId]), predecessors)
    const selectedNode = data.nodes.find(n => n.id === selectedNodeId)
    if (selectedNode?.kind === 'job') {
      const directOutputs = successors.get(selectedNodeId) ?? []
      return new Set([...upstream, ...directOutputs])
    }
    return upstream
  }, [selectedNodeId, data, predecessors, successors])

  const filtered = useMemo(() => {
    if (!data) return null

    // Flow mode: show only nodes in the selected lineage chain
    if (selectedFlow) {
      return {
        nodes: data.nodes.filter(n => selectedFlow.has(n.id)),
        edges: data.edges.filter(e => selectedFlow.has(e.source) && selectedFlow.has(e.target)),
      }
    }

    // Filter mode: apply kind + namespace + text search
    let visibleNodes = data.nodes
    if (filterKind !== 'all') visibleNodes = visibleNodes.filter(n => n.kind === filterKind)
    if (filterNamespace) visibleNodes = visibleNodes.filter(n => n.namespace === filterNamespace)

    if (search.trim()) {
      const q = search.toLowerCase()
      const directMatches = new Set(
        visibleNodes
          .filter(n => n.name.toLowerCase().includes(q) || n.namespace.toLowerCase().includes(q))
          .map(n => n.id)
      )
      if (directMatches.size === 0) return { nodes: [], edges: [] }
      const reachable = bfs(directMatches, successors)
      bfs(directMatches, predecessors).forEach(id => reachable.add(id))
      visibleNodes = visibleNodes.filter(n => reachable.has(n.id))
    }

    const nodeIds = new Set(visibleNodes.map(n => n.id))
    return {
      nodes: visibleNodes,
      edges: data.edges.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target)),
    }
  }, [data, search, filterKind, filterNamespace, selectedFlow, successors, predecessors])

  useEffect(() => {
    if (!filtered) return
    const { nodes: ln, edges: le } = layoutGraph(filtered.nodes, filtered.edges)

    // Highlight selected node with amber border + glow
    const styledNodes = selectedNodeId
      ? ln.map(n =>
          n.id === selectedNodeId
            ? {
                ...n,
                style: {
                  ...n.style,
                  border: '2px solid #f59e0b',
                  boxShadow: '0 0 0 3px rgba(245,158,11,0.2)',
                },
              }
            : n
        )
      : ln

    // Highlight edges that touch the selected node
    const styledEdges = selectedNodeId
      ? le.map(e =>
          e.source === selectedNodeId || e.target === selectedNodeId
            ? {
                ...e,
                style: { stroke: '#f59e0b', strokeWidth: 2 },
                markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: '#f59e0b' },
              }
            : e
        )
      : le

    setNodes(styledNodes)
    setEdges(styledEdges)
  }, [filtered, selectedNodeId])

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNodeId(prev => (prev === node.id ? null : node.id))
  }, [])

  const handlePaneClick = useCallback(() => {
    setSelectedNodeId(null)
  }, [])

  const clearAll = () => {
    setSearch('')
    setFilterKind('all')
    setFilterNamespace('')
    setSelectedNodeId(null)
  }

  const isFiltered = search || filterKind !== 'all' || filterNamespace || selectedNodeId

  if (loading) return <div className="empty-state"><p>Cargando grafo…</p></div>
  if (error) return <div className="empty-state"><p style={{ color: '#f87171' }}>Error: {error}</p></div>
  if (!data || data.nodes.length === 0) return (
    <div className="empty-state">
      <h3>Sin datos en el grafo</h3>
      <p>Ejecuta Sync para cargar eventos de linaje.</p>
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 8 }}>
      {/* Toolbar */}
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', padding: '0 4px', flexShrink: 0, flexWrap: 'wrap' }}>
        <input
          value={search}
          onChange={e => { setSearch(e.target.value); setSelectedNodeId(null) }}
          placeholder="Buscar nombre o namespace…"
          style={{
            flex: 1, minWidth: 140,
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 6, padding: '6px 10px', color: 'var(--text)', fontSize: 12,
          }}
        />
        <Select
          value={filterNamespace}
          onChange={v => { setFilterNamespace(v); setSelectedNodeId(null) }}
          options={namespaceOptions}
          style={{ minWidth: 160 }}
        />
        <Select
          value={filterKind}
          onChange={v => { setFilterKind(v); setSelectedNodeId(null) }}
          options={[
            { value: 'all', label: 'Todos' },
            { value: 'job', label: 'Jobs' },
            { value: 'dataset', label: 'Datasets' },
          ]}
          style={{ minWidth: 100 }}
        />
        {isFiltered && (
          <button
            onClick={clearAll}
            style={{
              background: 'transparent', border: '1px solid var(--border)',
              borderRadius: 6, padding: '5px 10px', color: 'var(--text-muted)',
              fontSize: 11, cursor: 'pointer',
            }}
          >
            ✕ Limpiar
          </button>
        )}
        <span style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap', marginLeft: 'auto' }}>
          {filtered?.nodes.length ?? 0} nodos · {filtered?.edges.length ?? 0} aristas
          {selectedNodeId && <span style={{ color: '#f59e0b', marginLeft: 6 }}>· flujo activo</span>}
        </span>
      </div>

      {/* Graph canvas */}
      <div style={{ flex: 1, borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border)', position: 'relative' }}>
        {selectedNodeId && (
          <div style={{
            position: 'absolute', top: 8, left: 8, zIndex: 10,
            background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.4)',
            borderRadius: 6, padding: '4px 10px', fontSize: 11, color: '#f59e0b',
            pointerEvents: 'none',
          }}>
            Flujo completo · haz clic en vacío para resetear
          </div>
        )}
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
          onPaneClick={handlePaneClick}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.05}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#1e293b" gap={20} />
          <Controls style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }} />
          <MiniMap
            nodeColor={n =>
              n.id === selectedNodeId ? '#f59e0b'
              : (n.style?.border as string)?.includes('3b82f6') ? '#3b82f6'
              : '#334155'
            }
            style={{ background: '#0f172a', border: '1px solid var(--border)' }}
            maskColor="rgba(0,0,0,0.4)"
          />
        </ReactFlow>
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 12, padding: '0 4px', flexShrink: 0, fontSize: 11, color: 'var(--text-muted)', flexWrap: 'wrap' }}>
        <span><span style={{ color: '#3b82f6' }}>■</span> Job ETL</span>
        <span><span style={{ color: '#334155' }}>■</span> Dataset</span>
        <span><span style={{ color: '#f59e0b' }}>■</span> Seleccionado</span>
        <span><span style={{ background: '#14532d', padding: '0 3px', borderRadius: 2 }}>py</span> código Glue</span>
        <span><span style={{ background: '#3b1f5e', padding: '0 3px', borderRadius: 2 }}>sql</span> SQL</span>
        <span><span style={{ background: '#4a1d1d', padding: '0 3px', borderRadius: 2 }}>col</span> linaje columnas</span>
        <span style={{ marginLeft: 'auto' }}>Clic en nodo para flujo completo</span>
      </div>
    </div>
  )
}
