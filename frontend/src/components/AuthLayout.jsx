import React from 'react'
import { BarChart3 } from 'lucide-react'

export default function AuthLayout({ title, subtitle, children, footer }) {
  return (
    <div className="flex min-h-screen flex-col bg-slate-50 lg:flex-row">
      <aside className="relative hidden flex-1 flex-col justify-between overflow-hidden bg-brand-700 px-12 py-12 text-white lg:flex">
        <div className="absolute -right-24 -top-24 h-96 w-96 rounded-full bg-brand-500/40 blur-3xl" />
        <div className="absolute -bottom-32 -left-16 h-96 w-96 rounded-full bg-indigo-400/30 blur-3xl" />
        <div className="relative flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-white/15">
            <BarChart3 className="h-6 w-6" />
          </span>
          <div>
            <p className="text-xl font-bold leading-tight">DataLab</p>
            <p className="text-xs uppercase tracking-wider text-brand-200">
              Data science workspace
            </p>
          </div>
        </div>
        <div className="relative max-w-md">
          <h2 className="text-3xl font-bold leading-snug">
            Profile, clean, train and evaluate — in one place.
          </h2>
          <p className="mt-4 text-sm leading-relaxed text-brand-100">
            Upload a dataset, explore automated statistics and quality checks, apply
            reproducible cleaning steps, then train and compare machine-learning models
            with leakage-safe pipelines.
          </p>
          <ul className="mt-8 space-y-3 text-sm text-brand-100">
            <li>Automated exploratory data analysis</li>
            <li>Auditable, versioned data cleaning</li>
            <li>Classification and regression benchmarks</li>
            <li>Saved models with live predictions</li>
          </ul>
        </div>
        <p className="relative text-xs text-brand-200">
          DataLab · Automated Data Analysis, Cleaning &amp; ML Platform
        </p>
      </aside>

      <main className="flex flex-1 items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600 text-white">
              <BarChart3 className="h-5 w-5" />
            </span>
            <div>
              <p className="text-lg font-bold leading-tight text-slate-900">DataLab</p>
              <p className="text-[11px] font-medium uppercase tracking-wider text-slate-400">
                Data science workspace
              </p>
            </div>
          </div>

          <div className="card p-6 sm:p-8">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
            {subtitle ? <p className="mt-1 text-sm text-slate-500">{subtitle}</p> : null}
            <div className="mt-6">{children}</div>
          </div>

          {footer ? <div className="mt-6 text-center text-sm text-slate-500">{footer}</div> : null}
        </div>
      </main>
    </div>
  )
}
