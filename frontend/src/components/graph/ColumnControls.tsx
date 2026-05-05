import { Select } from './Select'

interface ColumnControlsProps {
  colNamespace: string
  colTable: string
  colColumn: string
  namespaceList: string[]
  tableList: string[]
  columnList: { name: string; type: string }[]
  tableLoading: boolean
  columnLoading: boolean
  colLoading: boolean
  colError: string | null
  colActive: boolean
  onNamespaceChange: (v: string) => void
  onTableChange: (v: string) => void
  onColumnChange: (v: string) => void
  onTrace: () => void
  onClear: () => void
  onAsk?: () => void
}

export function ColumnControls({
  colNamespace, colTable, colColumn,
  namespaceList, tableList, columnList,
  tableLoading, columnLoading, colLoading, colError, colActive,
  onNamespaceChange, onTableChange, onColumnChange,
  onTrace, onClear, onAsk,
}: ColumnControlsProps) {
  const canTrace = !!colTable && !colLoading

  return (
    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>

      <div style={{ flex: '1 1 160px' }}>
        <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Namespace</label>
        <Select
          value={colNamespace}
          onChange={onNamespaceChange}
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
          onChange={onTableChange}
          options={[
            {
              value: '',
              label: tableLoading ? 'Cargando tablas…' : colNamespace ? 'Selecciona tabla…' : 'Selecciona namespace primero…',
            },
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
          onChange={onColumnChange}
          options={[
            {
              value: '',
              label: colTable
                ? (columnLoading ? 'Cargando columnas…' : columnList.length ? 'Todas las columnas' : 'Sin columnas con linaje')
                : 'Selecciona tabla primero…',
            },
            ...columnList.map(c => ({ value: c.name, label: c.type ? `${c.name} (${c.type})` : c.name })),
          ]}
        />
      </div>

      <div style={{ display: 'flex', gap: 6, alignSelf: 'flex-end' }}>
        <button
          onClick={onTrace}
          disabled={!canTrace}
          style={{
            background: canTrace ? '#8b5cf6' : '#2d1a4a',
            border: 'none', borderRadius: 6, padding: '8px 18px',
            color: canTrace ? '#faf5ff' : '#374151',
            fontSize: 13, fontWeight: 600,
            cursor: canTrace ? 'pointer' : 'not-allowed',
            transition: 'background 0.15s',
          }}
        >
          {colLoading ? 'Trazando…' : 'Trazar'}
        </button>
        {colActive && (
          <button
            onClick={onClear}
            style={{
              background: 'transparent', border: '1px solid var(--border)',
              borderRadius: 6, padding: '8px 12px',
              color: 'var(--text-muted)', fontSize: 12, cursor: 'pointer',
            }}
          >
            ✕ Limpiar
          </button>
        )}
        {colActive && onAsk && (
          <button
            onClick={onAsk}
            style={{
              background: 'transparent', border: '1px solid #4c1d95',
              borderRadius: 6, padding: '8px 12px',
              color: '#a78bfa', fontSize: 12, cursor: 'pointer',
              transition: 'background 0.1s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(139,92,246,0.15)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
          >
            💬 Preguntar
          </button>
        )}
      </div>

      {colError && (
        <div style={{ width: '100%', marginTop: 4, fontSize: 12, color: '#f87171' }}>
          {colError}
        </div>
      )}
    </div>
  )
}
