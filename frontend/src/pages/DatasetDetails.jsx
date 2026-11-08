import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  BarChart3,
  ChevronLeft,
  ChevronRight,
  Download,
  Eraser,
  Layers,
  Table2,
  Trash2,
} from 'lucide-react'
import api, { downloadWithAuth, getErrorMessage } from '../api/client'
import PageHeader from '../components/PageHeader'
import Badge, { statusTone } from '../components/Badge'
import { ErrorMessage, InlineNotice, LoadingSpinner } from '../components/Feedback'
import { formatDate, formatNumber, titleCase } from '../utils/format'

const PAGE_SIZE = 25

export default function DatasetDetails() {
  const { datasetId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()

  const [dataset, setDataset] = useState(null)
  const [versions, setVersions] = useState([])
  const [preview, setPreview] = useState(null)
  const [versionId, setVersionId] = useState('')
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [error, setError] = useState('')
  const [previewError, setPreviewError] = useState('')
  const [notice, setNotice] = useState(
    location.state?.uploaded ? 'Dataset uploaded successfully.' : '',
  )
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [datasetResponse, versionsResponse] = await Promise.all([
        api.get(`/datasets/${datasetId}`),
        api.get(`/datasets/${datasetId}/versions`),
      ])
      setDataset(datasetResponse.data)
      setVersions(versionsResponse.data)
    } catch (err) {
      setError(getErrorMessage(err, 'Unable to load this dataset'))
    } finally {
      setLoading(false)
    }
  }, [datasetId])

  const loadPreview = useCallback(async () => {
    setPreviewLoading(true)
    setPreviewError('')
    try {
      const params = { offset, limit: PAGE_SIZE }
      if (versionId) params.version_id = versionId
      const response = await api.get(`/datasets/${datasetId}/preview`, { params })
      setPreview(response.data)
    } catch (err) {
      setPreviewError(getErrorMessage(err, 'Unable to load the preview'))
    } finally {
      setPreviewLoading(false)
    }
  }, [datasetId, offset, versionId])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    loadPreview()
  }, [loadPreview])

  const latestVersion = useMemo(
    () => versions.reduce((latest, item) => (item.version_number > (latest?.version_number ?? -1) ? item : latest), null),
    [versions],
  )

  const activeVersion = useMemo(
    () =>
      versionId
        ? versions.find((item) => String(item.id) === String(versionId))
        : latestVersion,
    [versionId, versions, latestVersion],
  )

  const handleVersionChange = (event) => {
    setVersionId(event.target.value)
    setOffset(0)
  }

  const handleDownload = async () => {
    if (!dataset) return
    try {
      const params = versionId ? `?version_id=${versionId}` : ''
      await downloadWithAuth(
        `/datasets/${dataset.id}/download${params}`,
        `${dataset.name}${activeVersion ? `_v${activeVersion.version_number}` : ''}.${dataset.file_format}`,
      )
    } catch (err) {
      setError(getErrorMessage(err, 'Download failed'))
    }
  }

  const handleDelete = async () => {
    if (!dataset) return
    const confirmed = window.confirm(
      `Delete “${dataset.name}”? This also removes its versions, cleaning jobs, experiments and saved models. This cannot be undone.`,
    )
    if (!confirmed) return
    setDeleting(true)
    setError('')
    try {
      await api.delete(`/datasets/${dataset.id}`)
      navigate('/datasets', { replace: true })
    } catch (err) {
      setError(getErrorMessage(err, 'Unable to delete dataset'))
      setDeleting(false)
    }
  }

  if (loading) {
    return <LoadingSpinner label="Loading dataset…" />
  }

  if (!dataset) {
    return (
      <div>
        <PageHeader title="Dataset unavailable" />
        <ErrorMessage message={error || 'Dataset not found'} onRetry={load} />
        <Link to="/datasets" className="btn-secondary mt-4">
          <ArrowLeft className="h-4 w-4" />
          Back to datasets
        </Link>
      </div>
    )
  }

  const totalRows = preview?.row_count ?? dataset.row_count
  const pageStart = totalRows === 0 ? 0 : offset + 1
  const pageEnd = Math.min(offset + PAGE_SIZE, totalRows)
  const canGoPrevious = offset > 0
  const canGoNext = offset + PAGE_SIZE < totalRows

  return (
    <div>
      <PageHeader
        eyebrow="Dataset"
        title={dataset.name}
        description={`${dataset.original_filename} · uploaded ${formatDate(dataset.created_at)}`}
        actions={
          <>
            <button type="button" className="btn-secondary" onClick={handleDownload}>
              <Download className="h-4 w-4" />
              Download
            </button>
            <Link to={`/datasets/${dataset.id}/analysis`} className="btn-secondary">
              <BarChart3 className="h-4 w-4" />
              Analysis
            </Link>
            <Link to={`/datasets/${dataset.id}/cleaning`} className="btn-primary">
              <Eraser className="h-4 w-4" />
              Clean data
            </Link>
          </>
        }
      />

      <ErrorMessage message={error} onRetry={load} />
      {notice ? (
        <div className="mb-4">
          <InlineNotice tone="success">{notice}</InlineNotice>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="card p-5">
          <p className="text-sm font-medium text-slate-500">Rows</p>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {formatNumber(dataset.row_count, 0)}
          </p>
        </div>
        <div className="card p-5">
          <p className="text-sm font-medium text-slate-500">Columns</p>
          <p className="mt-2 text-2xl font-bold text-slate-900">{dataset.column_count}</p>
        </div>
        <div className="card p-5">
          <p className="text-sm font-medium text-slate-500">Versions</p>
          <p className="mt-2 text-2xl font-bold text-slate-900">{versions.length}</p>
        </div>
        <div className="card p-5">
          <p className="text-sm font-medium text-slate-500">Status</p>
          <div className="mt-2">
            <Badge tone={statusTone(dataset.status)}>{titleCase(dataset.status)}</Badge>
          </div>
          <p className="mt-2 text-xs uppercase tracking-wide text-slate-400">
            {dataset.file_format} · {dataset.version_count} version
            {dataset.version_count === 1 ? '' : 's'}
          </p>
        </div>
      </div>

      <section className="card mt-6">
        <div className="flex flex-col gap-3 border-b border-slate-200 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <Table2 className="h-4 w-4 text-brand-600" />
            <h2 className="text-base font-semibold text-slate-900">Data preview</h2>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <label htmlFor="version-select" className="sr-only">
              Dataset version
            </label>
            <select
              id="version-select"
              className="input sm:w-64"
              value={versionId}
              onChange={handleVersionChange}
            >
              <option value="">
                Latest{latestVersion ? ` (v${latestVersion.version_number})` : ''}
              </option>
              {versions.map((version) => (
                <option key={version.id} value={version.id}>
                  v{version.version_number} · {titleCase(version.version_type)}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="px-5 py-4">
          {previewError ? <ErrorMessage message={previewError} onRetry={loadPreview} /> : null}

          {previewLoading && !preview ? (
            <LoadingSpinner label="Loading preview…" />
          ) : preview && preview.columns.length > 0 ? (
            <>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col" className="w-12">
                        #
                      </th>
                      {preview.columns.map((column) => (
                        <th key={column} scope="col">
                          <span className="block text-slate-700">{column}</span>
                          <span className="block font-normal normal-case tracking-normal text-slate-400">
                            {preview.data_types?.[column]}
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.first_rows.map((row, rowIndex) => (
                      <tr key={`row-${offset + rowIndex}`}>
                        <td className="text-slate-400">{offset + rowIndex + 1}</td>
                        {row.map((cell, cellIndex) => (
                          <td key={`cell-${offset + rowIndex}-${cellIndex}`} className="max-w-xs truncate">
                            {cell === null || cell === undefined || cell === '' ? (
                              <span className="text-slate-300">—</span>
                            ) : (
                              String(cell)
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-sm text-slate-500">
                  Showing {pageStart.toLocaleString()}–{pageEnd.toLocaleString()} of{' '}
                  {totalRows.toLocaleString()} rows
                  {activeVersion ? ` · version ${activeVersion.version_number}` : ''}
                </p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className="btn-secondary !py-1.5"
                    onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
                    disabled={!canGoPrevious || previewLoading}
                  >
                    <ChevronLeft className="h-4 w-4" />
                    Previous
                  </button>
                  <button
                    type="button"
                    className="btn-secondary !py-1.5"
                    onClick={() => setOffset((current) => current + PAGE_SIZE)}
                    disabled={!canGoNext || previewLoading}
                  >
                    Next
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </>
          ) : (
            <p className="py-8 text-center text-sm text-slate-500">
              This dataset has no rows to preview.
            </p>
          )}
        </div>
      </section>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <section className="card lg:col-span-2">
          <div className="flex items-center gap-2 border-b border-slate-200 px-5 py-4">
            <Layers className="h-4 w-4 text-brand-600" />
            <h2 className="text-base font-semibold text-slate-900">Versions</h2>
          </div>
          <div className="table-wrap border-0">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Version</th>
                  <th scope="col">Type</th>
                  <th scope="col">Parent</th>
                  <th scope="col">Created</th>
                  <th scope="col" className="text-right">
                    Preview
                  </th>
                </tr>
              </thead>
              <tbody>
                {versions.map((version) => (
                  <tr key={version.id}>
                    <td className="font-semibold text-slate-800">v{version.version_number}</td>
                    <td>
                      <Badge tone={version.version_type === 'original' ? 'neutral' : 'info'}>
                        {titleCase(version.version_type)}
                      </Badge>
                    </td>
                    <td>{version.parent_version_id ? `#${version.parent_version_id}` : '—'}</td>
                    <td>{formatDate(version.created_at)}</td>
                    <td className="text-right">
                      <button
                        type="button"
                        className="btn-secondary !py-1.5"
                        onClick={() => {
                          setVersionId(String(version.id))
                          setOffset(0)
                        }}
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <aside className="space-y-4">
          <div className="card p-5">
            <h2 className="text-sm font-semibold text-slate-900">Next steps</h2>
            <div className="mt-3 space-y-2">
              <Link
                to={`/datasets/${dataset.id}/analysis`}
                className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                <span className="inline-flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-brand-600" />
                  Explore analysis
                </span>
                <ChevronRight className="h-4 w-4 text-slate-400" />
              </Link>
              <Link
                to={`/datasets/${dataset.id}/cleaning`}
                className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                <span className="inline-flex items-center gap-2">
                  <Eraser className="h-4 w-4 text-brand-600" />
                  Clean data
                </span>
                <ChevronRight className="h-4 w-4 text-slate-400" />
              </Link>
              <Link
                to="/experiments"
                className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                <span className="inline-flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-brand-600" />
                  Train a model
                </span>
                <ChevronRight className="h-4 w-4 text-slate-400" />
              </Link>
            </div>
          </div>

          <div className="card border-red-200 p-5">
            <h2 className="text-sm font-semibold text-red-700">Danger zone</h2>
            <p className="mt-1 text-xs text-slate-500">
              Deleting this dataset also deletes its versions, cleaning jobs, experiments and
              models.
            </p>
            <button
              type="button"
              className="btn-danger mt-3 w-full"
              onClick={handleDelete}
              disabled={deleting}
            >
              <Trash2 className="h-4 w-4" />
              {deleting ? 'Deleting…' : 'Delete dataset'}
            </button>
          </div>
        </aside>
      </div>
    </div>
  )
}
