import React from 'react'

const TONES = {
  neutral: 'bg-slate-100 text-slate-700',
  success: 'bg-emerald-100 text-emerald-700',
  warning: 'bg-amber-100 text-amber-700',
  danger: 'bg-red-100 text-red-700',
  info: 'bg-brand-100 text-brand-700',
}

export default function Badge({ children, tone = 'neutral', className = '' }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${TONES[tone] || TONES.neutral} ${className}`}
    >
      {children}
    </span>
  )
}

export function statusTone(status) {
  if (status === 'completed' || status === 'cleaned' || status === 'healthy') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'training' || status === 'uploaded') return 'warning'
  return 'neutral'
}
