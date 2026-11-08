import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search, Trash2, Trophy } from 'lucide-react'
import api, { getErrorMessage } from '../api/client'
import PageHeader from '../components/PageHeader'
import Badge, { statusTone } from '../components/Badge'
import { EmptyState, ErrorMessage, InlineNotice, LoadingSpinner } from '../components/Feedback'
import { formatDate, formatMetric, formatNumber, titleCase } from '../utils/format'

export default function ModelLeaderboard() {
  const [models, setModels] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [search, setSearch] = useState('')
  const [problemFilter, setProblemFilter] = useState('all')
  const [sort, setSort] = useState('newest')
  const [deletingId, setDeletingId] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await api.get('/models/')
      setModels(response.data)
    } catch (err) {
      setError(getErrorMessage(err, 'Unable to load models'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const visibleModels = useMemo(() => {
    const term = search.trim().toLowerCase()
    let filtered = models
    if (problemFilter !== 'all') {
      filtered = filtered.filter((model) => model.problem_type === problemFilter)
    }
    if (term) {
      filtered = filtered.filter(
        (model) =>
          (model.algorithm_label || model.algorithm_name).toLowerCase().includes(term) ||
          model.dataset_name.toLowerCase().includes(term) ||
          model.target_column.toLowerCase().includes(term),
      )
    }

    const primary = (model) =>
      model.problem_type === 'classification'
        ? model.metrics?.f1_score ?? model.metrics?.accuracy ?? -1
        : model.metrics?.r2_score ?? -1

    const sorted = [...filtered]
    if (sort === 'best') {
      sorted.sort((a, b) => primary(b) - primary(a))
    } else if (sort === 'fastest') {
      sorted.sort(
        (a, b) => (a.training_duration ?? Infinity) - (b.training_duration ?? Infinity),
      )
    } else {
      sorted.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    }
    return sorted
  }, [models, search, problemFilter, sort])

  const handleDelete = async (model) => {
    const confirmed = window.confirm(
      `Delete model “${model.algorithm_label || model.algorithm_name}” for “${model.target_column}”? This also removes its prediction history.`,
    )
    if (!confirmed) return
    setDeletingId(model.id)
    setError('')
    setNotice('')
    try {
      await api.delete(`/models/${model.id}`)
      setModels((current) => current.filter((item) => item.id !== model.id))
      setNotice('Model deleted.')
    } catch (err) {
      setError(getErrorMessage(err, 'Unable to delete model'))
    } finally {
      setDeletingId(null)
    }
  }

  if (loading) {
    return <LoadingSpinner label="Loading models…" />
  }

  return (
    <div>
      <PageHeader
        eyebrow="Models"
        title="Model leaderboard"
        description="Every successfully trained pipeline, ranked and ready for predictions."
      />

      <ErrorMessage message={error} onRetry={load} />
      {notice ? (
        <div className="mb-4">
          <InlineNotice tone="success">{notice}</InlineNotice>
        </div>
      ) : null}

      {models.length === 0 ? (
        <EmptyState
          icon={Trophy}
          title="No trained models yet"
          description="Run an experiment to train your first model."
          action={
            <Link to="/experiments" className="btn-primary">
              Go to experiments
            </Link>
          }
        />
      ) : (
        <>
          <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                type="search"
                className="input pl-9"
                placeholder="Search models…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                aria-label="Search models"
              />
            </div>
            <select
              className="input"
              value={problemFilter}
              onChange={(event) => setProblemFilter(event.target.value)}
              aria-label="Filter by problem type"
            >
              <option value="all">All problem types</option>
              <option value="classification">Classification</option>
              <option value="regression">Regression</option>
            </select>
            <select
              className="input"
              value={sort}
              onChange={(event) => setSort(event.target.value)}
              aria-label="Sort models"
            >
              <option value="newest">Newest first</option>
              <option value="best">Best score</option>
              <option value="fastest">Fastest training</option>
            </select>
            <p className="self-center text-sm text-slate-500">
              {visibleModels.length} of {models.length} model{models.length === 1 ? '' : 's'}
            </p>
          </div>

          {visibleModels.length === 0 ? (
            <EmptyState
              icon={Search}
              title="No matching models"
              description="Try a different search term or filter."
            />
          ) : (
            <div className="table-wrap bg-white">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Model</th>
                    <th scope="col">Dataset</th>
                    <th scope="col">Target</th>
                    <th scope="col">Problem</th>
                    <th scope="col">Score</th>
                    <th scope="col">Train time</th>
                    <th scope="col">Status</th>
                    <th scope="col">Created</th>
                    <th scope="col" className="text-right">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {visibleModels.map((model) => {
                    const isClassification = model.problem_type === 'classification'
                    return (
                      <tr key={model.id}>
                        <td>
                          <Link
                            to={`/models/${model.id}`}
                            className="font-semibold text-slate-800 hover:text-brand-600"
                          >
                            {model.algorithm_label || titleCase(model.algorithm_name)}
                          </Link>
                          <p className="text-xs text-slate-400">Model #{model.id}</p>
                        </td>
                        <td>
                          <Link
                            to={`/datasets/${model.dataset_id}`}
                            className="text-slate-600 hover:text-brand-600"
                          >
                            {model.dataset_name}
                          </Link>
                        </td>
                        <td>{model.target_column}</td>
                        <td>{titleCase(model.problem_type)}</td>
                        <td>
                          {isClassification ? (
                            <>
                              <span className="font-semibold text-slate-800">
                                F1 {formatMetric(model.metrics?.f1_score)}
                              </span>
                              <p className="text-xs text-slate-400">
                                Acc {formatMetric(model.metrics?.accuracy)}
                              </p>
                            </>
                          ) : (
                            <>
                              <span className="font-semibold text-slate-800">
                                R² {formatMetric(model.metrics?.r2_score)}
                              </span>
                              <p className="text-xs text-slate-400">
                                RMSE {formatMetric(model.metrics?.rmse)}
                              </p>
                            </>
                          )}
                        </td>
                        <td>
                          {model.training_duration !== null && model.training_duration !== undefined
                            ? `${formatNumber(model.training_duration, 3)}s`
                            : '—'}
                        </td>
                        <td>
                          <Badge tone={statusTone(model.status)}>{titleCase(model.status)}</Badge>
                        </td>
                        <td>{formatDate(model.created_at)}</td>
                        <td>
                          <div className="flex items-center justify-end gap-2">
                            <Link to={`/models/${model.id}`} className="btn-secondary !py-1.5">
                              Open
                            </Link>
                            <button
                              type="button"
                              className="btn-danger !px-2.5 !py-1.5"
                              aria-label={`Delete model ${model.id}`}
                              disabled={deletingId === model.id}
                              onClick={() => handleDelete(model)}
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
        </>
      )}
    </div>
  )
}
