import React from 'react'

export const inputStyle: React.CSSProperties = {
  background: 'var(--bg-card)', border: '1px solid var(--border)',
  borderRadius: 6, padding: '8px 12px', color: 'var(--text)',
  fontSize: 13, width: '100%', boxSizing: 'border-box',
}

export const selectStyle: React.CSSProperties = {
  background: 'var(--bg-card)', border: '1px solid var(--border)',
  borderRadius: 6, padding: '8px 28px 8px 12px', color: 'var(--text)',
  fontSize: 13, cursor: 'pointer', appearance: 'none', WebkitAppearance: 'none',
  width: '100%', boxSizing: 'border-box',
}

export function Select({ value, onChange, options }: {
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
