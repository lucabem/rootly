import { useCallback, useEffect, useState } from 'react'
import { useNodesState, useEdgesState } from 'reactflow'
import { ColNodeData, TraceFieldNode } from './types'
import { collectColField, layoutColGraph } from './layout'

export function useColumnTrace() {
  const [colNamespace, setColNamespace] = useState('')
  const [colTable, setColTable] = useState('')
  const [colColumn, setColColumn] = useState('')
  const [tableList, setTableList] = useState<string[]>([])
  const [columnList, setColumnList] = useState<{ name: string; type: string }[]>([])
  const [tableLoading, setTableLoading] = useState(false)
  const [columnLoading, setColumnLoading] = useState(false)
  const [colLoading, setColLoading] = useState(false)
  const [colError, setColError] = useState<string | null>(null)
  const [colActive, setColActive] = useState(false)
  const [colInfo, setColInfo] = useState<{ fields: number; datasets: number } | null>(null)
  const [colNodes, setColNodes, onColNodesChange] = useNodesState([])
  const [colEdges, setColEdges, onColEdgesChange] = useEdgesState([])

  useEffect(() => {
    setColTable('')
    setColColumn('')
    setColumnList([])
    setTableList([])
    if (!colNamespace) return
    setTableLoading(true)
    fetch(`/api/tables?namespace=${encodeURIComponent(colNamespace)}`)
      .then(r => r.json())
      .then(d => setTableList(d.tables ?? []))
      .catch(() => setTableList([]))
      .finally(() => setTableLoading(false))
  }, [colNamespace])

  useEffect(() => {
    if (!colTable) { setColumnList([]); setColColumn(''); return }
    setColumnLoading(true)
    const params = new URLSearchParams({ dataset: colTable })
    if (colNamespace) params.set('namespace', colNamespace)
    fetch(`/api/schema?${params}`)
      .then(r => r.json())
      .then(d => { setColumnList(d.columns ?? []); setColColumn('') })
      .catch(() => setColumnList([]))
      .finally(() => setColumnLoading(false))
  }, [colTable])

  const handleColTrace = useCallback(() => {
    if (!colTable) return
    setColLoading(true)
    setColError(null)
    setColActive(false)
    setColInfo(null)

    const params = new URLSearchParams({ dataset: colTable })
    if (colColumn) params.set('field', colColumn)
    if (colNamespace) params.set('namespace', colNamespace)

    fetch(`/api/trace?${params}`)
      .then(r => r.json().then(body => ({ ok: r.ok, body })))
      .then(({ ok, body }) => {
        if (!ok) throw new Error(body.detail ?? `HTTP error`)
        const results: Array<{ dataset: string; namespace: string; fields: TraceFieldNode[]; message?: string }> = body.results ?? []
        if (!results.length) throw new Error('Sin resultados.')

        const seenNodes = new Map<string, ColNodeData>()
        const rawEdges: Array<{ source: string; target: string; label: string }> = []
        const seenEdgeKeys = new Set<string>()
        let totalFields = 0

        for (const result of results) {
          if (!result.fields?.length) continue
          for (const fieldRoot of result.fields) {
            totalFields++
            collectColField(fieldRoot, seenNodes, rawEdges, seenEdgeKeys)
          }
        }

        if (!seenNodes.size) {
          const msg = results[0]?.message ?? 'No hay linaje de columna disponible para este dataset.'
          throw new Error(msg)
        }

        const { nodes: allNodes, edges: allEdges } = layoutColGraph(seenNodes, rawEdges)
        setColNodes(allNodes)
        setColEdges(allEdges)
        setColInfo({ fields: totalFields, datasets: new Set([...seenNodes.keys()].map(k => k.split('::')[0])).size })
        setColActive(true)
      })
      .catch((e: Error) => setColError(e.message))
      .finally(() => setColLoading(false))
  }, [colTable, colColumn, colNamespace])

  const handleColClear = useCallback(() => {
    setColActive(false)
    setColError(null)
    setColInfo(null)
    setColNodes([])
    setColEdges([])
    setColNamespace('')
    setColTable('')
    setColColumn('')
    setColumnList([])
  }, [])

  return {
    colNamespace, setColNamespace,
    colTable, setColTable,
    colColumn, setColColumn,
    tableList, columnList,
    tableLoading, columnLoading,
    colLoading, colError, colActive, colInfo,
    colNodes, colEdges, onColNodesChange, onColEdgesChange,
    handleColTrace, handleColClear,
  }
}
