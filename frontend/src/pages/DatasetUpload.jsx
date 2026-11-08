import React, { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileSpreadsheet, Upload, X } from 'lucide-react'
import api, { getErrorMessage } from '../api/client'
import PageHeader from '../components/PageHeader'
import { ErrorMessage, InlineNotice } from '../components/Feedback'
import { formatBytes } from '../utils/format'

const MAX_BYTES = 100 * 1024 * 1024
const ACCEPTED = ['.csv', '.xlsx', '.xls']

export default function DatasetUpload() {
  const navigate = useNavigate()
  const inputRef = useRef(null)
  const [file, setFile] = useState(null)
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)

  const resetFile = () => {
    setFile(null)
    setName('')
    setProgress(0)
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleFileChange = (event) => {
    const selected = event.target.files?.[0]
    setError('')
    if (!selected) {
      setFile(null)
      return
    }
    const extension = `.${selected.name.split('.').pop()?.toLowerCase() || ''}`
    if (!ACCEPTED.includes(extension)) {
      setError('Only .csv, .xlsx and .xls files are supported')
      resetFile()
      return
    }
    if (selected.size > MAX_BYTES) {
      setError(`File is too large. The maximum size is ${formatBytes(MAX_BYTES)}`)
      resetFile()
      return
    }
    if (selected.size === 0) {
      setError('The selected file is empty')
      resetFile()
      return
    }
    setFile(selected)
    if (!name) {
      setName(selected.name.replace(/\.[^/.]+$/, ''))
    }
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    if (!file) {
      setError('Choose a CSV or Excel file to upload')
      return
    }

    const formData = new FormData()
    formData.append('file', file)
    formData.append('name', name.trim())

    setUploading(true)
    setProgress(0)
    try {
      const response = await api.post('/datasets/upload', formData, {
        onUploadProgress: (event) => {
          if (event.total) {
            setProgress(Math.round((event.loaded / event.total) * 100))
          }
        },
      })
      navigate(`/datasets/${response.data.id}`, {
        replace: true,
        state: { uploaded: true },
      })
    } catch (err) {
      setError(getErrorMessage(err, 'Upload failed'))
    } finally {
      setUploading(false)
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Data"
        title="Upload dataset"
        description="Upload a CSV or Excel file. Duplicate column names and unsupported formats are rejected before anything is stored."
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <form onSubmit={handleSubmit} className="card space-y-5 p-6 lg:col-span-2" noValidate>
          <ErrorMessage message={error} />

          <div>
            <label className="label" htmlFor="dataset-file">
              Dataset file
            </label>
            <div className="rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 px-5 py-8 text-center">
              <FileSpreadsheet className="mx-auto h-10 w-10 text-slate-300" />
              <p className="mt-3 text-sm text-slate-600">
                <label
                  htmlFor="dataset-file"
                  className="cursor-pointer font-semibold text-brand-600 hover:text-brand-700"
                >
                  Choose a file
                </label>{' '}
                or drag it into this area
              </p>
              <p className="mt-1 text-xs text-slate-400">
                CSV, XLSX or XLS · up to {formatBytes(MAX_BYTES)}
              </p>
              <input
                ref={inputRef}
                id="dataset-file"
                type="file"
                accept=".csv,.xlsx,.xls"
                className="sr-only"
                onChange={handleFileChange}
              />
            </div>

            {file ? (
              <div className="mt-3 flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2">
                <div className="flex min-w-0 items-center gap-2">
                  <FileSpreadsheet className="h-4 w-4 shrink-0 text-brand-600" />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-800">{file.name}</p>
                    <p className="text-xs text-slate-500">{formatBytes(file.size)}</p>
                  </div>
                </div>
                <button
                  type="button"
                  className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                  onClick={resetFile}
                  aria-label="Remove selected file"
                  disabled={uploading}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ) : null}
          </div>

          <div>
            <label className="label" htmlFor="dataset-name">
              Dataset name
            </label>
            <input
              id="dataset-name"
              type="text"
              className="input"
              value={name}
              maxLength={256}
              placeholder="e.g. Customer churn"
              onChange={(event) => setName(event.target.value)}
              disabled={uploading}
            />
            <p className="mt-1 text-xs text-slate-400">
              Optional. Defaults to the file name.
            </p>
          </div>

          {uploading ? (
            <div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-brand-600 transition-all"
                  style={{ width: `${progress}%` }}
                  role="progressbar"
                  aria-valuenow={progress}
                  aria-valuemin={0}
                  aria-valuemax={100}
                />
              </div>
              <p className="mt-1 text-xs text-slate-500">Uploading… {progress}%</p>
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <button type="submit" className="btn-primary" disabled={uploading || !file}>
              <Upload className="h-4 w-4" />
              {uploading ? 'Uploading…' : 'Upload dataset'}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => navigate('/datasets')}
              disabled={uploading}
            >
              Cancel
            </button>
          </div>
        </form>

        <aside className="space-y-4">
          <div className="card p-5">
            <h2 className="text-sm font-semibold text-slate-900">What happens next?</h2>
            <ol className="mt-3 space-y-3 text-sm text-slate-600">
              <li>
                <span className="font-semibold text-slate-800">1. Validation.</span> The file is
                parsed and duplicate headers are rejected.
              </li>
              <li>
                <span className="font-semibold text-slate-800">2. Versioning.</span> Your upload
                is stored as version 0 of the dataset.
              </li>
              <li>
                <span className="font-semibold text-slate-800">3. Exploration.</span> Preview the
                rows, then open Analysis for automated profiling.
              </li>
              <li>
                <span className="font-semibold text-slate-800">4. Modelling.</span> Clean the data
                and train models on any version.
              </li>
            </ol>
          </div>
          <InlineNotice tone="info">
            Files are stored per dataset and never mixed between accounts. Deleting a dataset
            also removes its derived versions, experiments and models.
          </InlineNotice>
        </aside>
      </div>
    </div>
  )
}
