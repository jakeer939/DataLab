import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  BarChart3,
  CheckCircle2,
  Download,
  Eraser,
  Plus,
  Trash2,
  Wand2,
} from 'lucide-react'
import api, { downloadWithAuth, getErrorMessage } from '../api/client'
import PageHeader from '../components/PageHeader'
import Badge, { statusTone } from '../components/Badge'
import ColumnPicker from '../components/ColumnPicker'
import { EmptyState, ErrorMessage, InlineNotice, LoadingSpinner } from '../components/Feedback'
import { formatDate, formatNumber, titleCase } from '../utils/format'

const OPERATIONS = [
  {
    value: 'missing_value_handling',
    label: 'Handle missing values',
    description: 'Impute or drop rows with null values.',
  },
  {
    value: 'remove_duplicates',
    label: 'Remove duplicates',
    description: 'Drop repeated rows.',
  },
  {
    value: 'outlier_handling',
    label: 'Handle outliers',
    description: 'Detect, remove or cap outliers using IQR or Z-score.',
  },
  {
    value: 'encoding',
    label: 'Encode categoricals',
    description: 'One-hot or ordinal encode text columns.',
  },
  {
    value: 'feature_scaling',
    label: 'Scale numeric features',
    description: 'Standardise, min-max or robust-scale numeric columns.',
  },
  {
    value: 'data_type_conversion',
    label: 'Convert data types',
    description: 'Convert columns to numeric, string, category or datetime.',
  },
]

function defaultsFor(operation) {
  if (operation === 'missing_value_handling') return { method: 'mean', fill_value: '' }
  if (operation === 'remove_duplicates') return { strategy: 'remove_all' }
  if (operation === 'outlier_handling')
    return { method: 'iqr', operation_mode: 'detect', iqr_factor: '1.5', z_threshold: '3.0' }
  if (operation === 'encoding') return { method: 'one_hot' }
  if (operation === 'feature_scaling') return { method: 'standard' }
  return { target_type: 'float' }
}

export default function Cleaning() {
  const { datasetId } = useParams()
  const [dataset, setDataset] = useState(null)
  const [versions, setVersions] = useState([])
  const [preview, setPreview] = useState(null)
  const [history, setHistory] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [operation, setOperation] = useState('missing_value_handling')
  const [config, setConfig] = useState(defaultsFor('missing_value_handling'))
  const [columns, setColumns] = useState([])
  const [steps, setSteps] = useState([])
  const [applying, setApplying] = useState(false)

  const loadHistory = useCallback(async () => {
    try {
      const response = await api.get(`/cleaning/${datasetId}/cleaning-history`)
      setHistory(response.data.data)
    } catch {
      setHistory(null)
    }
  }, [datasetId])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [datasetResponse, versionsResponse, previewResponse] = await Promise.all([
        api.get(`/datasets/${datasetId}`),
        api.get(`/datasets/${datasetId}/versions`),
        api.get(`/datasets/${datasetId}/preview`, { params: { limit: 5 } }),
      ])
      setDataset(datasetResponse.data)
      setVersions(versionsResponse.data)
      setPreview(previewResponse.data)
      await loadHistory()
    } catch (err) {
      setError(getErrorMessage(err, 'Unable to load this dataset'))
    } finally {
      setLoading(false)
    }
  }, [datasetId, loadHistory])

  useEffect(() => {
    load()
  }, [load])

  const columnNames = preview?.columns || []

  const numericColumns = useMemo(() => {
    if (!preview?.data_types) return []
    return Object.entries(preview.data_types)
      .filter(([, dtype]) => /int|float|double|decimal/i.test(dtype))
      .map(([column]) => column)
  }, [preview])

  const handleOperationChange = (event) => {
    const next = event.target.value
    setOperation(next)
    setConfig(defaultsFor(next))
    setColumns([])
  }

  const handleConfigChange = (event) => {
    const { name, value } = event.target
    setConfig((current) => ({ ...current, [name]: value }))
  }

  const buildStep = () => {
    const configuration = {}
    let affected = columns
    if (operation === 'missing_value_handling') {
      configuration.method = config.method
      if (config.method === 'constant') {
        if (String(config.fill_value).trim() === '') {
          throw new Error('Enter a fill value for constant imputation')
        }
        configuration.fill_value = config.fill_value
      }
    } else if (operation === 'remove_duplicates') {
      configuration.strategy = config.strategy
      affected = []
    } else if (operation === 'outlier_handling') {
      configuration.method = config.method
      configuration.operation = config.operation_mode
      configuration.iqr_factor = Number(config.iqr_factor) || 1.5
      configuration.z_threshold = Number(config.z_threshold) || 3.0
    } else if (operation === 'encoding') {
      configuration.method = config.method
    } else if (operation === 'feature_scaling') {
      configuration.method = config.method
    } else if (operation === 'data_type_conversion') {
      configuration.target_type = config.target_type
      if (affected.length === 0) {
        throw new Error('Select at least one column to convert')
      }
    }

    return { operation, affected_columns: affected, configuration }
  }

  const handleAddStep = () => {
    setError('')
    setNotice('')
    try {
      const step = buildStep()
      setSteps((current) => [...current, step])
      setColumns([])
      setConfig(defaultsFor(operation))
    } catch (err) {
      setError(err.message)
    }
  }

  const handleApply = async () => {
    if (steps.length === 0) return
    setApplying(true)
    setError('')
    setNotice('')
    try {
      const response = await api.post(`/cleaning/${datasetId}/start`, { operations: steps })
      const result = response.data.data
      setNotice(
        `Cleaning completed. Created version ${result.version_number} with ${formatNumber(
          result.remaining_rows,
          0,
        )} rows and ${result.remaining_columns} columns.`,
      )
      setSteps([])
      await load()
    } catch (err) {
      setError(getErrorMessage(err, 'Cleaning failed'))
    } finally {
      setApplying(false)
    }
  }

  const handleDownload = async () => {
    try {
      await downloadWithAuth(
        `/cleaning/${datasetId}/download`,
        `${dataset?.name || 'dataset'}_cleaned.csv`,
      )
    } catch (err) {
      setError(getErrorMessage(err, 'Download failed'))
    }
  }

  if (loading) {
    return <LoadingSpinner label="Loading dataset…" />
  }

  if (!dataset) {
    return (
      <div>
        <PageHeader title="Cleaning unavailable" />
        <ErrorMessage message={error || 'Dataset not found'} onRetry={load} />
        <Link to="/datasets" className="btn-secondary mt-4">
          <ArrowLeft className="h-4 w-4" />
          Back to datasets
        </Link>
      </div>
    )
  }

  const selectedOperation = OPERATIONS.find((item) => item.value === operation)

  return (
    <div>
      <PageHeader
        eyebrow="Cleaning"
        title={`Clean · ${dataset.name}`}
        description="Build a cleaning recipe, apply it to the latest version, and keep every result as a new dataset version."
        actions={
          <>
            <Link to={`/datasets/${dataset.id}`} className="btn-secondary">
              <ArrowLeft className="h-4 w-4" />
              Dataset
            </Link>
            <Link to={`/datasets/${dataset.id}/analysis`} className="btn-secondary">
              <BarChart3 className="h-4 w-4" />
              Analysis
            </Link>
            <button type="button" className="btn-secondary" onClick={handleDownload}>
              <Download className="h-4 w-4" />
              Download cleaned
            </button>
          </>
        }
      />

      <ErrorMessage message={error} onRetry={load} />
      {notice ? (
        <div className="mb-4">
          <InlineNotice tone="success">{notice}</InlineNotice>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <section className="card p-5 lg:col-span-2">
          <div className="flex items-center gap-2">
            <Wand2 className="h-4 w-4 text-brand-600" />
            <h2 className="text-base font-semibold text-slate-900">Add a cleaning step</h2>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            Steps run in order against the latest dataset version.
          </p>

          <div className="mt-4 space-y-4">
            <div>
              <label className="label" htmlFor="operation">
                Operation
              </label>
              <select
                id="operation"
                className="input"
                value={operation}
                onChange={handleOperationChange}
              >
                {OPERATIONS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
              {selectedOperation ? (
                <p className="mt-1 text-xs text-slate-400">{selectedOperation.description}</p>
              ) : null}
            </div>

            {operation === 'missing_value_handling' ? (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="label" htmlFor="missing-method">
                    Method
                  </label>
                  <select
                    id="missing-method"
                    name="method"
                    className="input"
                    value={config.method}
                    onChange={handleConfigChange}
                  >
                    <option value="mean">Mean (numeric)</option>
                    <option value="median">Median (numeric)</option>
                    <option value="mode">Most frequent</option>
                    <option value="constant">Constant value</option>
                    <option value="drop">Drop rows</option>
                  </select>
                </div>
                {config.method === 'constant' ? (
                  <div>
                    <label className="label" htmlFor="fill-value">
                      Fill value
                    </label>
                    <input
                      id="fill-value"
                      name="fill_value"
                      className="input"
                      value={config.fill_value}
                      onChange={handleConfigChange}
                      placeholder="e.g. 0 or Unknown"
                    />
                  </div>
                ) : null}
              </div>
            ) : null}

            {operation === 'remove_duplicates' ? (
              <div>
                <label className="label" htmlFor="duplicate-strategy">
                  Strategy
                </label>
                <select
                  id="duplicate-strategy"
                  name="strategy"
                  className="input"
                  value={config.strategy}
                  onChange={handleConfigChange}
                >
                  <option value="remove_all">Remove every duplicate</option>
                  <option value="keep_first">Keep first occurrence</option>
                  <option value="keep_last">Keep last occurrence</option>
                </select>
              </div>
            ) : null}

            {operation === 'outlier_handling' ? (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="label" htmlFor="outlier-method">
                    Detection method
                  </label>
                  <select
                    id="outlier-method"
                    name="method"
                    className="input"
                    value={config.method}
                    onChange={handleConfigChange}
                  >
                    <option value="iqr">IQR</option>
                    <option value="z_score">Z-score</option>
                  </select>
                </div>
                <div>
                  <label className="label" htmlFor="outlier-mode">
                    Action
                  </label>
                  <select
                    id="outlier-mode"
                    name="operation_mode"
                    className="input"
                    value={config.operation_mode}
                    onChange={handleConfigChange}
                  >
                    <option value="detect">Detect only</option>
                    <option value="remove">Remove rows</option>
                    <option value="cap">Cap values</option>
                  </select>
                </div>
                {config.method === 'iqr' ? (
                  <div>
                    <label className="label" htmlFor="iqr-factor">
                      IQR factor
                    </label>
                    <input
                      id="iqr-factor"
                      name="iqr_factor"
                      type="number"
                      step="0.1"
                      min="0.1"
                      className="input"
                      value={config.iqr_factor}
                      onChange={handleConfigChange}
                    />
                  </div>
                ) : (
                  <div>
                    <label className="label" htmlFor="z-threshold">
                      Z threshold
                    </label>
                    <input
                      id="z-threshold"
                      name="z_threshold"
                      type="number"
                      step="0.1"
                      min="0.1"
                      className="input"
                      value={config.z_threshold}
                      onChange={handleConfigChange}
                    />
                  </div>
                )}
              </div>
            ) : null}

            {operation === 'encoding' ? (
              <div>
                <label className="label" htmlFor="encoding-method">
                  Encoding
                </label>
                <select
                  id="encoding-method"
                  name="method"
                  className="input"
                  value={config.method}
                  onChange={handleConfigChange}
                >
                  <option value="one_hot">One-hot</option>
                  <option value="ordinal">Ordinal</option>
                </select>
              </div>
            ) : null}

            {operation === 'feature_scaling' ? (
              <div>
                <label className="label" htmlFor="scaling-method">
                  Scaling
                </label>
                <select
                  id="scaling-method"
                  name="method"
                  className="input"
                  value={config.method}
                  onChange={handleConfigChange}
                >
                  <option value="standard">Standard (z-score)</option>
                  <option value="minmax">Min–max</option>
                  <option value="robust">Robust</option>
                </select>
              </div>
            ) : null}

            {operation === 'data_type_conversion' ? (
              <div>
                <label className="label" htmlFor="target-type">
                  Target type
                </label>
                <select
                  id="target-type"
                  name="target_type"
                  className="input"
                  value={config.target_type}
                  onChange={handleConfigChange}
                >
                  <option value="float">Float</option>
                  <option value="integer">Integer</option>
                  <option value="string">String</option>
                  <option value="categorical">Category</option>
                  <option value="datetime">Datetime</option>
                </select>
              </div>
            ) : null}

            {operation !== 'remove_duplicates' ? (
              <ColumnPicker
                columns={
                  operation === 'outlier_handling' || operation === 'feature_scaling'
                    ? numericColumns
                    : columnNames
                }
                selected={columns}
                onChange={setColumns}
                hint={
                  columns.length === 0
                    ? 'Leave empty to apply to all applicable columns.'
                    : undefined
                }
              />
            ) : null}

            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn-primary" onClick={handleAddStep}>
                <Plus className="h-4 w-4" />
                Add step
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  setColumns([])
                  setConfig(defaultsFor(operation))
                }}
              >
                Reset
              </button>
            </div>
          </div>
        </section>

        <aside className="space-y-4">
          <div className="card p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-slate-900">Recipe</h2>
              <Badge tone={steps.length > 0 ? 'info' : 'neutral'}>
                {steps.length} step{steps.length === 1 ? '' : 's'}
              </Badge>
            </div>
            {steps.length === 0 ? (
              <p className="mt-3 text-sm text-slate-500">
                No steps yet. Configure an operation and add it to the recipe.
              </p>
            ) : (
              <ol className="mt-3 space-y-2">
                {steps.map((step, index) => (
                  <li
                    key={`${step.operation}-${index}`}
                    className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-slate-800">
                          {index + 1}. {titleCase(step.operation)}
                        </p>
                        <p className="text-xs text-slate-500">
                          {step.affected_columns.length > 0
                            ? step.affected_columns.join(', ')
                            : 'All applicable columns'}
                        </p>
                        <p className="mt-0.5 text-xs text-slate-400">
                          {Object.entries(step.configuration)
                            .map(([key, value]) => `${titleCase(key)}: ${value}`)
                            .join(' · ')}
                        </p>
                      </div>
                      <button
                        type="button"
                        className="rounded p-1 text-slate-400 hover:bg-white hover:text-red-600"
                        aria-label={`Remove step ${index + 1}`}
                        onClick={() =>
                          setSteps((current) => current.filter((_, i) => i !== index))
                        }
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </li>
                ))}
              </ol>
            )}
            <button
              type="button"
              className="btn-primary mt-4 w-full"
              onClick={handleApply}
              disabled={steps.length === 0 || applying}
            >
              <CheckCircle2 className="h-4 w-4" />
              {applying ? 'Applying…' : 'Apply cleaning'}
            </button>
            <p className="mt-2 text-xs text-slate-400">
              Applying creates a new cleaned version. The original upload is never modified.
            </p>
          </div>

          <div className="card p-5">
            <h2 className="text-base font-semibold text-slate-900">Current data</h2>
            <dl className="mt-3 space-y-2 text-sm">
              <div className="flex justify-between gap-3">
                <dt className="text-slate-500">Rows</dt>
                <dd className="font-semibold text-slate-800">
                  {formatNumber(dataset.row_count, 0)}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-slate-500">Columns</dt>
                <dd className="font-semibold text-slate-800">{dataset.column_count}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-slate-500">Versions</dt>
                <dd className="font-semibold text-slate-800">{versions.length}</dd>
              </div>
            </dl>
          </div>
        </aside>
      </div>

      <section className="card mt-6">
        <div className="flex items-center gap-2 border-b border-slate-200 px-5 py-4">
          <Eraser className="h-4 w-4 text-brand-600" />
          <h2 className="text-base font-semibold text-slate-900">Cleaning history</h2>
        </div>
        {!history || history.cleaning_history.length === 0 ? (
          <div className="p-5">
            <EmptyState
              icon={Eraser}
              title="No cleaning runs yet"
              description="Applied recipes will appear here with their row and column counts."
            />
          </div>
        ) : (
          <div className="table-wrap border-0">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Version</th>
                  <th scope="col">Operations</th>
                  <th scope="col">Rows</th>
                  <th scope="col">Columns</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {history.cleaning_history.map((job) => (
                  <tr key={job.job_id}>
                    <td>{formatDate(job.created_at)}</td>
                    <td>
                      {(() => {
                        const version = (history.versions || []).find(
                          (item) => item.id === job.version_id,
                        )
                        return version ? `v${version.version_number}` : `#${job.version_id}`
                      })()}
                    </td>
                    <td className="max-w-md whitespace-normal text-xs">
                      {(job.configuration?.operations || [])
                        .map((step) => titleCase(step.operation))
                        .join(' → ') || '—'}
                    </td>
                    <td>
                      {formatNumber(job.summary?.rows_before, 0)} →{' '}
                      {formatNumber(job.summary?.rows_after, 0)}
                    </td>
                    <td>
                      {job.summary?.columns_before ?? '—'} → {job.summary?.columns_after ?? '—'}
                    </td>
                    <td>
                      <Badge tone={statusTone(job.status)}>{titleCase(job.status)}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
