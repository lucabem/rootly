import React from 'react'
import { ApiNode, NODE_WIDTH, NODE_HEIGHT, COL_NODE_WIDTH, COL_NODE_HEIGHT } from './types'

export function badgeStyle(bg: string): React.CSSProperties {
  return {
    background: bg, borderRadius: 4, padding: '1px 5px',
    fontSize: 10, color: '#cbd5e1', letterSpacing: '0.02em',
    whiteSpace: 'nowrap',
  }
}

export function nodeStyle(n: ApiNode, isCentral: boolean): React.CSSProperties {
  if (isCentral) {
    return {
      background: '#1c2a1c', border: '2px solid #22c55e', borderRadius: 8,
      boxShadow: '0 0 0 3px rgba(34,197,94,0.2)', padding: '6px 10px',
      fontSize: 12, color: '#e2e8f0', width: NODE_WIDTH, minHeight: NODE_HEIGHT, cursor: 'pointer',
    }
  }
  if (n.kind === 'job') {
    return {
      background: '#1e293b', border: '1.5px solid #3b82f6', borderRadius: 8,
      padding: '6px 10px', fontSize: 12, color: '#e2e8f0',
      width: NODE_WIDTH, minHeight: NODE_HEIGHT, cursor: 'pointer',
    }
  }
  return {
    background: '#0f172a', border: '1.5px solid #334155', borderRadius: 8,
    padding: '6px 10px', fontSize: 12, color: '#e2e8f0',
    width: NODE_WIDTH, minHeight: NODE_HEIGHT, cursor: 'pointer',
  }
}

export function colNodeStyle(isRoot: boolean): React.CSSProperties {
  if (isRoot) {
    return {
      background: '#1c1030', border: '2px solid #8b5cf6', borderRadius: 8,
      boxShadow: '0 0 0 3px rgba(139,92,246,0.2)', padding: '6px 10px',
      fontSize: 12, color: '#e2e8f0', width: COL_NODE_WIDTH, minHeight: COL_NODE_HEIGHT, cursor: 'default',
    }
  }
  return {
    background: '#0f0a1e', border: '1.5px solid #4c1d95', borderRadius: 8,
    padding: '6px 10px', fontSize: 12, color: '#e2e8f0',
    width: COL_NODE_WIDTH, minHeight: COL_NODE_HEIGHT, cursor: 'default',
  }
}

export function NodeLabel({ node, isCentral, isExpandable, onDotsClick }: {
  node: ApiNode
  isCentral: boolean
  isExpandable: boolean
  onDotsClick?: (e: React.MouseEvent, node: ApiNode) => void
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, width: '100%', overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <span style={{ fontSize: 13, flexShrink: 0 }}>{node.kind === 'job' ? '⚙' : isCentral ? '◉' : '◈'}</span>
        <span style={{ fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', flex: 1, minWidth: 0 }}>
          {node.name}
        </span>
        {isExpandable && (
          <span style={{ fontSize: 11, color: '#f59e0b', fontWeight: 700, flexShrink: 0, lineHeight: 1 }}>+</span>
        )}
        <button
          onClick={e => { e.stopPropagation(); onDotsClick?.(e, node) }}
          onMouseEnter={e => { e.currentTarget.style.color = '#94a3b8'; e.currentTarget.style.background = 'rgba(255,255,255,0.08)' }}
          onMouseLeave={e => { e.currentTarget.style.color = '#475569'; e.currentTarget.style.background = 'none' }}
          title="Opciones"
          style={{
            background: 'none', border: 'none', color: '#475569',
            cursor: 'pointer', padding: '0 3px', borderRadius: 3,
            fontSize: 15, lineHeight: 1, flexShrink: 0,
            display: 'flex', alignItems: 'center', transition: 'color 0.1s',
          }}
        >⋮</button>
      </div>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {node.kind === 'dataset' && node.format && node.format !== 'unknown' && (
          <span style={badgeStyle('#1e3a5f')}>{node.format}</span>
        )}
        {node.has_column_lineage && <span style={badgeStyle('#4a1d1d')}>col</span>}
        {node.kind === 'dataset' && node.namespace && (
          <span style={{ ...badgeStyle('#334155'), maxWidth: 130, overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {node.namespace}
          </span>
        )}
      </div>
    </div>
  )
}

export function ColNodeLabel({ dataset, namespace, field, isRoot }: {
  dataset: string
  namespace: string
  field: string
  isRoot: boolean
}) {
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
