import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  Download,
  FlaskConical,
  History,
  Layers,
  Sparkles,
  Trash2,
  Upload,
} from 'lucide-react'
import api, { downloadWithAuth, getErrorMessage } from '../api/client'
import PageHeader from '../components/PageHeader'
import Badge, { statusTone } from '../components/Badge'
import { EmptyState, ErrorMessage, InlineNotice, LoadingSpinner } from '../components/Feedback'
import { formatDate, formatMetric, formatNumber, titleCase } from '../utils/format'

const CLASSIFICATION_METRICS = [
  ['accuracy', 'Accuracy'],
  ['precision', 'Precision (weighted)'],
  ['recall', 'Recall (weighted)'],
  ['f1_score', 'F1 score (weighted)'],
  ['roc_auc', 'ROC AUC'],
  ['cv_mean', 'CV mean'],
  ['cv_std', 'CV std'],
]

const REGRESSION_METRICS = [
  ['r2_score', 'R²'],
  ['mae', 'MAE'],
  ['mse', 'MSE'],
  ['rmse', 'RMSE'],
  ['cv_mean', 'CV mean'],
  ['cv_std', 'CV std'],
]

function metricColumns(problemType) {
  return problemType === 'classification' ? CLASSIFICATION_METRICS : REGRESSION_METRICS
}

function ProbabilityBars({ probability }) {
  if (!probability || Object.keys(probability).length === 0) return null
  const entries = Object.entries(probability).sort((a, b) => b[1] - a[1])
  return (
    <div className="space-y-2">
      {entries.map(([label, value]) => (
        <div key={label}>
          <div className="flex items-center justify-between text-xs text-slate-600">
            <span className="font-medium">{label}</span>
            <span>{(Number(value) * 100).toFixed(1)}%</span>
          </div>
          <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-brand-600"
              style={{ width: `${Math.max(0, Math.min(Number(value) * 100, 100))}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

export default function ModelDetails() {
  const { modelId } = useParams()
  const navigate = useNavigate()

  const [model, setModel] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [formValues, setFormValues] = useState({})
  const [predicting, setPredicting] = useState(false)
  const [predictionError, setPredictionError] = useState('')
  const [prediction, setPrediction] = useState(null)

  const [batchResult, setBatchResult] = useState(null)
  const [batchError, setBatchError] = useState('')
  const [batchUploading, setBatchUploading] = useState(false)
  const batchInputRef = useRef(null)

  const [history, setHistory] = useState([])
  const [historyError, setHistoryError] = useState('')
  const [historyLoading, setHistoryLoading] = useState(true)
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await api.get(`/models/${modelId}`)
      setModel(response.data)
    } catch (err) {
      setError(getErrorMessage(err, 'Unable to load this model'))
    } finally {
      setLoading(false)
    }
  }, [modelId])

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true)
    setHistoryError('')
    try {
      const response = await api.get(`/models/${modelId}/predictions`, {
        params: { limit: 25 },
      })
      setHistory(response.data)
    } catch (err) {
      setHistoryError(getErrorMessage(err, 'Unable to load prediction history'))
    } finally {
      setHistoryLoading(false)
    }
  }, [modelId])

  useEffect(() => {
    load()
    loadHistory()
  }, [load, loadHistory])

  useEffect(() => {
    if (!model?.feature_schema) return
    const initial = {}
    model.feature_schema.forEach((feature) => {
      initial[feature.name] = ''
    })
    setFormValues(initial)
  }, [model])

  const metricRows = useMemo(() => {
    if (!model) return []
    return metricColumns(model.problem_type).map(([key, label]) => ({
      key,
      label,
      value: model.metrics?.[key],
    }))
  }, [model])

  const handleValueChange = (name, value) => {
    setFormValues((current) => ({ ...current, [name]: value }))
  }

  const buildPayload = () => {
    const data = {}
    for (const feature of model.feature_schema) {
      const raw = formValues[feature.name]
      if (feature.type === 'numeric') {
        if (raw === '' || raw === undefined) {
          data[feature.name] = null
        } else {
          const numeric = Number(raw)
          if (Number.isNaN(numeric)) {
            throw new Error(`“${feature.name}” must be a number`)
          }
          data[feature.name] = numeric
        }
      } else {
        data[feature.name] = raw === '' || raw === undefined ? null : raw
      }
    }
    return data
  }

  const handlePredict = async (event) => {
    event.preventDefault()
    setPredictionError('')
    setPrediction(null)
    let payload
    try {
      payload = buildPayload()
    } catch (err) {
      setPredictionError(err.message)
      return
    }

    setPredicting(true)
    try {
      const response = await api.post(`/models/${model.id}/predict`, { data: payload })
      setPrediction(response.data)
      loadHistory()
    } catch (err) {
      setPredictionError(getErrorMessage(err, 'Prediction failed'))
    } finally {
      setPredicting(false)
    }
  }

  const handleBatch = async (event) => {
    event.preventDefault()
    const file = batchInputRef.current?.files?.[0]
    setBatchError('')
    setBatchResult(null)
    if (!file) {
      setBatchError('Choose a CSV file to score')
      return
    }
    const formData = new FormData()
    formData.append('file', file)
    setBatchUploading(true)
    try {
      const response = await api.post(`/models/${model.id}/predict/batch`, formData, {
        timeout: 180000,
      })
      setBatchResult(response.data)
      loadHistory()
    } catch (err) {
      setBatchError(getErrorMessage(err, 'Batch prediction failed'))
    } finally {
      setBatchUploading(false)
    }
  }

  const handleDownload = async () => {
    try {
      await downloadWithAuth(
        `/models/${model.id}/download`,
        `${model.target_column}_${model.algorithm_name}_${model.id}.joblib`,
      )
    } catch (err) {
      setError(getErrorMessage(err, 'Download failed'))
    }
  }

  const handleDelete = async () => {
    const confirmed = window.confirm(
      `Delete model “${model.algorithm_label || model.algorithm_name}”? Its prediction history will also be removed.`,
    )
    if (!confirmed) return
    setDeleting(true)
    try {
      await api.delete(`/models/${model.id}`)
      navigate('/models', { replace: true })
    } catch (err) {
      setError(getErrorMessage(err, 'Unable to delete model'))
      setDeleting(false)
    }
  }

  if (loading) {
    return <LoadingSpinner label="Loading model…" />
  }

  if (!model) {
    return (
      <div>
        <PageHeader title="Model unavailable" />
        <ErrorMessage message={error || 'Model not found'} onRetry={load} />
        <Link to="/models" className="btn-secondary mt-4">
          <ArrowLeft className="h-4 w-4" />
          Back to models
        </Link>
      </div>
    )
  }

  const isClassification = model.problem_type === 'classification'
  const confusion = model.metrics?.confusion_matrix
  const classLabels = model.metrics?.class_labels || []
  const artifactAvailable = model.artifact_available && model.feature_schema.length > 0

  return (
    <div>
      <PageHeader
        eyebrow="Model"
        title={model.algorithm_label || titleCase(model.algorithm_name)}
        description={`Predicting “${model.target_column}” from ${model.dataset_name} · ${
          isClassification ? 'classification' : 'regression'
        }`}
        actions={
          <>
            <Link to="/models" className="btn-secondary">
              <ArrowLeft className="h-4 w-4" />
              Leaderboard
            </Link>
            <button
              type="button"
              className="btn-secondary"
              onClick={handleDownload}
              disabled={!model.artifact_available}
            >
              <Download className="h-4 w-4" />
              Download
            </button>
            <button type="button" className="btn-danger" onClick={handleDelete} disabled={deleting}>
              <Trash2 className="h-4 w-4" />
              {deleting ? 'Deleting…' : 'Delete'}
            </button>
          </>
        }
      />

      <ErrorMessage message={error} onRetry={load} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="card p-5">
          <p className="text-sm font-medium text-slate-500">Status</p>
          <div className="mt-2">
            <Badge tone={statusTone(model.status)}>{titleCase(model.status)}</Badge>
          </div>
          <p className="mt-2 text-xs text-slate-400">Experiment #{model.experiment_id}</p>
        </div>
        <div className="card p-5">
          <p className="text-sm font-medium text-slate-500">Dataset</p>
          <Link
            to={`/datasets/${model.dataset_id}`}
            className="mt-2 block truncate text-base font-bold text-slate-900 hover:text-brand-600"
          >
            {model.dataset_name}
          </Link>
          <p className="mt-1 text-xs text-slate-400">Target: {model.target_column}</p>
        </div>
        <div className="card p-5">
          <p className="text-sm font-medium text-slate-500">Training time</p>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {model.training_duration !== null && model.training_duration !== undefined
              ? `${formatNumber(model.training_duration, 3)}s`
              : '—'}
          </p>
          <p className="mt-1 text-xs text-slate-400">Seed used during training</p>
        </div>
        <div className="card p-5">
          <p className="text-sm font-medium text-slate-500">Artifact</p>
          <p className="mt-2 text-base font-bold text-slate-900">
            {model.artifact_available ? 'Available' : 'Missing'}
          </p>
          <p className="mt-1 text-xs text-slate-400">
            {model.feature_schema.length} input feature
            {model.feature_schema.length === 1 ? '' : 's'}
          </p>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <section className="card lg:col-span-2">
          <div className="flex items-center gap-2 border-b border-slate-200 px-5 py-4">
            <Sparkles className="h-4 w-4 text-brand-600" />
            <h2 className="text-base font-semibold text-slate-900">Evaluation metrics</h2>
          </div>
          <dl className="grid grid-cols-1 gap-4 p-5 sm:grid-cols-2 lg:grid-cols-3">
            {metricRows.map((row) => (
              <div key={row.key} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  {row.label}
                </dt>
                <dd className="mt-1 text-lg font-bold text-slate-900">
                  {formatMetric(row.value)}
                </dd>
              </div>
            ))}
          </dl>
          {confusion && confusion.length > 0 ? (
            <div className="border-t border-slate-200 p-5">
              <h3 className="text-sm font-semibold text-slate-900">Confusion matrix</h3>
              <div className="table-wrap mt-3">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Actual \ Predicted</th>
                      {classLabels.map((label) => (
                        <th key={label} scope="col">
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {confusion.map((row, rowIndex) => (
                      <tr key={`confusion-${rowIndex}`}>
                        <th scope="row" className="text-slate-700">
                          {classLabels[rowIndex] ?? `Class ${rowIndex}`}
                        </th>
                        {row.map((value, columnIndex) => (
                          <td
                            key={`confusion-${rowIndex}-${columnIndex}`}
                            className={
                              rowIndex === columnIndex
                                ? 'font-semibold text-emerald-700'
                                : 'text-slate-600'
                            }
                          >
                            {value}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </section>

        <section className="card p-5">
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-brand-600" />
            <h2 className="text-base font-semibold text-slate-900">Hyperparameters</h2>
          </div>
          <div className="mt-3 space-y-3 text-sm">
            {model.hyperparameters?.label ? (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Label
                </p>
                <p className="mt-0.5 text-slate-700">{model.hyperparameters.label}</p>
              </div>
            ) : null}
            {model.hyperparameters?.class_names?.length > 0 ? (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Classes
                </p>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {model.hyperparameters.class_names.map((label) => (
                    <Badge key={label} tone="info">
                      {label}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}
            {model.hyperparameters?.params ? (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Estimator parameters
                </p>
                <dl className="mt-1 divide-y divide-slate-100 rounded-lg border border-slate-200">
                  {Object.entries(model.hyperparameters.params).map(([key, value]) => (
                    <div key={key} className="flex justify-between gap-3 px-3 py-1.5">
                      <dt className="truncate text-xs text-slate-500">{key}</dt>
                      <dd className="max-w-[55%] truncate text-right text-xs font-medium text-slate-700">
                        {String(value)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            ) : null}
            {model.hyperparameters?.feature_columns?.length > 0 ? (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Features
                </p>
                <p className="mt-1 text-xs text-slate-600">
                  {model.hyperparameters.feature_columns.join(', ')}
                </p>
              </div>
            ) : null}
          </div>
        </section>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="card p-5">
          <div className="flex items-center gap-2">
            <FlaskConical className="h-4 w-4 text-brand-600" />
            <h2 className="text-base font-semibold text-slate-900">Make a prediction</h2>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            Enter a value for each feature. Empty values are imputed using the training data.
          </p>

          {!artifactAvailable ? (
            <div className="mt-4">
              <InlineNotice tone="warning">
                This model has no usable artifact, so it cannot make predictions. Re-run the
                experiment to regenerate it.
              </InlineNotice>
            </div>
          ) : (
            <form onSubmit={handlePredict} className="mt-4 space-y-3" noValidate>
              <ErrorMessage message={predictionError} />
              <div className="max-h-80 space-y-3 overflow-y-auto pr-1">
                {model.feature_schema.map((feature) => (
                  <div key={feature.name}>
                    <label className="label" htmlFor={`feature-${feature.name}`}>
                      {feature.name}
                      <span className="ml-1 text-xs font-normal text-slate-400">
                        {feature.type}
                      </span>
                    </label>
                    {feature.type === 'categorical' ? (
                      <select
                        id={`feature-${feature.name}`}
                        className="input"
                        value={formValues[feature.name] ?? ''}
                        onChange={(event) =>
                          handleValueChange(feature.name, event.target.value)
                        }
                      >
                        <option value="">Missing (impute)</option>
                        {(feature.categories || []).map((category) => (
                          <option key={category} value={category}>
                            {category}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        id={`feature-${feature.name}`}
                        type="number"
                        step="any"
                        className="input"
                        value={formValues[feature.name] ?? ''}
                        onChange={(event) =>
                          handleValueChange(feature.name, event.target.value)
                        }
                        placeholder="Leave empty to impute"
                      />
                    )}
                  </div>
                ))}
              </div>
              <button type="submit" className="btn-primary w-full" disabled={predicting}>
                <Sparkles className="h-4 w-4" />
                {predicting ? 'Predicting…' : 'Predict'}
              </button>
            </form>
          )}

          {prediction ? (
            <div className="mt-4 rounded-xl border border-brand-200 bg-brand-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-brand-700">
                Prediction
              </p>
              <p className="mt-1 text-2xl font-bold text-brand-800">
                {typeof prediction.prediction === 'object'
                  ? JSON.stringify(prediction.prediction)
                  : prediction.prediction}
              </p>
              {prediction.probability ? (
                <div className="mt-3">
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-brand-700">
                    Class probabilities
                  </p>
                  <ProbabilityBars probability={prediction.probability} />
                </div>
              ) : null}
            </div>
          ) : null}
        </section>

        <section className="card p-5">
          <div className="flex items-center gap-2">
            <Upload className="h-4 w-4 text-brand-600" />
            <h2 className="text-base font-semibold text-slate-900">Batch prediction</h2>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            Upload a CSV containing the feature columns. Up to 5,000 rows per file.
          </p>

          <form onSubmit={handleBatch} className="mt-4 space-y-3">
            <ErrorMessage message={batchError} />
            <input
              ref={batchInputRef}
              type="file"
              accept=".csv"
              className="block w-full cursor-pointer rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-brand-50 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-brand-700"
              disabled={!artifactAvailable || batchUploading}
            />
            <button
              type="submit"
              className="btn-secondary w-full"
              disabled={!artifactAvailable || batchUploading}
            >
              <Upload className="h-4 w-4" />
              {batchUploading ? 'Scoring…' : 'Upload and score'}
            </button>
          </form>

          {batchResult ? (
            <div className="mt-4">
              <InlineNotice tone="success">
                Scored {batchResult.row_count} row{batchResult.row_count === 1 ? '' : 's'}.
              </InlineNotice>
              <div className="table-wrap mt-3">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">#</th>
                      <th scope="col">Prediction</th>
                    </tr>
                  </thead>
                  <tbody>
                    {batchResult.predictions.slice(0, 20).map((value, index) => (
                      <tr key={`batch-${index}`}>
                        <td className="text-slate-400">{index + 1}</td>
                        <td className="font-medium text-slate-800">
                          {typeof value === 'object' ? JSON.stringify(value) : value}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {batchResult.predictions.length > 20 ? (
                <p className="mt-2 text-xs text-slate-400">
                  Showing the first 20 of {batchResult.predictions.length} predictions.
                </p>
              ) : null}
            </div>
          ) : null}
        </section>
      </div>

      <section className="card mt-6">
        <div className="flex items-center gap-2 border-b border-slate-200 px-5 py-4">
          <History className="h-4 w-4 text-brand-600" />
          <h2 className="text-base font-semibold text-slate-900">Prediction history</h2>
        </div>
        {historyError ? (
          <div className="p-5">
            <ErrorMessage message={historyError} onRetry={loadHistory} />
          </div>
        ) : historyLoading ? (
          <LoadingSpinner label="Loading prediction history…" />
        ) : history.length === 0 ? (
          <div className="p-5">
            <EmptyState
              icon={History}
              title="No predictions yet"
              description="Single and batch predictions are recorded here."
            />
          </div>
        ) : (
          <div className="table-wrap border-0">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Input</th>
                  <th scope="col">Output</th>
                </tr>
              </thead>
              <tbody>
                {history.map((row) => {
                  const output = row.predicted_output || {}
                  return (
                    <tr key={row.id}>
                      <td>{formatDate(row.created_at)}</td>
                      <td className="max-w-sm whitespace-normal text-xs text-slate-500">
                        {row.input_data?.filename
                          ? `${row.input_data.filename} (${row.input_data.row_count} rows)`
                          : Object.entries(row.input_data || {})
                              .map(([key, value]) => `${key}: ${value ?? '—'}`)
                              .join(', ')}
                      </td>
                      <td className="max-w-sm whitespace-normal text-xs text-slate-600">
                        {output.predictions
                          ? `${output.predictions.length} prediction(s)${
                              output.truncated ? ' (truncated)' : ''
                            }`
                          : `${output.prediction}${
                              output.probability
                                ? ` · ${Object.entries(output.probability)
                                    .map(
                                      ([label, value]) =>
                                        `${label}: ${(Number(value) * 100).toFixed(1)}%`,
                                    )
                                    .join(', ')}`
                                : ''
                            }`}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
