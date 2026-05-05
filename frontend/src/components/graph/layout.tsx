import React from 'react'
import dagre from '@dagrejs/dagre'
import { Node, Edge, Position, MarkerType } from 'reactflow'
import {
  ApiNode, ApiEdge, ColNodeData, TraceFieldNode,
  NODE_WIDTH, NODE_HEIGHT, COL_NODE_WIDTH, COL_NODE_HEIGHT,
} from './types'
import { NodeLabel, ColNodeLabel, nodeStyle, colNodeStyle } from './NodeLabel'

export function layoutGraph(
  apiNodes: ApiNode[],
  apiEdges: ApiEdge[],
  centralIds: Set<string>,
  expandableIds: Set<string>,
  onDotsClick?: (e: React.MouseEvent, node: ApiNode) => void,
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
      data: { label: <NodeLabel node={n} isCentral={isCentral} isExpandable={isExpandable} onDotsClick={onDotsClick} /> },
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

export function collectColField(
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

export function layoutColGraph(
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
