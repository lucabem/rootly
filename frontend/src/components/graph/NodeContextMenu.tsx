import { useEffect, useState } from 'react'
import { ContextMenuState } from './types'

function MenuItem({ icon, label, onClick }: { icon: string; label: string; onClick: () => void }) {
  const [hover, setHover] = useState(false)
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        width: '100%', padding: '10px 14px',
        background: hover ? 'rgba(99,102,241,0.15)' : 'none',
        border: 'none', color: hover ? '#818cf8' : '#e2e8f0',
        fontSize: 13, cursor: 'pointer', textAlign: 'left',
        transition: 'background 0.1s, color 0.1s',
        fontFamily: 'inherit',
      }}
    >
      <span style={{ fontSize: 15 }}>{icon}</span>
      {label}
    </button>
  )
}

export function NodeContextMenu({ menu, onAsk, onClose }: {
  menu: ContextMenuState
  onAsk: () => void
  onClose: () => void
}) {
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const el = document.getElementById('node-context-menu')
      if (el && !el.contains(e.target as Element)) onClose()
    }
    window.addEventListener('mousedown', handler)
    return () => window.removeEventListener('mousedown', handler)
  }, [onClose])

  return (
    <div
      id="node-context-menu"
      style={{
        position: 'fixed', left: menu.x, top: menu.y, zIndex: 1000,
        background: '#1e293b', border: '1px solid #334155', borderRadius: 8,
        boxShadow: '0 8px 32px rgba(0,0,0,0.6)', minWidth: 230,
        overflow: 'hidden', userSelect: 'none',
      }}
    >
      <div style={{
        padding: '8px 12px', fontSize: 11, color: '#64748b',
        borderBottom: '1px solid #334155', display: 'flex', alignItems: 'center', gap: 6,
      }}>
        <span>{menu.node.kind === 'job' ? '⚙' : '◈'}</span>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#94a3b8', fontWeight: 500 }}>
          {menu.node.name}
        </span>
      </div>
      <MenuItem
        icon="💬"
        label={`Pregunta a Lucy sobre ${menu.node.kind === 'job' ? 'este job' : 'este dataset'}…`}
        onClick={onAsk}
      />
    </div>
  )
}
