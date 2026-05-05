import ReactFlow, { Background, Controls, MiniMap } from 'reactflow'
import 'reactflow/dist/style.css'
import { ApiNode, Mode } from './graph/types'
import { NodeContextMenu } from './graph/NodeContextMenu'
import { GraphControls } from './graph/GraphControls'
import { ColumnControls } from './graph/ColumnControls'
import { useGraphData } from './graph/useGraphData'
import { useGraphFilter } from './graph/useGraphFilter'
import { useColumnTrace } from './graph/useColumnTrace'
import { useState } from 'react'

interface GraphViewProps {
  onAskAboutNode?: (node: Pick<ApiNode, 'kind' | 'name' | 'namespace'> & { field?: string }) => void
}

export function GraphView({ onAskAboutNode }: GraphViewProps) {
  const [mode, setMode] = useState<Mode>('graph')

  const { data, loading, error, namespaceList, successors, predecessors } = useGraphData()

  const graph = useGraphFilter(data, successors, predecessors)

  const col = useColumnTrace()

  if (loading) return <div className="empty-state"><p>Cargando grafo…</p></div>
  if (error) return <div className="empty-state"><p style={{ color: '#f87171' }}>Error: {error}</p></div>
  if (!data || data.nodes.length === 0) return (
    <div className="empty-state">
      <h3>Sin datos en el grafo</h3>
      <p>Ejecuta Sync para cargar eventos de linaje.</p>
    </div>
  )

  const activeNodes = mode === 'column' ? col.colNodes : graph.nodes
  const activeEdges = mode === 'column' ? col.colEdges : graph.edges
  const onActiveNodesChange = mode === 'column' ? col.onColNodesChange : graph.onNodesChange
  const onActiveEdgesChange = mode === 'column' ? col.onColEdgesChange : graph.onEdgesChange

  const showEmpty = mode === 'graph' ? !graph.isActive : !col.colActive && !col.colLoading

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 10 }}>

      {/* Filter panel */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 8, padding: '14px 16px', flexShrink: 0,
      }}>
        {/* Mode toggle */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 12 }}>
          {(['graph', 'column'] as Mode[]).map(m => (
            <button
              key={m}
              onClick={() => setMode(m)}
              style={{
                background: mode === m ? (m === 'column' ? '#4c1d95' : '#14532d') : 'transparent',
                border: `1px solid ${mode === m ? (m === 'column' ? '#8b5cf6' : '#22c55e') : 'var(--border)'}`,
                borderRadius: 6, padding: '5px 14px',
                color: mode === m ? (m === 'column' ? '#c4b5fd' : '#86efac') : 'var(--text-muted)',
                fontSize: 12, fontWeight: mode === m ? 600 : 400, cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              {m === 'graph' ? 'Grafo de datasets' : 'Linaje de columna'}
            </button>
          ))}
        </div>

        {mode === 'graph' && (
          <GraphControls
            filterNamespace={graph.filterNamespace}
            filterDataset={graph.filterDataset}
            filterJob={graph.filterJob}
            direction={graph.direction}
            namespaceList={namespaceList}
            tableList={graph.tableList}
            tableLoading={graph.tableLoading}
            jobSuggestions={graph.jobSuggestions}
            canApply={graph.canApply}
            hasApplied={graph.applied !== null}
            onNamespaceChange={graph.setFilterNamespace}
            onDatasetChange={graph.setFilterDataset}
            onJobChange={graph.setFilterJob}
            onDirectionChange={graph.setDirection}
            onApply={graph.handleApply}
            onClear={graph.handleClear}
          />
        )}

        {mode === 'column' && (
          <ColumnControls
            colNamespace={col.colNamespace}
            colTable={col.colTable}
            colColumn={col.colColumn}
            namespaceList={namespaceList}
            tableList={col.tableList}
            columnList={col.columnList}
            tableLoading={col.tableLoading}
            columnLoading={col.columnLoading}
            colLoading={col.colLoading}
            colError={col.colError}
            colActive={col.colActive}
            onNamespaceChange={col.setColNamespace}
            onTableChange={col.setColTable}
            onColumnChange={col.setColColumn}
            onTrace={col.handleColTrace}
            onClear={col.handleColClear}
            onAsk={onAskAboutNode ? () => onAskAboutNode({
              kind: 'dataset',
              name: col.colTable,
              namespace: col.colNamespace,
              field: col.colColumn || undefined,
            }) : undefined}
          />
        )}
      </div>

      {/* Graph canvas */}
      <div style={{ flex: 1, borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border)', position: 'relative' }}>

        {showEmpty && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 10, background: 'var(--bg)',
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12,
          }}>
            <span style={{ fontSize: 36, opacity: 0.3 }}>◈</span>
            {mode === 'graph' ? (
              <>
                <p style={{ color: 'var(--text-muted)', fontSize: 14, margin: 0 }}>
                  {graph.applied ? 'Sin resultados para los filtros aplicados' : 'Utiliza los filtros para visualizar'}
                </p>
                {!graph.applied && (
                  <p style={{ color: 'var(--text-muted)', fontSize: 12, margin: 0, opacity: 0.6 }}>
                    {data.nodes.length} nodos disponibles · introduce un dataset y pulsa Visualizar
                  </p>
                )}
              </>
            ) : (
              <>
                <p style={{ color: 'var(--text-muted)', fontSize: 14, margin: 0 }}>
                  {col.colLoading ? 'Trazando linaje de columna…' : 'Introduce un dataset y columna y pulsa Trazar'}
                </p>
                <p style={{ color: 'var(--text-muted)', fontSize: 12, margin: 0, opacity: 0.6 }}>
                  La columna vacía traza todas las columnas del dataset con linaje registrado
                </p>
              </>
            )}
          </div>
        )}

        {mode === 'graph' && graph.isActive && (
          <div style={{
            position: 'absolute', top: 8, left: 8, zIndex: 10,
            background: 'rgba(15,23,42,0.9)', border: '1px solid var(--border)',
            borderRadius: 6, padding: '5px 10px', fontSize: 11, color: 'var(--text-muted)',
            pointerEvents: 'none', display: 'flex', gap: 8, alignItems: 'center',
          }}>
            <span>{graph.visibleIds.size} nodos</span>
            <span style={{ color: '#22c55e' }}>
              {graph.applied!.direction === 'both' ? '↕' : graph.applied!.direction === 'upstream' ? '↑' : '↓'}
            </span>
            {graph.expandableIds.size > 0 && (
              <span style={{ color: '#f59e0b' }}>
                {graph.expandableIds.size} expandible{graph.expandableIds.size > 1 ? 's' : ''} <span style={{ fontWeight: 700 }}>+</span>
              </span>
            )}
          </div>
        )}

        {mode === 'column' && col.colActive && col.colInfo && (
          <div style={{
            position: 'absolute', top: 8, left: 8, zIndex: 10,
            background: 'rgba(15,10,30,0.9)', border: '1px solid #4c1d95',
            borderRadius: 6, padding: '5px 10px', fontSize: 11, color: '#c4b5fd',
            pointerEvents: 'none', display: 'flex', gap: 8, alignItems: 'center',
          }}>
            <span style={{ color: '#8b5cf6' }}>◈</span>
            <span>{col.colInfo.fields} campo{col.colInfo.fields !== 1 ? 's' : ''}</span>
            <span style={{ color: '#4c1d95' }}>·</span>
            <span>{col.colInfo.datasets} dataset{col.colInfo.datasets !== 1 ? 's' : ''} en el camino</span>
          </div>
        )}

        {graph.contextMenu && (
          <NodeContextMenu
            menu={graph.contextMenu}
            onAsk={() => {
              onAskAboutNode?.(graph.contextMenu!.node)
              graph.setContextMenu(null)
            }}
            onClose={() => graph.setContextMenu(null)}
          />
        )}

        <ReactFlow
          nodes={activeNodes}
          edges={activeEdges}
          onNodesChange={onActiveNodesChange}
          onEdgesChange={onActiveEdgesChange}
          onNodeClick={mode === 'graph' ? graph.handleNodeClick : undefined}
          onPaneClick={() => graph.setContextMenu(null)}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          minZoom={0.05}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#1e293b" gap={20} />
          <Controls style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }} />
          {mode === 'graph' && graph.isActive && (
            <MiniMap
              nodeColor={n =>
                graph.visibleIds.has(n.id) && (n.style?.border as string)?.includes('22c55e') ? '#22c55e'
                : (n.style?.border as string)?.includes('3b82f6') ? '#3b82f6'
                : '#334155'
              }
              style={{ background: '#0f172a', border: '1px solid var(--border)' }}
              maskColor="rgba(0,0,0,0.4)"
            />
          )}
          {mode === 'column' && col.colActive && (
            <MiniMap
              nodeColor={n =>
                (n.style?.border as string)?.includes('8b5cf6') ? '#8b5cf6' : '#4c1d95'
              }
              style={{ background: '#0f0a1e', border: '1px solid #4c1d95' }}
              maskColor="rgba(0,0,0,0.4)"
            />
          )}
        </ReactFlow>
      </div>

      {/* Legend */}
      {mode === 'graph' ? (
        <div style={{
          display: 'flex', gap: 12, padding: '0 4px', flexShrink: 0,
          fontSize: 11, color: 'var(--text-muted)', flexWrap: 'wrap',
        }}>
          <span><span style={{ color: '#22c55e' }}>◉</span> Dataset central</span>
          <span><span style={{ color: '#3b82f6' }}>■</span> Job ETL</span>
          <span><span style={{ color: '#334155' }}>■</span> Dataset</span>
          <span><span style={{ color: '#f59e0b', fontWeight: 700 }}>+</span> tiene vecinos ocultos</span>
          <span><span style={{ background: '#14532d', padding: '0 3px', borderRadius: 2 }}>py</span> código Glue</span>
          <span><span style={{ background: '#3b1f5e', padding: '0 3px', borderRadius: 2 }}>sql</span> SQL</span>
          <span><span style={{ background: '#4a1d1d', padding: '0 3px', borderRadius: 2 }}>col</span> linaje columnas</span>
          <span style={{ marginLeft: 'auto', opacity: 0.5 }}>Clic en nodo para expandir vecinos directos</span>
        </div>
      ) : (
        <div style={{
          display: 'flex', gap: 12, padding: '0 4px', flexShrink: 0,
          fontSize: 11, color: 'var(--text-muted)', flexWrap: 'wrap',
        }}>
          <span><span style={{ color: '#8b5cf6' }}>◉</span> Campo trazado (destino)</span>
          <span><span style={{ color: '#4c1d95' }}>◈</span> Campo fuente</span>
          <span><span style={{ color: '#8b5cf6' }}>──▶</span> flujo de dato + tipo transformación</span>
          <span style={{ marginLeft: 'auto', opacity: 0.5 }}>Izquierda = origen · Derecha = destino</span>
        </div>
      )}
    </div>
  )
}
