export interface ApiNode {
  id: string
  kind: 'job' | 'dataset'
  name: string
  namespace: string
  has_code: boolean
  has_sql: boolean
  has_column_lineage: boolean
  format: string
}

export interface ApiEdge {
  source: string
  target: string
  relation: string
}

export interface GraphData {
  nodes: ApiNode[]
  edges: ApiEdge[]
}

export interface TraceFieldNode {
  field: string
  dataset: string
  namespace?: string
  sources: (TraceFieldNode & { transform?: string; transform_subtype?: string })[]
  cycle?: boolean
}

export type Direction = 'both' | 'upstream' | 'downstream'
export type Mode = 'graph' | 'column'

export type ColNodeData = { dataset: string; namespace: string; field: string; isRoot: boolean }

export interface ContextMenuState {
  x: number
  y: number
  node: ApiNode
}

export const NODE_WIDTH = 220
export const NODE_HEIGHT = 56
export const COL_NODE_WIDTH = 220
export const COL_NODE_HEIGHT = 72
