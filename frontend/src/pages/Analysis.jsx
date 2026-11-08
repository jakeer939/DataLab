import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  Eraser,
  Grid3X3,
  LineChart,
  Table2,
} from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import api, { getErrorMessage } from '../api/client'
import PageHeader from '../components/PageHeader'
import Badge from '../components/Badge'
import { EmptyState, ErrorMessage, InlineNotice, LoadingSpinner } from '../components/Feedback'
import { formatBytes, formatNumber, formatPercent, titleCase } from '../utils/format'

const TABS = [
  { id: 'overview', label: 'Overview', icon: BarChart3 },
  { id: 'columns', label: 'Columns', icon: Table2 },
  { id: 'charts', label: 'Charts', icon: LineChart },
  { id: 'quality', label: 'Quality', icon: AlertTriangle },
]

function summaryFor(column) {
  if (column.data_type === 'numerical') {
    return `mean ${formatNumber(column.mean)} · median ${formatNumber(column.median)} · min ${formatNumber(
      column.minimum,
    )} · max ${formatNumber(column.maximum)}`
  }
  if (column.data_type === 'datetime') {
    return `${column.earliest || '—'} → ${column.latest || '—'}`
  }
  if (column.most_frequent_category !== undefined) {
    return `${column.number_of_unique_categories} categories · most frequent “${column.most_frequent_category}”`
  }
  return '—'
}

function ChartCard({ title, subtitle, children }) {
  return (
    <div className="card p-4">
      <div className="mb-3">
        <h3 className="truncate text-sm font-semibold text-slate-800" title={title}>
          {title}
        </h3>
        {subtitle ? <p className="text-xs text-slate-400">{subtitle}</p> : null}
      </div>
      <div className="h-56 w-full">{children}</div>
    </div>
  )
}

function ScatterSection({ datasetId, numericColumns }) {
  const [xColumn, setXColumn] = useState(numericColumns[0] || '')
  const [yColumn, setYColumn] = useState(numericColumns[1] || numericColumns[0] || '')
  const [points, setPoints] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (numericColumns.length === 0) return
    setXColumn((current) => (numericColumns.includes(current) ? current : numericColumns[0]))
    setYColumn((current) =>
      numericColumns.includes(current) ? current : numericColumns[1] || numericColumns[0],
    )
  }, [numericColumns])

  const loadScatter = useCallback(async () => {
    if (!xColumn || !yColumn) return
    setLoading(true)
    setError('')
    try {
      const response = await api.get(`/profiling/${datasetId}/scatter`, {
        params: { x_column: xColumn, y_column: yColumn, limit: 1000 },
      })
      setPoints(response.data.points || [])
    } catch (err) {
      setError(getErrorMessage(err, 'Unable to load scatter data'))
    } finally {
      setLoading(false)
    }
  }, [datasetId, xColumn, yColumn])

  useEffect(() => {
    loadScatter()
  }, [loadScatter])

  if (numericColumns.length < 2) {
    return (
      <InlineNotice tone="info">
        A scatter plot needs at least two numeric columns.
      </InlineNotice>
    )
  }

  return (
    <div className="card p-4">
      <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">Scatter plot</h3>
          <p className="text-xs text-slate-400">
            Sampled up to 1,000 complete numeric pairs.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <label className="text-xs font-medium text-slate-500">
            X axis
            <select
              className="input mt-1 sm:w-40"
              value={xColumn}
              onChange={(event) => setXColumn(event.target.value)}
            >
              {numericColumns.map((column) => (
                <option key={column} value={column}>
                  {column}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-slate-500">
            Y axis
            <select
              className="input mt-1 sm:w-40"
              value={yColumn}
              onChange={(event) => setYColumn(event.target.value)}
            >
              {numericColumns.map((column) => (
                <option key={column} value={column}>
                  {column}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      {error ? <ErrorMessage message={error} onRetry={loadScatter} /> : null}
      {loading ? (
        <LoadingSpinner label="Loading scatter data…" />
      ) : points.length === 0 ? (
        <p className="py-10 text-center text-sm text-slate-500">
          No complete numeric pairs were found for these columns.
        </p>
      ) : (
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis
                type="number"
                dataKey="x"
                name={xColumn}
                tick={{ fontSize: 11 }}
                stroke="#94a3b8"
              />
              <YAxis
                type="number"
                dataKey="y"
                name={yColumn}
                tick={{ fontSize: 11 }}
                stroke="#94a3b8"
              />
              <Tooltip
                cursor={{ strokeDasharray: '3 3' }}
                formatter={(value) => formatNumber(value, 4)}
              />
              <Scatter data={points} fill="#4f46e5" fillOpacity={0.6} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

export default function Analysis() {
  const { datasetId } = useParams()
  const [dataset, setDataset] = useState(null)
  const [profile, setProfile] = useState(null)
  const [quality, setQuality] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('overview')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [datasetResponse, profileResponse, qualityResponse] = await Promise.all([
        api.get(`/datasets/${datasetId}`),
        api.get(`/profiling/${datasetId}`),
        api.get(`/profiling/${datasetId}/quality`),
      ])
      setDataset(datasetResponse.data)
      setProfile(profileResponse.data)
      setQuality(qualityResponse.data)
    } catch (err) {
      setError(getErrorMessage(err, 'Unable to profile this dataset'))
    } finally {
      setLoading(false)
    }
  }, [datasetId])

  useEffect(() => {
    load()
  }, [load])

  const numericColumns = useMemo(() => {
    if (!profile?.column_analysis) return []
    return Object.values(profile.column_analysis)
      .filter((column) => column.data_type === 'numerical')
      .map((column) => column.column_name)
  }, [profile])

  const overview = profile?.overview
  const correlation = profile?.correlation
  const charts = profile?.charts

  if (loading) {
    return <LoadingSpinner label="Profiling dataset…" />
  }

  if (!profile || !dataset) {
    return (
      <div>
        <PageHeader title="Analysis unavailable" />
        <ErrorMessage message={error || 'Unable to load analysis'} onRetry={load} />
        <Link to="/datasets" className="btn-secondary mt-4">
          <ArrowLeft className="h-4 w-4" />
          Back to datasets
        </Link>
      </div>
    )
  }

  const typeEntries = [
    ['Numerical', overview.total_numerical_columns, 'brand'],
    ['Categorical', overview.total_categorical_columns, 'warning'],
    ['Datetime', overview.total_datetime_columns, 'info'],
    ['Boolean', overview.total_boolean_columns, 'neutral'],
    ['Empty', overview.total_empty_columns, 'danger'],
  ]

  return (
    <div>
      <PageHeader
        eyebrow="Analysis"
        title={`Profile · ${dataset.name}`}
        description="Automated statistics, distributions and data-quality checks for the latest dataset version."
        actions={
          <>
            <Link to={`/datasets/${dataset.id}`} className="btn-secondary">
              <ArrowLeft className="h-4 w-4" />
              Dataset
            </Link>
            <Link to={`/datasets/${dataset.id}/cleaning`} className="btn-primary">
              <Eraser className="h-4 w-4" />
              Clean data
            </Link>
          </>
        }
      />

      <ErrorMessage message={error} onRetry={load} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="card p-5">
          <p className="text-sm font-medium text-slate-500">Rows</p>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {formatNumber(overview.number_of_rows, 0)}
          </p>
          <p className="mt-1 text-xs text-slate-400">
            {overview.total_duplicate_rows} duplicate rows
          </p>
        </div>
        <div className="card p-5">
          <p className="text-sm font-medium text-slate-500">Columns</p>
          <p className="mt-2 text-2xl font-bold text-slate-900">{overview.number_of_columns}</p>
          <p className="mt-1 text-xs text-slate-400">
            {overview.total_numerical_columns} numerical · {overview.total_categorical_columns}{' '}
            categorical
          </p>
        </div>
        <div className="card p-5">
          <p className="text-sm font-medium text-slate-500">Missing cells</p>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {formatNumber(overview.total_missing_cells, 0)}
          </p>
          <p className="mt-1 text-xs text-slate-400">
            {formatPercent(
              (overview.total_missing_cells /
                Math.max(overview.number_of_rows * overview.number_of_columns, 1)) *
                100,
            )}{' '}
            of all cells
          </p>
        </div>
        <div className="card p-5">
          <p className="text-sm font-medium text-slate-500">Memory</p>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {formatBytes(overview.memory_usage_bytes)}
          </p>
          <p className="mt-1 text-xs text-slate-400">{overview.memory_usage_mb} MB in memory</p>
        </div>
      </div>

      <div className="mt-6 flex flex-wrap gap-2 border-b border-slate-200">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            aria-selected={tab === id}
            className={`-mb-px inline-flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors ${
              tab === id
                ? 'border-brand-600 text-brand-700'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      <div className="mt-5">
        {tab === 'overview' ? (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <section className="card p-5">
              <h2 className="text-base font-semibold text-slate-900">Column types</h2>
              <ul className="mt-4 space-y-2">
                {typeEntries.map(([label, count, tone]) => (
                  <li key={label} className="flex items-center justify-between gap-3">
                    <Badge tone={tone}>{label}</Badge>
                    <span className="text-sm font-semibold text-slate-800">{count}</span>
                  </li>
                ))}
              </ul>
            </section>

            <section className="card p-5">
              <div className="flex items-center gap-2">
                <Grid3X3 className="h-4 w-4 text-brand-600" />
                <h2 className="text-base font-semibold text-slate-900">Correlation matrix</h2>
              </div>
              {correlation?.columns?.length > 1 ? (
                <div className="table-wrap mt-3 border-0">
                  <table className="table">
                    <thead>
                      <tr>
                        <th scope="col"> </th>
                        {correlation.columns.map((column) => (
                          <th key={column} scope="col">
                            {column}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {correlation.matrix.map((row, rowIndex) => (
                        <tr key={`corr-${correlation.columns[rowIndex]}`}>
                          <th scope="row" className="text-slate-700">
                            {correlation.columns[rowIndex]}
                          </th>
                          {row.map((value, columnIndex) => {
                            const numeric = typeof value === 'number' ? value : 0
                            const intensity = Math.min(Math.abs(numeric), 1)
                            return (
                              <td
                                key={`corr-${rowIndex}-${columnIndex}`}
                                style={{
                                  backgroundColor:
                                    numeric >= 0
                                      ? `rgba(79, 70, 229, ${intensity * 0.35})`
                                      : `rgba(239, 68, 68, ${intensity * 0.35})`,
                                }}
                              >
                                {value === null ? '—' : Number(value).toFixed(2)}
                              </td>
                            )
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="mt-3 text-sm text-slate-500">
                  At least two numeric columns are required for correlations.
                </p>
              )}
            </section>
          </div>
        ) : null}

        {tab === 'columns' ? (
          <div className="table-wrap bg-white">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Column</th>
                  <th scope="col">Type</th>
                  <th scope="col">Missing</th>
                  <th scope="col">Unique</th>
                  <th scope="col">Statistics</th>
                </tr>
              </thead>
              <tbody>
                {Object.values(profile.column_analysis).map((column) => (
                  <tr key={column.column_name}>
                    <td className="font-semibold text-slate-800">{column.column_name}</td>
                    <td>
                      <Badge tone={column.data_type === 'numerical' ? 'info' : 'neutral'}>
                        {titleCase(column.data_type)}
                      </Badge>
                      <span className="ml-2 text-xs text-slate-400">{column.dtype}</span>
                    </td>
                    <td>
                      <span
                        className={
                          column.missing_value_percentage > 50
                            ? 'font-semibold text-red-600'
                            : 'text-slate-600'
                        }
                      >
                        {formatPercent(column.missing_value_percentage)}
                      </span>
                      <span className="ml-1 text-xs text-slate-400">
                        ({column.missing_value_count})
                      </span>
                    </td>
                    <td>{column.unique_value_count}</td>
                    <td className="whitespace-normal text-xs text-slate-500">
                      {summaryFor(column)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {tab === 'charts' ? (
          <div className="space-y-6">
            <ScatterSection datasetId={dataset.id} numericColumns={numericColumns} />

            {Object.keys(charts?.histograms || {}).length > 0 ? (
              <div>
                <h2 className="mb-3 text-base font-semibold text-slate-900">
                  Numeric distributions
                </h2>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {Object.entries(charts.histograms).map(([column, histogram]) => {
                    const data = histogram.counts.map((count, index) => ({
                      label: `${formatNumber(histogram.bins[index])}–${formatNumber(
                        histogram.bins[index + 1],
                      )}`,
                      count,
                    }))
                    return (
                      <ChartCard
                        key={column}
                        title={column}
                        subtitle={`${histogram.counts.reduce((sum, value) => sum + value, 0)} values · ${
                          histogram.counts.length
                        } bins`}
                      >
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                            <XAxis dataKey="label" hide />
                            <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" />
                            <Tooltip
                              formatter={(value) => [value, 'Count']}
                              labelFormatter={(label) => `Range: ${label}`}
                            />
                            <Bar dataKey="count" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </ChartCard>
                    )
                  })}
                </div>
              </div>
            ) : null}

            {Object.keys(charts?.bar_charts || {}).length > 0 ? (
              <div>
                <h2 className="mb-3 text-base font-semibold text-slate-900">
                  Category distributions
                </h2>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {Object.entries(charts.bar_charts).map(([column, chart]) => {
                    const data = chart.categories.map((category, index) => ({
                      name: category,
                      count: chart.counts[index],
                    }))
                    return (
                      <ChartCard key={column} title={column} subtitle="Top 10 categories">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                            <XAxis dataKey="name" hide />
                            <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" />
                            <Tooltip
                              formatter={(value) => [value, 'Count']}
                              labelFormatter={(label) => `Category: ${label}`}
                            />
                            <Bar dataKey="count" fill="#0ea5e9" radius={[4, 4, 0, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </ChartCard>
                    )
                  })}
                </div>
              </div>
            ) : null}

            {Object.keys(charts?.histograms || {}).length === 0 &&
            Object.keys(charts?.bar_charts || {}).length === 0 ? (
              <EmptyState
                icon={LineChart}
                title="No chartable columns"
                description="This dataset does not contain numeric or categorical columns with values."
              />
            ) : null}
          </div>
        ) : null}

        {tab === 'quality' ? (
          <div className="space-y-6">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="card p-5">
                <p className="text-sm font-medium text-slate-500">Duplicate rows</p>
                <p className="mt-2 text-2xl font-bold text-slate-900">
                  {quality.duplicate_records.total_duplicates}
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  {formatPercent(quality.duplicate_records.percentage)} of rows
                </p>
              </div>
              <div className="card p-5">
                <p className="text-sm font-medium text-slate-500">Outlier columns</p>
                <p className="mt-2 text-2xl font-bold text-slate-900">
                  {Object.keys(quality.outliers).length}
                </p>
                <p className="mt-1 text-xs text-slate-400">Detected with the IQR method</p>
              </div>
              <div className="card p-5">
                <p className="text-sm font-medium text-slate-500">Columns with missing values</p>
                <p className="mt-2 text-2xl font-bold text-slate-900">
                  {
                    Object.values(quality.missing_values).filter((item) => item.count > 0)
                      .length
                  }
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  {
                    Object.values(quality.missing_values).filter((item) => item.is_excessive)
                      .length
                  }{' '}
                  exceed 50% missing
                </p>
              </div>
            </div>

            <section className="card">
              <div className="border-b border-slate-200 px-5 py-4">
                <h2 className="text-base font-semibold text-slate-900">Missing values</h2>
              </div>
              <div className="table-wrap border-0">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Column</th>
                      <th scope="col">Missing</th>
                      <th scope="col">Percentage</th>
                      <th scope="col">Assessment</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(quality.missing_values).map(([column, item]) => (
                      <tr key={column}>
                        <td className="font-semibold text-slate-800">{column}</td>
                        <td>{item.count}</td>
                        <td>{formatPercent(item.percentage)}</td>
                        <td>
                          {item.count === 0 ? (
                            <Badge tone="success">Complete</Badge>
                          ) : item.is_excessive ? (
                            <Badge tone="danger">Excessive</Badge>
                          ) : (
                            <Badge tone="warning">Some missing</Badge>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {Object.keys(quality.outliers).length > 0 ? (
              <section className="card">
                <div className="border-b border-slate-200 px-5 py-4">
                  <h2 className="text-base font-semibold text-slate-900">Outliers</h2>
                </div>
                <div className="table-wrap border-0">
                  <table className="table">
                    <thead>
                      <tr>
                        <th scope="col">Column</th>
                        <th scope="col">Count</th>
                        <th scope="col">Percentage</th>
                        <th scope="col">Bounds</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(quality.outliers).map(([column, item]) => (
                        <tr key={column}>
                          <td className="font-semibold text-slate-800">{column}</td>
                          <td>{item.count}</td>
                          <td>{formatPercent(item.percentage)}</td>
                          <td>
                            {formatNumber(item.lower_bound)} – {formatNumber(item.upper_bound)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            ) : null}

            <section className="card p-5">
              <h2 className="text-base font-semibold text-slate-900">Inconsistent data</h2>
              <dl className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Whitespace issues
                  </dt>
                  <dd className="mt-1 text-sm text-slate-700">
                    {quality.inconsistent_data.whitespace_columns.length > 0
                      ? quality.inconsistent_data.whitespace_columns.join(', ')
                      : 'None detected'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Mixed types
                  </dt>
                  <dd className="mt-1 text-sm text-slate-700">
                    {quality.inconsistent_data.mixed_type_columns.length > 0
                      ? quality.inconsistent_data.mixed_type_columns.join(', ')
                      : 'None detected'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Partly numeric
                  </dt>
                  <dd className="mt-1 text-sm text-slate-700">
                    {quality.inconsistent_data.invalid_numerical_columns.length > 0
                      ? quality.inconsistent_data.invalid_numerical_columns.join(', ')
                      : 'None detected'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Partly dates
                  </dt>
                  <dd className="mt-1 text-sm text-slate-700">
                    {quality.inconsistent_data.invalid_date_columns.length > 0
                      ? quality.inconsistent_data.invalid_date_columns.join(', ')
                      : 'None detected'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Empty columns
                  </dt>
                  <dd className="mt-1 text-sm text-slate-700">
                    {quality.inconsistent_data.empty_columns.length > 0
                      ? quality.inconsistent_data.empty_columns.join(', ')
                      : 'None detected'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Constant columns
                  </dt>
                  <dd className="mt-1 text-sm text-slate-700">
                    {quality.inconsistent_data.constant_columns.length > 0
                      ? quality.inconsistent_data.constant_columns.join(', ')
                      : 'None detected'}
                  </dd>
                </div>
              </dl>
            </section>
          </div>
        ) : null}
      </div>
    </div>
  )
}
