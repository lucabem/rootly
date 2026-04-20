import { useEffect, useRef, useState } from 'react'

interface AutocompleteProps {
  value: string
  onChange: (value: string) => void
  suggestions: string[]
  placeholder?: string
  disabled?: boolean
  label?: string
}

export function Autocomplete({ value, onChange, suggestions, placeholder, disabled, label }: AutocompleteProps) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const [activeIdx, setActiveIdx] = useState(-1)

  const filtered = value.trim()
    ? suggestions.filter(s => s.toLowerCase().includes(value.toLowerCase()))
    : suggestions

  useEffect(() => {
    setActiveIdx(-1)
  }, [value, open])

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  // Scroll active item into view
  useEffect(() => {
    if (activeIdx >= 0 && listRef.current) {
      const item = listRef.current.children[activeIdx] as HTMLElement
      item?.scrollIntoView({ block: 'nearest' })
    }
  }, [activeIdx])

  function select(s: string) {
    onChange(s)
    setOpen(false)
    setActiveIdx(-1)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'Enter') { setOpen(true); return }
    }
    if (e.key === 'Escape') { setOpen(false); return }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx(i => Math.min(i + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx(i => Math.max(i - 1, -1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (activeIdx >= 0 && filtered[activeIdx]) {
        select(filtered[activeIdx])
      } else if (filtered.length === 1) {
        select(filtered[0])
      }
    }
  }

  function toggleDropdown() {
    if (disabled) return
    if (open) {
      setOpen(false)
    } else {
      setOpen(true)
      inputRef.current?.focus()
    }
  }

  function handleClear() {
    onChange('')
    setOpen(true)
    inputRef.current?.focus()
  }

  const isEmpty = suggestions.length === 0

  return (
    <div className="autocomplete-wrapper" ref={containerRef}>
      {label && <div className="autocomplete-label">{label}</div>}
      <div className={`autocomplete-field ${open ? 'focused' : ''}`}>
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={e => { onChange(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder={isEmpty ? 'Sin datos - ejecuta Sync' : placeholder}
          disabled={disabled || isEmpty}
          autoComplete="off"
        />
        <div className="autocomplete-actions">
          {value && (
            <button className="autocomplete-clear" onMouseDown={e => { e.preventDefault(); handleClear() }} tabIndex={-1}>
              ×
            </button>
          )}
          <button
            className={`autocomplete-chevron ${open ? 'rotated' : ''}`}
            onMouseDown={e => { e.preventDefault(); toggleDropdown() }}
            tabIndex={-1}
            disabled={disabled || isEmpty}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
        </div>
      </div>

      {open && filtered.length > 0 && (
        <ul className="autocomplete-dropdown" ref={listRef} role="listbox">
          {filtered.slice(0, 50).map((s, i) => (
            <li
              key={s}
              role="option"
              aria-selected={s === value}
              className={[s === value ? 'selected' : '', i === activeIdx ? 'active' : ''].join(' ')}
              onMouseDown={e => { e.preventDefault(); select(s) }}
              onMouseEnter={() => setActiveIdx(i)}
            >
              <Highlight text={s} query={value} />
            </li>
          ))}
          {filtered.length > 50 && (
            <li className="autocomplete-more">…y {filtered.length - 50} más - escribe para filtrar</li>
          )}
        </ul>
      )}

      {open && filtered.length === 0 && value && (
        <ul className="autocomplete-dropdown">
          <li className="autocomplete-empty">Sin resultados para «{value}»</li>
        </ul>
      )}
    </div>
  )
}

function Highlight({ text, query }: { text: string; query: string }) {
  if (!query.trim()) return <>{text}</>
  const idx = text.toLowerCase().indexOf(query.toLowerCase())
  if (idx === -1) return <>{text}</>
  return (
    <>
      {text.slice(0, idx)}
      <mark>{text.slice(idx, idx + query.length)}</mark>
      {text.slice(idx + query.length)}
    </>
  )
}
