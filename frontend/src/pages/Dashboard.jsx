import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  Database,
  FlaskConical,
  Sparkles,
  Trophy,
  Upload,
} from 'lucide-react'
import api, { getErrorMessage } from '../api/client'
import { useAuth } from '../context/AuthContext'
import PageHeader from '../components/PageHeader'
import StatCard from '../components/StatCard'
import Badge, { statusTone } from '../components/Badge'
import { EmptyState, ErrorMessage, LoadingSpinner, InlineNotice } from '../components/Feedback'
import { formatDate, formatMetric, titleCase } from '../utils/format'

export default function Dashboard() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [datasets, setDatasets] = useState([])
  const [experiments, setExperiments] = useState([])
  const [models, setModels] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [partial, setPartial] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    setPartial('')
    const results = await Promise.allSettled([
      api.get('/datasets/'),
      api.get('/experiments/'),
      api.get('/models/'),
    ])

    const failures = []
    if (results[0].status === 'fulfilled') {
      setDatasets(results[0].value.data)
    } else {
      failures.push('datasets')
    }
    if (results[1].status === 'fulfilled') {
      setExperiments(results[1].value.data)
    } else {
      failures.push('experiments')
    }
    if (results[2].status === 'fulfilled') {
      setModels(results[2].value.data)
    } else {
      failures.push('models')
    }

    if (failures.length === 3) {
      setError(getErrorMessage(results[0].reason, 'Unable to load your workspace'))
    } else if (failures.length > 0) {
      setPartial(`Could not load: ${failures.join(', ')}. Some numbers may be incomplete.`)
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const completedModels = useMemo(
    () => models.filter((model) => model.status === 'completed'),
    [models],
  )

  const bestModel = useMemo(() => {
    const completed = completedModels.filter((model) => model.metrics)
    if (completed.length === 0) return null
    return completed.reduce((best, model) => {
      if (model.problem_type === 'classification') {
        const score = model.metrics?.f1_score ?? model.metrics?.accuracy ?? -1
        const bestScore = best?.metrics?.f1_score ?? best?.metrics?.accuracy ?? -1
        return score > bestScore ? model : best
      }
      const score = model.metrics?.r2_score ?? -Infinity
      const bestScore = best?.metrics?.r2_score ?? -Infinity
      return score > bestScore ? model : best
    }, completed[0])
  }, [completedModels])

  if (loading) {
    return <LoadingSpinner label="Loading your workspace…" />
  }

  return (
    <div>
      <PageHeader
        eyebrow="Overview"
        title={`Welcome back, ${user?.username || 'there'}`}
        description="A snapshot of your datasets, experiments and trained models."
        actions={
          <>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => navigate('/datasets/upload')}
            >
              <Upload className="h-4 w-4" />
              Upload dataset
            </button>
            <button type="button" className="btn-primary" onClick={() => navigate('/experiments')}>
              <FlaskConical className="h-4 w-4" />
              New experiment
            </button>
          </>
        }
      />

      <ErrorMessage message={error} onRetry={load} />
      {partial ? (
        <div className="mb-4">
          <InlineNotice tone="warning">{partial}</InlineNotice>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          icon={Database}
          label="Datasets"
          value={datasets.length}
          hint={`${datasets.filter((item) => item.status === 'cleaned').length} cleaned`}
        />
        <StatCard
          icon={FlaskConical}
          label="Experiments"
          value={experiments.length}
          hint={`${experiments.filter((item) => item.status === 'completed').length} completed`}
          tone="amber"
        />
        <StatCard
          icon={Trophy}
          label="Trained models"
          value={completedModels.length}
          hint={`${models.length} total model records`}
          tone="emerald"
        />
        <StatCard
          icon={Sparkles}
          label="Best model"
          value={
            bestModel
              ? bestModel.problem_type === 'classification'
                ? formatMetric(bestModel.metrics?.f1_score)
                : formatMetric(bestModel.metrics?.r2_score)
              : '—'
          }
          hint={
            bestModel
              ? `${bestModel.algorithm_label || titleCase(bestModel.algorithm_name)} · ${
                  bestModel.problem_type === 'classification' ? 'F1' : 'R²'
                }`
              : 'Train a model to see it here'
          }
          tone="slate"
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="card">
          <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
            <h2 className="text-base font-semibold text-slate-900">Recent datasets</h2>
            <Link
              to="/datasets"
              className="inline-flex items-center gap-1 text-sm font-semibold text-brand-600 hover:text-brand-700"
            >
              View all <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
          {datasets.length === 0 ? (
            <div className="p-5">
              <EmptyState
                icon={Database}
                title="No datasets yet"
                description="Upload a CSV or Excel file to begin profiling, cleaning and modelling."
                action={
                  <Link to="/datasets/upload" className="btn-primary">
                    <Upload className="h-4 w-4" />
                    Upload dataset
                  </Link>
                }
              />
            </div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {datasets.slice(0, 5).map((dataset) => (
                <li key={dataset.id}>
                  <Link
                    to={`/datasets/${dataset.id}`}
                    className="flex items-center justify-between gap-3 px-5 py-3 hover:bg-slate-50"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-slate-800">
                        {dataset.name}
                      </p>
                      <p className="text-xs text-slate-500">
                        {dataset.row_count.toLocaleString()} rows · {dataset.column_count} columns
                        · {formatDate(dataset.created_at)}
                      </p>
                    </div>
                    <Badge tone={statusTone(dataset.status)}>{titleCase(dataset.status)}</Badge>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card">
          <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
            <h2 className="text-base font-semibold text-slate-900">Recent experiments</h2>
            <Link
              to="/experiments"
              className="inline-flex items-center gap-1 text-sm font-semibold text-brand-600 hover:text-brand-700"
            >
              View all <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
          {experiments.length === 0 ? (
            <div className="p-5">
              <EmptyState
                icon={FlaskConical}
                title="No experiments yet"
                description="Choose a dataset and target column to train and compare models."
                action={
                  <Link to="/experiments" className="btn-primary">
                    Start an experiment
                  </Link>
                }
              />
            </div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {experiments.slice(0, 5).map((experiment) => (
                <li key={experiment.id}>
                  <Link
                    to={`/experiments/${experiment.id}`}
                    className="flex items-center justify-between gap-3 px-5 py-3 hover:bg-slate-50"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-slate-800">
                        Predicting “{experiment.target_column}”
                      </p>
                      <p className="text-xs text-slate-500">
                        {titleCase(experiment.problem_type)} · {experiment.results?.length || 0}{' '}
                        algorithms · {formatDate(experiment.created_at)}
                      </p>
                    </div>
                    <Badge tone={statusTone(experiment.status)}>
                      {titleCase(experiment.status)}
                    </Badge>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}
