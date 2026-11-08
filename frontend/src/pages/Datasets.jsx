import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Database, Search, Trash2, Upload } from 'lucide-react'
import api, { getErrorMessage } from '../api/client'
import PageHeader from '../components/PageHeader'
import Badge, { statusTone } from '../components/Badge'
import { EmptyState, ErrorMessage, LoadingSpinner, InlineNotice } from '../components/Feedback'
import { formatDate, formatNumber, titleCase } from '../utils/format'

export default function Datasets() {
  const navigate = useNavigate()
  const [datasets, setDatasets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [search, setSearch] = useState('')
  const [deletingId, setDeletingId] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await api.get('/datasets/')
      setDatasets(response.data)
    } catch (err) {
      setError(getErrorMessage(err, 'Unable to load datasets'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return datasets
    return datasets.filter(
      (dataset) =>
        dataset.name.toLowerCase().includes(term) ||
        dataset.original_filename.toLowerCase().includes(term),
    )
  }, [datasets, search])

  const handleDelete = async (dataset) => {
    const confirmed = window.confirm(
      `Delete “${dataset.name}”? This also removes its versions, cleaning jobs, experiments and saved models. This cannot be undone.`,
    )
    if (!confirmed) return
    setDeletingId(dataset.id)
    setError('')
    setNotice('')
    try {
      await api.delete(`/datasets/${dataset.id}`)
      setDatasets((current) => current.filter((item) => item.id !== dataset.id))
      setNotice(`Deleted “${dataset.name}”.`)
    } catch (err) {
      setError(getErrorMessage(err, 'Unable to delete dataset'))
    } finally {
      setDeletingId(null)
    }
  }

  if (loading) {
    return <LoadingSpinner label="Loading datasets…" />
  }

  return (
    <div>
      <PageHeader
        eyebrow="Data"
        title="Datasets"
        description="Every upload is versioned. Open a dataset to preview it, run profiling, or apply cleaning steps."
        actions={
          <button type="button" className="btn-primary" onClick={() => navigate('/datasets/upload')}>
            <Upload className="h-4 w-4" />
            Upload dataset
          </button>
        }
      />

      <ErrorMessage message={error} onRetry={load} />
      {notice ? (
        <div className="mb-4">
          <InlineNotice tone="success">{notice}</InlineNotice>
        </div>
      ) : null}

      {datasets.length === 0 ? (
        <EmptyState
          icon={Database}
          title="No datasets uploaded"
          description="Upload a CSV or Excel file to start exploring your data."
          action={
            <Link to="/datasets/upload" className="btn-primary">
              <Upload className="h-4 w-4" />
              Upload dataset
            </Link>
          }
        />
      ) : (
        <>
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative w-full sm:max-w-xs">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                type="search"
                className="input pl-9"
                placeholder="Search datasets…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                aria-label="Search datasets"
              />
            </div>
            <p className="text-sm text-slate-500">
              {filtered.length} of {datasets.length} dataset{datasets.length === 1 ? '' : 's'}
            </p>
          </div>

          {filtered.length === 0 ? (
            <EmptyState
              icon={Search}
              title="No matching datasets"
              description="Try a different search term."
            />
          ) : (
            <div className="table-wrap bg-white">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Dataset</th>
                    <th scope="col">Format</th>
                    <th scope="col">Rows</th>
                    <th scope="col">Columns</th>
                    <th scope="col">Versions</th>
                    <th scope="col">Status</th>
                    <th scope="col">Uploaded</th>
                    <th scope="col" className="text-right">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((dataset) => (
                    <tr key={dataset.id}>
                      <td>
                        <Link
                          to={`/datasets/${dataset.id}`}
                          className="font-semibold text-slate-800 hover:text-brand-600"
                        >
                          {dataset.name}
                        </Link>
                        <p className="text-xs text-slate-400">{dataset.original_filename}</p>
                      </td>
                      <td className="uppercase">{dataset.file_format}</td>
                      <td>{formatNumber(dataset.row_count, 0)}</td>
                      <td>{dataset.column_count}</td>
                      <td>{dataset.version_count}</td>
                      <td>
                        <Badge tone={statusTone(dataset.status)}>
                          {titleCase(dataset.status)}
                        </Badge>
                      </td>
                      <td>{formatDate(dataset.created_at)}</td>
                      <td>
                        <div className="flex items-center justify-end gap-2">
                          <Link to={`/datasets/${dataset.id}`} className="btn-secondary !py-1.5">
                            Open
                          </Link>
                          <button
                            type="button"
                            className="btn-danger !px-2.5 !py-1.5"
                            aria-label={`Delete ${dataset.name}`}
                            disabled={deletingId === dataset.id}
                            onClick={() => handleDelete(dataset)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
