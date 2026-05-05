import React from 'react'
import { Direction } from './types'
import { Select, inputStyle } from './Select'

interface GraphControlsProps {
  filterNamespace: string
  filterDataset: string
  filterJob: string
  direction: Direction
  namespaceList: string[]
  tableList: string[]
  tableLoading: boolean
  jobSuggestions: string[]
  canApply: boolean
  hasApplied: boolean
  onNamespaceChange: (v: string) => void
  onDatasetChange: (v: string) => void
  onJobChange: (v: string) => void
  onDirectionChange: (v: Direction) => void
  onApply: () => void
  onClear: () => void
}

export function GraphControls({
  filterNamespace, filterDataset, filterJob, direction,
  namespaceList, tableList, tableLoading, jobSuggestions,
  canApply, hasApplied,
  onNamespaceChange, onDatasetChange, onJobChange, onDirectionChange,
  onApply, onClear,
}: GraphControlsProps) {
  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') onApply()
  }

  return (
    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>

      <div style={{ flex: '1 1 160px' }}>
        <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Namespace</label>
        <Select
          value={filterNamespace}
          onChange={v => { onNamespaceChange(v); onDatasetChange(''); onJobChange('') }}
          options={[
            { value: '', label: 'Todos…' },
            ...namespaceList.map(n => ({ value: n, label: n })),
          ]}
        />
      </div>

      <div style={{ flex: '2 1 200px' }}>
        <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
          Dataset <span style={{ color: '#22c55e' }}>◉</span> (elemento central)
          {tableLoading && <span style={{ color: '#64748b', marginLeft: 6 }}>cargando…</span>}
        </label>
        <input
          list="dataset-suggestions"
          value={filterDataset}
          onChange={e => onDatasetChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={filterNamespace ? 'Nombre del dataset…' : 'Selecciona namespace para filtrar…'}
          style={inputStyle}
        />
        <datalist id="dataset-suggestions">
          {tableList.map(name => <option key={name} value={name} />)}
        </datalist>
      </div>

      <div style={{ flex: '2 1 180px' }}>
        <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
          Job <span style={{ color: '#64748b' }}>(opcional)</span>
        </label>
        <input
          list="job-suggestions"
          value={filterJob}
          onChange={e => onJobChange(e.target.value)}
          onKeyDown={handleKeyDown}
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
          onChange={v => onDirectionChange(v as Direction)}
          options={[
            { value: 'both', label: '↕ Ambas' },
            { value: 'upstream', label: '↑ Upstream' },
            { value: 'downstream', label: '↓ Downstream' },
          ]}
        />
      </div>

      <div style={{ display: 'flex', gap: 6, alignSelf: 'flex-end' }}>
        <button
          onClick={onApply}
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
        {hasApplied && (
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
      </div>
    </div>
  )
}
