import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowRight,
  FlaskConical,
  Play,
  Trash2,
  Trophy,
} from 'lucide-react'
import api, { getErrorMessage } from '../api/client'
import PageHeader from '../components/PageHeader'
import Badge, { statusTone } from '../components/Badge'
import ColumnPicker from '../components/ColumnPicker'
import { EmptyState, ErrorMessage, InlineNotice, LoadingSpinner } from '../components/Feedback'
import { formatDate, formatMetric, formatNumber, titleCase } from '../utils/format'

const CLASSIFICATION_METRICS = [
  ['accuracy', 'Accuracy'],
  ['precision', 'Precision'],
  ['recall', 'Recall'],
  ['f1_score', 'F1 score'],
  ['roc_auc', 'ROC AUC'],
  ['cv_mean', 'CV mean'],
]

const REGRESSION_METRICS = [
  ['r2_score', 'R²'],
  ['mae', 'MAE'],
  ['mse', 'MSE'],
  ['rmse', 'RMSE'],
  ['cv_mean', 'CV mean'],
]

const DEFAULT_ALGORITHMS = {
  classification: ['logistic_regression', 'decision_tree', 'random_forest'],
  regression: ['linear_regression', 'decision_tree', 'random_forest'],
}

function metricColumns(problemType) {
  return problemType === 'classification' ? CLASSIFICATION_METRICS : REGRESSION_METRICS
}

function ResultsTable({ experiment }) {
  const columns = metricColumns(experiment.problem_type)
  const results = experiment.results || []
  if (results.length === 0) {
    return (
      <p className="px-5 py-6 text-sm text-slate-500">
        No algorithm results were recorded for this experiment.
      </p>
    )
  }
  return (
    <div className="table-wrap border-0">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Algorithm</th>
            <th scope="col">Status</th>
            {columns.map(([key, label]) => (
              <th key={key} scope="col">
                {label}
              </th>
            ))}
            <th scope="col">Train time</th>
            <th scope="col" className="text-right">
              Model
            </th>
          </tr>
        </thead>
        <tbody>
          {results.map((result) => {
            const recommended = result.model_id === experiment.recommended_model_id
            return (
              <tr key={result.model_id || result.algorithm}>
                <td>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-800">
                      {result.algorithm_label || titleCase(result.algorithm)}
                    </span>
                    {recommended ? <Badge tone="success">Recommended</Badge> : null}
                  </div>
                  {result.error ? (
                    <p className="mt-0.5 max-w-xs whitespace-normal text-xs text-red-600">
                      {result.error}
                    </p>
                  ) : null}
                </td>
                <td>
                  <Badge tone={statusTone(result.status)}>{titleCase(result.status)}</Badge>
                </td>
                {columns.map(([key]) => (
                  <td key={key}>{formatMetric(result.metrics?.[key])}</td>
                ))}
                <td>
                  {result.training_duration !== null && result.training_duration !== undefined
                    ? `${formatNumber(result.training_duration, 3)}s`
                    : '—'}
                </td>
                <td className="text-right">
                  {result.model_id && result.status === 'completed' ? (
                    <Link to={`/models/${result.model_id}`} className="btn-secondary !py-1.5">
                      View
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  ) : (
                    <span className="text-slate-300">—</span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default function Experiments() {
  const { experimentId } = useParams()
  const navigate = useNavigate()

  const [experiments, setExperiments] = useState([])
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState('')
  const [notice, setNotice] = useState('')

  const [datasets, setDatasets] = useState([])
  const [datasetsLoading, setDatasetsLoading] = useState(true)
  const [datasetId, setDatasetId] = useState('')
  const [columns, setColumns] = useState([])
  const [columnsLoading, setColumnsLoading] = useState(false)
  const [targetColumn, setTargetColumn] = useState('')
  const [problemType, setProblemType] = useState('auto')
  const [selectedFeatures, setSelectedFeatures] = useState([])
  const [testSize, setTestSize] = useState('0.2')
  const [randomSeed, setRandomSeed] = useState('42')
  const [crossValidation, setCrossValidation] = useState(false)
  const [algorithms, setAlgorithms] = useState([])
  const [catalog, setCatalog] = useState({ classification: [], regression: [], labels: {} })
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState('')

  const [experiment, setExperiment] = useState(null)
  const [detailLoading, setDetailLoading] = useState(Boolean(experimentId))
  const [detailError, setDetailError] = useState('')

  const loadExperiments = useCallback(async () => {
    setListLoading(true)
    setListError('')
    try {
      const response = await api.get('/experiments/')
      setExperiments(response.data)
    } catch (err) {
      setListError(getErrorMessage(err, 'Unable to load experiments'))
    } finally {
      setListLoading(false)
    }
  }, [])

  const loadDatasets = useCallback(async () => {
    setDatasetsLoading(true)
    try {
      const response = await api.get('/datasets/')
      setDatasets(response.data)
    } catch (err) {
      setListError(getErrorMessage(err, 'Unable to load datasets'))
    } finally {
      setDatasetsLoading(false)
    }
  }, [])

  const loadDetail = useCallback(async () => {
    if (!experimentId) return
    setDetailLoading(true)
    setDetailError('')
    try {
      const response = await api.get(`/experiments/${experimentId}`)
      setExperiment(response.data)
    } catch (err) {
      setDetailError(getErrorMessage(err, 'Unable to load experiment'))
    } finally {
      setDetailLoading(false)
    }
  }, [experimentId])

  useEffect(() => {
    loadExperiments()
    loadDatasets()
    api
      .get('/experiments/algorithms')
      .then((response) => setCatalog(response.data))
      .catch(() => setCatalog({ classification: [], regression: [], labels: {} }))
  }, [loadExperiments, loadDatasets])

  useEffect(() => {
    loadDetail()
  }, [loadDetail])

  useEffect(() => {
    if (!datasetId) {
      setColumns([])
      setTargetColumn('')
      setSelectedFeatures([])
      return undefined
    }
    let active = true
    setColumnsLoading(true)
    api
      .get(`/datasets/${datasetId}/preview`, { params: { limit: 1 } })
      .then((response) => {
        if (!active) return
        setColumns(response.data.columns || [])
        setTargetColumn('')
        setSelectedFeatures([])
      })
      .catch((err) => {
        if (!active) return
        setFormError(getErrorMessage(err, 'Unable to load dataset columns'))
      })
      .finally(() => {
        if (active) setColumnsLoading(false)
      })
    return () => {
      active = false
    }
  }, [datasetId])

  const availableAlgorithms = useMemo(() => {
    if (problemType === 'classification') return catalog.classification
    if (problemType === 'regression') return catalog.regression
    return []
  }, [catalog, problemType])

  const handleProblemTypeChange = (event) => {
    const next = event.target.value
    setProblemType(next)
    setAlgorithms(DEFAULT_ALGORITHMS[next] || [])
  }

  const toggleAlgorithm = (algorithm) => {
    setAlgorithms((current) =>
      current.includes(algorithm)
        ? current.filter((item) => item !== algorithm)
        : [...current, algorithm],
    )
  }

  const featureOptions = columns.filter((column) => column !== targetColumn)

  const handleSubmit = async (event) => {
    event.preventDefault()
    setFormError('')
    if (!datasetId) {
      setFormError('Choose a dataset')
      return
    }
    if (!targetColumn) {
      setFormError('Choose a target column')
      return
    }
    const testSizeNumber = Number(testSize)
    if (Number.isNaN(testSizeNumber) || testSizeNumber < 0.05 || testSizeNumber > 0.5) {
      setFormError('Test size must be between 0.05 and 0.5')
      return
    }
    const seedNumber = Number(randomSeed)
    if (!Number.isInteger(seedNumber)) {
      setFormError('Random seed must be an integer')
      return
    }

    setSubmitting(true)
    try {
      const response = await api.post(
        '/experiments/',
        {
          dataset_id: Number(datasetId),
          target_column: targetColumn,
          problem_type: problemType,
          selected_features: selectedFeatures,
          split_configuration: {
            test_size: testSizeNumber,
            random_seed: seedNumber,
            cross_validation: crossValidation,
          },
          algorithms,
        },
        { timeout: 300000 },
      )
      setNotice(
        `Experiment ${response.data.experiment_id} finished with ${
          response.data.results.filter((result) => result.status === 'completed').length
        } successful model(s).`,
      )
      await loadExperiments()
      navigate(`/experiments/${response.data.experiment_id}`)
    } catch (err) {
      setFormError(getErrorMessage(err, 'Training failed'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (target) => {
    const confirmed = window.confirm(
      `Delete experiment ${target.id}? Its saved models and prediction history will also be removed.`,
    )
    if (!confirmed) return
    try {
      await api.delete(`/experiments/${target.id}`)
      if (String(target.id) === String(experimentId)) {
        navigate('/experiments', { replace: true })
      }
      setNotice(`Deleted experiment ${target.id}.`)
      await loadExperiments()
    } catch (err) {
      setListError(getErrorMessage(err, 'Unable to delete experiment'))
    }
  }

  if (experimentId) {
    if (detailLoading) {
      return <LoadingSpinner label="Loading experiment…" />
    }
    if (!experiment) {
      return (
        <div>
          <PageHeader title="Experiment unavailable" />
          <ErrorMessage message={detailError || 'Experiment not found'} onRetry={loadDetail} />
          <Link to="/experiments" className="btn-secondary mt-4">
            <ArrowLeft className="h-4 w-4" />
            Back to experiments
          </Link>
        </div>
      )
    }

    const bestResult = (experiment.results || []).find(
      (result) => result.model_id === experiment.recommended_model_id,
    )

    return (
      <div>
        <PageHeader
          eyebrow="Experiment"
          title={`Predicting “${experiment.target_column}”`}
          description={`${titleCase(experiment.problem_type)} · ${
            experiment.selected_features?.length || 0
          } features · split ${formatNumber(experiment.split_configuration?.test_size, 2)} · seed ${
            experiment.random_seed
          }`}
          actions={
            <>
              <Link to="/experiments" className="btn-secondary">
                <ArrowLeft className="h-4 w-4" />
                All experiments
              </Link>
              <button
                type="button"
                className="btn-danger"
                onClick={() => handleDelete(experiment)}
              >
                <Trash2 className="h-4 w-4" />
                Delete
              </button>
            </>
          }
        />

        {notice ? (
          <div className="mb-4">
            <InlineNotice tone="success">{notice}</InlineNotice>
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <div className="card p-5">
            <p className="text-sm font-medium text-slate-500">Status</p>
            <div className="mt-2">
              <Badge tone={statusTone(experiment.status)}>{titleCase(experiment.status)}</Badge>
            </div>
          </div>
          <div className="card p-5">
            <p className="text-sm font-medium text-slate-500">Algorithms</p>
            <p className="mt-2 text-2xl font-bold text-slate-900">
              {experiment.results?.length || 0}
            </p>
          </div>
          <div className="card p-5">
            <p className="text-sm font-medium text-slate-500">Recommended</p>
            <p className="mt-2 truncate text-base font-bold text-slate-900">
              {bestResult
                ? bestResult.algorithm_label || titleCase(bestResult.algorithm)
                : '—'}
            </p>
            {bestResult ? (
              <p className="mt-1 text-xs text-slate-400">
                {experiment.problem_type === 'classification' ? 'F1 ' : 'R² '}
                {formatMetric(
                  experiment.problem_type === 'classification'
                    ? bestResult.metrics?.f1_score
                    : bestResult.metrics?.r2_score,
                )}
              </p>
            ) : null}
          </div>
          <div className="card p-5">
            <p className="text-sm font-medium text-slate-500">Created</p>
            <p className="mt-2 text-sm font-semibold text-slate-800">
              {formatDate(experiment.created_at)}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              Version #{experiment.dataset_version_id}
            </p>
          </div>
        </div>

        <section className="card mt-6">
          <div className="flex items-center gap-2 border-b border-slate-200 px-5 py-4">
            <Trophy className="h-4 w-4 text-brand-600" />
            <h2 className="text-base font-semibold text-slate-900">Model results</h2>
          </div>
          <ResultsTable experiment={experiment} />
        </section>

        <section className="card mt-6 p-5">
          <h2 className="text-base font-semibold text-slate-900">Configuration</h2>
          <dl className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Target
              </dt>
              <dd className="mt-1 text-sm text-slate-700">{experiment.target_column}</dd>
            </div>
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Problem type
              </dt>
              <dd className="mt-1 text-sm text-slate-700">
                {titleCase(experiment.problem_type)}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Test size
              </dt>
              <dd className="mt-1 text-sm text-slate-700">
                {formatNumber(experiment.split_configuration?.test_size, 2)}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Random seed
              </dt>
              <dd className="mt-1 text-sm text-slate-700">{experiment.random_seed}</dd>
            </div>
          </dl>
          <div className="mt-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Features
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {(experiment.selected_features || []).map((feature) => (
                <span
                  key={feature}
                  className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600"
                >
                  {feature}
                </span>
              ))}
              {experiment.selected_features?.length === 0 ? (
                <span className="text-sm text-slate-500">None recorded</span>
              ) : null}
            </div>
          </div>
        </section>
      </div>
    )
  }

  return (
    <div>
      <PageHeader
        eyebrow="Machine learning"
        title="Experiments"
        description="Train and compare algorithms on a single leakage-free train/test split."
      />

      {notice ? (
        <div className="mb-4">
          <InlineNotice tone="success">{notice}</InlineNotice>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <form onSubmit={handleSubmit} className="card space-y-4 p-5 lg:col-span-3" noValidate>
          <div className="flex items-center gap-2">
            <FlaskConical className="h-4 w-4 text-brand-600" />
            <h2 className="text-base font-semibold text-slate-900">New experiment</h2>
          </div>

          <ErrorMessage message={formError} />

          {datasets.length === 0 && !datasetsLoading ? (
            <EmptyState
              icon={FlaskConical}
              title="No datasets available"
              description="Upload a dataset before training a model."
              action={
                <Link to="/datasets/upload" className="btn-primary">
                  Upload dataset
                </Link>
              }
            />
          ) : (
            <>
              <div>
                <label className="label" htmlFor="experiment-dataset">
                  Dataset
                </label>
                <select
                  id="experiment-dataset"
                  className="input"
                  value={datasetId}
                  onChange={(event) => setDatasetId(event.target.value)}
                  disabled={datasetsLoading || submitting}
                >
                  <option value="">Select a dataset…</option>
                  {datasets.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name} ({formatNumber(item.row_count, 0)} rows)
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="label" htmlFor="target-column">
                    Target column
                  </label>
                  <select
                    id="target-column"
                    className="input"
                    value={targetColumn}
                    onChange={(event) => {
                      setTargetColumn(event.target.value)
                      setSelectedFeatures([])
                    }}
                    disabled={!datasetId || columnsLoading || submitting}
                  >
                    <option value="">
                      {columnsLoading ? 'Loading columns…' : 'Select a target…'}
                    </option>
                    {columns.map((column) => (
                      <option key={column} value={column}>
                        {column}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="label" htmlFor="problem-type">
                    Problem type
                  </label>
                  <select
                    id="problem-type"
                    className="input"
                    value={problemType}
                    onChange={handleProblemTypeChange}
                    disabled={submitting}
                  >
                    <option value="auto">Auto-detect</option>
                    <option value="classification">Classification</option>
                    <option value="regression">Regression</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div>
                  <label className="label" htmlFor="test-size">
                    Test size
                  </label>
                  <input
                    id="test-size"
                    type="number"
                    min="0.05"
                    max="0.5"
                    step="0.05"
                    className="input"
                    value={testSize}
                    onChange={(event) => setTestSize(event.target.value)}
                    disabled={submitting}
                  />
                </div>
                <div>
                  <label className="label" htmlFor="random-seed">
                    Random seed
                  </label>
                  <input
                    id="random-seed"
                    type="number"
                    step="1"
                    className="input"
                    value={randomSeed}
                    onChange={(event) => setRandomSeed(event.target.value)}
                    disabled={submitting}
                  />
                </div>
                <label className="flex items-end gap-2 pb-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                    checked={crossValidation}
                    onChange={(event) => setCrossValidation(event.target.checked)}
                    disabled={submitting}
                  />
                  Cross-validate
                </label>
              </div>

              {problemType === 'auto' ? (
                <InlineNotice tone="info">
                  The problem type is inferred from the target. All compatible algorithms are
                  trained when none are selected.
                </InlineNotice>
              ) : (
                <div>
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-700">Algorithms</span>
                    <div className="flex gap-3 text-xs font-semibold">
                      <button
                        type="button"
                        className="text-brand-600 hover:text-brand-700"
                        onClick={() => setAlgorithms([...availableAlgorithms])}
                      >
                        Select all
                      </button>
                      <button
                        type="button"
                        className="text-slate-500 hover:text-slate-700"
                        onClick={() => setAlgorithms([])}
                      >
                        Clear
                      </button>
                    </div>
                  </div>
                  <div className="grid grid-cols-1 gap-1 rounded-lg border border-slate-300 bg-white p-2 sm:grid-cols-2">
                    {availableAlgorithms.map((algorithm) => (
                      <label
                        key={algorithm}
                        className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm text-slate-700 hover:bg-slate-50"
                      >
                        <input
                          type="checkbox"
                          className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                          checked={algorithms.includes(algorithm)}
                          onChange={() => toggleAlgorithm(algorithm)}
                          disabled={submitting}
                        />
                        {catalog.labels?.[algorithm] || titleCase(algorithm)}
                      </label>
                    ))}
                  </div>
                  <p className="mt-1 text-xs text-slate-400">
                    {algorithms.length === 0
                      ? 'No algorithms selected — all compatible algorithms will run.'
                      : `${algorithms.length} algorithm(s) selected.`}
                  </p>
                </div>
              )}

              {targetColumn ? (
                <ColumnPicker
                  columns={featureOptions}
                  selected={selectedFeatures}
                  onChange={setSelectedFeatures}
                  label="Features (optional)"
                  hint="Leave empty to use every usable feature except the target and identifier-like columns."
                />
              ) : null}

              <div className="flex flex-wrap gap-2">
                <button type="submit" className="btn-primary" disabled={submitting}>
                  <Play className="h-4 w-4" />
                  {submitting ? 'Training…' : 'Run experiment'}
                </button>
                {submitting ? (
                  <span className="self-center text-xs text-slate-500">
                    Training may take a few moments…
                  </span>
                ) : null}
              </div>
            </>
          )}
        </form>

        <aside className="space-y-4 lg:col-span-2">
          <div className="card p-5">
            <h2 className="text-sm font-semibold text-slate-900">How it works</h2>
            <ul className="mt-3 space-y-2 text-sm text-slate-600">
              <li>Every algorithm shares one train/test split.</li>
              <li>Imputers, encoders and scalers are fit on training data only.</li>
              <li>The best model is selected by weighted F1 or R².</li>
              <li>Fitted pipelines are saved and can make live predictions.</li>
            </ul>
          </div>
          <div className="card p-5">
            <h2 className="text-sm font-semibold text-slate-900">Supported algorithms</h2>
            <div className="mt-3 space-y-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Classification
                </p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {catalog.classification.map((algorithm) => (
                    <Badge key={algorithm} tone="info">
                      {catalog.labels?.[algorithm] || titleCase(algorithm)}
                    </Badge>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Regression
                </p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {catalog.regression.map((algorithm) => (
                    <Badge key={algorithm} tone="neutral">
                      {catalog.labels?.[algorithm] || titleCase(algorithm)}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </aside>
      </div>

      <section className="card mt-6">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <h2 className="text-base font-semibold text-slate-900">Experiment history</h2>
          <button type="button" className="btn-secondary !py-1.5" onClick={loadExperiments}>
            Refresh
          </button>
        </div>

        {listError ? (
          <div className="p-5">
            <ErrorMessage message={listError} onRetry={loadExperiments} />
          </div>
        ) : listLoading ? (
          <LoadingSpinner label="Loading experiments…" />
        ) : experiments.length === 0 ? (
          <div className="p-5">
            <EmptyState
              icon={FlaskConical}
              title="No experiments yet"
              description="Configure your first experiment above to train and compare models."
            />
          </div>
        ) : (
          <div className="table-wrap border-0">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Target</th>
                  <th scope="col">Problem</th>
                  <th scope="col">Algorithms</th>
                  <th scope="col">Recommended</th>
                  <th scope="col">Status</th>
                  <th scope="col">Created</th>
                  <th scope="col" className="text-right">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {experiments.map((item) => {
                  const best = (item.results || []).find(
                    (result) => result.model_id === item.recommended_model_id,
                  )
                  return (
                    <tr key={item.id}>
                      <td>
                        <Link
                          to={`/experiments/${item.id}`}
                          className="font-semibold text-slate-800 hover:text-brand-600"
                        >
                          {item.target_column}
                        </Link>
                        <p className="text-xs text-slate-400">Experiment #{item.id}</p>
                      </td>
                      <td>{titleCase(item.problem_type)}</td>
                      <td>{item.results?.length || 0}</td>
                      <td>
                        {best ? (
                          <span className="text-slate-700">
                            {best.algorithm_label || titleCase(best.algorithm)}
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td>
                        <Badge tone={statusTone(item.status)}>{titleCase(item.status)}</Badge>
                      </td>
                      <td>{formatDate(item.created_at)}</td>
                      <td>
                        <div className="flex items-center justify-end gap-2">
                          <Link
                            to={`/experiments/${item.id}`}
                            className="btn-secondary !py-1.5"
                          >
                            Open
                          </Link>
                          <button
                            type="button"
                            className="btn-danger !px-2.5 !py-1.5"
                            aria-label={`Delete experiment ${item.id}`}
                            onClick={() => handleDelete(item)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
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
