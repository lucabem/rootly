import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Autocomplete } from './components/Autocomplete'
import { GraphView } from './components/GraphView'

const SUGGESTIONS = [
  '¿Qué datasets existen en producción?',
  '¿Qué jobs producen el dataset contratos?',
  '¿Qué se rompe si cambio el schema de orders?',
  '¿De dónde viene la columna id_cliente?',
]

const LOADING_HINTS = [
  'Consultando el grafo de linaje…',
  'Buscando en el índice semántico…',
  'Ejecutando herramienta…',
  'Generando respuesta…',
]

function CodeBlock({ children }: { children: React.ReactNode }) {
  const [copied, setCopied] = useState(false)
  const text = (() => {
    const child = (children as any)?.[0]
    return child?.props?.children ?? ''
  })()
  return (
    <div className="code-block-wrapper">
      <button
        className={`copy-btn${copied ? ' copied' : ''}`}
        onClick={() => {
          navigator.clipboard.writeText(String(text).trimEnd())
          setCopied(true)
          setTimeout(() => setCopied(false), 2000)
        }}
      >
        {copied ? '✓ copiado' : 'copiar'}
      </button>
      <pre>{children}</pre>
    </div>
  )
}

type Role = 'user' | 'assistant'
type Tab = 'chat' | 'impact' | 'graph' | 'tasks'
type TaskStatus = 'PENDING' | 'STARTED' | 'SUCCESS' | 'FAILURE'

interface Message {
  id: number
  role: Role
  content: string
}

interface Stats {
  datasets: number
  jobs: number
  edges: number
  indexed_docs: number
  error?: string
}

interface ImpactNode {
  kind: string
  name: string
}

interface ImpactResult {
  dataset: string
  layers: ImpactNode[][]
}

interface DatasetEntry {
  key: string
  namespace: string
  name: string
}

interface TaskEntry {
  id: string
  status: TaskStatus
  message: string
  started_at: number
  finished_at?: number
  result?: { docs: number; datasets: number; jobs: number; source: string }
  error?: string
}

const TASKS_KEY = 'rag_tasks'
let msgId = 0

function loadTasks(): TaskEntry[] {
  try { return JSON.parse(localStorage.getItem(TASKS_KEY) ?? '[]') } catch { return [] }
}
function saveTasks(tasks: TaskEntry[]) {
  localStorage.setItem(TASKS_KEY, JSON.stringify(tasks.slice(0, 50)))
}

function timeAgo(ts: number) {
  const s = Math.floor((Date.now() - ts) / 1000)
  if (s < 60) return `hace ${s}s`
  if (s < 3600) return `hace ${Math.floor(s / 60)}m`
  return `hace ${Math.floor(s / 3600)}h`
}

export default function App() {
  const [tab, setTab] = useState<Tab>('chat')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [stats, setStats] = useState<Stats | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [toast, setToast] = useState<{ msg: string; type: 'success' | 'error' } | null>(null)
  const [impactNamespace, setImpactNamespace] = useState('')
  const [impactTable, setImpactTable] = useState('')
  const [impactResults, setImpactResults] = useState<ImpactResult[] | null>(null)
  const [impactLoading, setImpactLoading] = useState(false)
  const [allDatasets, setAllDatasets] = useState<DatasetEntry[]>([])
  const [allNamespaces, setAllNamespaces] = useState<string[]>([])
  const [tasks, setTasks] = useState<TaskEntry[]>(loadTasks)
  const [loadingHint, setLoadingHint] = useState(0)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const MAX_TASK_AGE_MS = 24 * 60 * 60 * 1000
  const pendingTasks = tasks.filter(t =>
    (t.status === 'PENDING' || t.status === 'STARTED') &&
    Date.now() - t.started_at < MAX_TASK_AGE_MS
  )

  // Initial load
  useEffect(() => { fetchStats(); fetchDatasets(); fetchHistory() }, [])

  // Auto-scroll chat
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading])

  // Toast auto-dismiss
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 3500)
    return () => clearTimeout(t)
  }, [toast])

  // Cycle loading hint text while waiting for response
  useEffect(() => {
    if (!loading) { setLoadingHint(0); return }
    const t = setInterval(() => setLoadingHint(h => (h + 1) % LOADING_HINTS.length), 3000)
    return () => clearInterval(t)
  }, [loading])

  // Persist tasks
  useEffect(() => { saveTasks(tasks) }, [tasks])

  // Poll pending tasks every 3 seconds
  useEffect(() => {
    if (pendingTasks.length === 0) return
    const interval = setInterval(async () => {
      for (const task of pendingTasks) {
        try {
          const r = await fetch(`/api/task/${task.id}`)
          const data = await r.json()
          if (data.status !== task.status) {
            setTasks(prev => prev.map(t =>
              t.id === task.id
                ? {
                    ...t,
                    status: data.status,
                    result: data.result,
                    error: data.error,
                    finished_at: ['SUCCESS', 'FAILURE'].includes(data.status) ? Date.now() : undefined,
                  }
                : t
            ))
            if (data.status === 'SUCCESS') {
              await fetch('/api/reload', { method: 'POST' })
              fetchStats()
              fetchDatasets()
              setToast({ msg: `Sync completado - ${data.result?.docs ?? 0} docs`, type: 'success' })
            }
            if (data.status === 'FAILURE') {
              setToast({ msg: `Sync fallido: ${data.error}`, type: 'error' })
            }
          }
        } catch { /* ignore */ }
      }
    }, 3000)
    return () => clearInterval(interval)
  }, [pendingTasks])

  async function fetchHistory() {
    try {
      const r = await fetch('/api/history?n=30')
      const data = await r.json()
      const loaded: Message[] = (data.messages ?? []).map((m: { role: Role; content: string }) => ({
        id: ++msgId,
        role: m.role,
        content: m.content,
      }))
      if (loaded.length > 0) setMessages(loaded)
    } catch { /* silent */ }
  }

  async function fetchDatasets() {
    try {
      const r = await fetch('/api/datasets')
      const data = await r.json()
      setAllDatasets(data.datasets ?? [])
      setAllNamespaces(data.namespaces ?? [])
    } catch { /* silent */ }
  }

  async function fetchStats() {
    try {
      const r = await fetch('/api/stats')
      setStats(await r.json())
    } catch {
      setStats({ datasets: 0, jobs: 0, edges: 0, indexed_docs: 0, error: 'offline' })
    }
  }

  async function sendQuestion(q: string) {
    if (!q || loading) return
    setMessages(prev => [...prev, { id: ++msgId, role: 'user', content: q }])
    setLoading(true)
    try {
      const history = messages.slice(-10).map(m => ({ role: m.role, content: m.content }))
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, history }),
      })
      const data = await r.json()
      if (r.status === 429) throw new Error(data.detail || 'Límite de uso alcanzado. Espera unos segundos e inténtalo de nuevo.')
      if (!r.ok) throw new Error(data.detail || 'Error del servidor')
      setMessages(prev => [...prev, { id: ++msgId, role: 'assistant', content: data.answer }])
    } catch (e: any) {
      setMessages(prev => [...prev, { id: ++msgId, role: 'assistant', content: `**Error:** ${e.message}` }])
    } finally {
      setLoading(false)
    }
  }

  async function sendMessage() {
    const q = input.trim()
    if (!q) return
    setInput('')
    await sendQuestion(q)
  }

  function handleAskAboutNode(node: { kind: string; name: string; namespace: string; field?: string }) {
    setTab('chat')
    const ns = node.namespace ? ` (${node.namespace})` : ''
    let q: string
    if (node.field) {
      q = `Cuéntame sobre la columna "${node.field}" del dataset "${node.name}"${ns}: de dónde viene, qué transformaciones sufre y qué jobs la producen o modifican.`
    } else if (node.kind === 'job') {
      q = `Cuéntame sobre el job ETL "${node.name}": qué datasets lee y escribe, cuál es su lógica y su historial de ejecuciones recientes.`
    } else {
      q = `Cuéntame sobre el dataset "${node.name}"${ns}: su schema, los jobs que lo producen y consumen, y si tiene linaje de columnas disponible.`
    }
    sendQuestion(q)
  }

  async function handleSync() {
    setSyncing(true)
    try {
      const r = await fetch('/api/sync', { method: 'POST' })
      const data = await r.json()
      if (!r.ok) throw new Error(data.detail || 'Error')
      const newTask: TaskEntry = {
        id: data.task_id,
        status: 'PENDING',
        message: data.message,
        started_at: Date.now(),
      }
      setTasks(prev => [newTask, ...prev])
      setTab('tasks')
    } catch (e: any) {
      setToast({ msg: `Error: ${e.message}`, type: 'error' })
    } finally {
      setSyncing(false)
    }
  }

  async function runImpact() {
    const table = impactTable.trim()
    if (!table || impactLoading) return
    setImpactLoading(true)
    setImpactResults(null)
    try {
      const r = await fetch('/api/impact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dataset: table, namespace: impactNamespace.trim() || null }),
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.detail || 'Error')
      setImpactResults(data.results)
    } catch (e: any) {
      setToast({ msg: `Error: ${e.message}`, type: 'error' })
    } finally {
      setImpactLoading(false)
    }
  }

  const tableSuggestions = allDatasets
    .filter(d => !impactNamespace || d.namespace.toLowerCase().includes(impactNamespace.toLowerCase()))
    .map(d => d.name)
    .filter((v, i, arr) => arr.indexOf(v) === i)
    .sort()

  function handleChatKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
  }

  const SpinIcon = () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  )

  return (
    <>
      {/* Header */}
      <header className="header">
        <div className="header-title">
          <img src="/rootly.jpeg" alt="Rootly" className="header-logo" />
          RAG Lineage
        </div>
        <div className="header-stats">
          {stats && !stats.error ? (
            <>
              <span className="stat-badge">{stats.datasets} datasets</span>
              <span className="stat-badge">{stats.jobs} jobs</span>
              <span className="stat-badge muted">{stats.indexed_docs} docs</span>
            </>
          ) : (
            <span className="stat-badge muted">sin índice</span>
          )}
          <button className={`sync-btn ${syncing ? 'spinning' : ''}`} onClick={handleSync} disabled={syncing}>
            <svg className="sync-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M23 4v6h-6M1 20v-6h6" />
              <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
            </svg>
            {syncing ? 'Despachando…' : 'Sync'}
          </button>
        </div>
      </header>

      {/* Tabs */}
      <nav className="tabs">
        <button className={`tab ${tab === 'chat' ? 'active' : ''}`} onClick={() => setTab('chat')}>Chat</button>
        <button className={`tab ${tab === 'impact' ? 'active' : ''}`} onClick={() => setTab('impact')}>Impacto</button>
        <button className={`tab ${tab === 'graph' ? 'active' : ''}`} onClick={() => setTab('graph')}>Grafo</button>
        <button className={`tab ${tab === 'tasks' ? 'active' : ''}`} onClick={() => setTab('tasks')}>
          Tareas
          {pendingTasks.length > 0 && <span className="tab-badge">{pendingTasks.length}</span>}
        </button>
      </nav>

      {/* Main */}
      <main className="main">

        {/* ── Chat ── */}
        {tab === 'chat' && (
          <>
            <div className="messages">
              {messages.length === 0 && !loading && (
                <div className="empty-state">
                  <div className="icon">
                    <img src="/rootly.jpeg" alt="Rootly" className="empty-logo" />
                  </div>
                  <h3>Consulta tu linaje de datos</h3>
                  <p>Pregunta sobre datasets, pipelines, impacto de cambios de schema y más.</p>
                  <div className="suggestions">
                    {SUGGESTIONS.map(s => (
                      <button key={s} className="suggestion-chip" onClick={() => setInput(s)}>
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {messages.map(msg => (
                <div key={msg.id} className={`message ${msg.role}`}>
                  <span className="message-label">{msg.role === 'user' ? 'Tú' : 'Asistente'}</span>
                  <div className="bubble">
                    {msg.role === 'assistant'
                      ? (
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{ pre: ({ children }) => <CodeBlock>{children}</CodeBlock> }}
                        >
                          {msg.content}
                        </ReactMarkdown>
                      )
                      : msg.content}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="message assistant">
                  <span className="message-label">Asistente</span>
                  <div className="bubble">
                    <div className="typing">
                      <span /><span /><span />
                      <span className="loading-hint">{LOADING_HINTS[loadingHint]}</span>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
            <div className="input-bar">
              <textarea rows={1} value={input} onChange={e => setInput(e.target.value)}
                onKeyDown={handleChatKey} placeholder="¿Qué pipelines fallarían si cambio el schema de orders?"
                disabled={loading}
                style={{ minHeight: '42px', maxHeight: '120px' }}
                onInput={e => {
                  const el = e.currentTarget
                  el.style.height = 'auto'
                  el.style.height = `${Math.min(el.scrollHeight, 120)}px`
                }} />
              <button className="send-btn" onClick={sendMessage} disabled={loading || !input.trim()}>Enviar</button>
            </div>
          </>
        )}

        {/* ── Impacto ── */}
        {tab === 'impact' && (
          <div className="impact-panel">
            <div className="impact-search">
              <Autocomplete label="Base de datos" value={impactNamespace}
                onChange={v => { setImpactNamespace(v); setImpactResults(null) }}
                suggestions={allNamespaces} placeholder="Filtra por namespace…" disabled={impactLoading} />
              <Autocomplete label="Tabla" value={impactTable}
                onChange={v => { setImpactTable(v); setImpactResults(null) }}
                suggestions={tableSuggestions} placeholder="Busca una tabla…" disabled={impactLoading} />
              <button className="send-btn" onClick={runImpact} disabled={impactLoading || !impactTable.trim()}>
                {impactLoading ? 'Analizando…' : 'Analizar'}
              </button>
            </div>
            <div className="impact-results">
              {!impactResults && !impactLoading && (
                <div className="empty-state">
                  <div className="icon">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" opacity="0.5">
                      <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
                    </svg>
                  </div>
                  <h3>Análisis de impacto</h3>
                  <p>Selecciona una tabla para ver qué jobs y datasets downstream se verían afectados.</p>
                </div>
              )}
              {impactResults?.length === 0 && (
                <p className="no-impact">Dataset no encontrado. Comprueba el nombre o ejecuta Sync.</p>
              )}
              {impactResults?.map((result, i) => (
                <div key={i} className="impact-card">
                  <h3>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <ellipse cx="12" cy="5" rx="9" ry="3" />
                      <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
                      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
                    </svg>
                    {result.dataset}
                  </h3>
                  {result.layers.length === 0 && <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Sin dependencias downstream.</p>}
                  {result.layers.map((layer, li) => (
                    <div key={li} className="impact-layer">
                      <div className="impact-layer-label">Nivel {li + 1}</div>
                      <div className="impact-nodes">
                        {layer.map((node, ni) => (
                          <span key={ni} className={`impact-node ${node.kind}`}>
                            {node.kind === 'job' ? '⚙' : '◈'} {node.name}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Grafo ── */}
        {tab === 'graph' && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <GraphView onAskAboutNode={handleAskAboutNode} />
          </div>
        )}

        {/* ── Tareas ── */}
        {tab === 'tasks' && (
          <div className="tasks-panel">
            <div className="tasks-header">
              <span>{tasks.length} tarea{tasks.length !== 1 ? 's' : ''} · polling cada 3s para las activas</span>
              {tasks.length > 0 && (
                <button className="clear-btn" onClick={() => setTasks([])}>Limpiar todo</button>
              )}
            </div>
            <div className="tasks-list">
              {tasks.length === 0 && (
                <div className="empty-state">
                  <div className="icon">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" opacity="0.5">
                      <path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
                    </svg>
                  </div>
                  <h3>Sin tareas</h3>
                  <p>Pulsa <strong>Sync</strong> para encolar un sync y verlo aquí.</p>
                </div>
              )}
              {tasks.map(task => (
                <div key={task.id} className={`task-card ${task.status}`}>
                  <div className={`task-icon ${task.status}`}>
                    {task.status === 'SUCCESS' && (
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    )}
                    {task.status === 'FAILURE' && (
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                        <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                    )}
                    {(task.status === 'STARTED' || task.status === 'PENDING') && <SpinIcon />}
                  </div>
                  <div className="task-body">
                    <div className="task-top">
                      <span className={`task-status-label ${task.status}`}>
                        {task.status === 'PENDING' ? 'En cola' : task.status === 'STARTED' ? 'En proceso' : task.status === 'SUCCESS' ? 'Completado' : 'Error'}
                      </span>
                      <span className="task-time">
                        {task.finished_at ? timeAgo(task.finished_at) : timeAgo(task.started_at)}
                      </span>
                    </div>
                    <div className="task-message">{task.message}</div>
                    {task.result && (
                      <div className="task-meta">
                        <span className="task-pill">{task.result.docs} docs</span>
                        <span className="task-pill">{task.result.datasets} datasets</span>
                        <span className="task-pill">{task.result.jobs} jobs</span>
                        <span className="task-pill">{task.result.source}</span>
                      </div>
                    )}
                    {task.error && <div className="task-error">{task.error}</div>}
                    <div className="task-id">{task.id}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {toast && <div className={`toast ${toast.type}`}>{toast.msg}</div>}
    </>
  )
}
