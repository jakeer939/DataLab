import React from 'react'
import { Loader2 } from 'lucide-react'

export function LoadingSpinner({ label = 'Loading…', className = '' }) {
  return (
    <div className={`flex items-center justify-center gap-3 py-10 text-slate-500 ${className}`}>
      <Loader2 className="h-5 w-5 animate-spin text-brand-600" />
      <span className="text-sm">{label}</span>
    </div>
  )
}

export function ErrorMessage({ message, onRetry }) {
  if (!message) return null
  return (
    <div
      role="alert"
      className="flex flex-col gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 sm:flex-row sm:items-center sm:justify-between"
    >
      <span>{message}</span>
      {onRetry ? (
        <button type="button" className="btn-secondary !py-1.5 text-red-700" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  )
}

export function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center">
      {Icon ? <Icon className="mb-3 h-10 w-10 text-slate-300" /> : null}
      <h3 className="text-base font-semibold text-slate-700">{title}</h3>
      {description ? <p className="mt-1 max-w-md text-sm text-slate-500">{description}</p> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  )
}

export function InlineNotice({ tone = 'info', children }) {
  const tones = {
    info: 'border-brand-200 bg-brand-50 text-brand-800',
    success: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    warning: 'border-amber-200 bg-amber-50 text-amber-800',
    danger: 'border-red-200 bg-red-50 text-red-800',
  }
  return (
    <div className={`rounded-lg border px-4 py-3 text-sm ${tones[tone] || tones.info}`}>
      {children}
    </div>
  )
}
