import React from 'react'

export default function ColumnPicker({
  columns,
  selected,
  onChange,
  label = 'Columns',
  hint,
  emptyMessage = 'No columns available.',
}) {
  const allSelected = columns.length > 0 && selected.length === columns.length

  const toggle = (column) => {
    onChange(
      selected.includes(column)
        ? selected.filter((item) => item !== column)
        : [...selected, column],
    )
  }

  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-slate-700">{label}</span>
        <button
          type="button"
          className="text-xs font-semibold text-brand-600 hover:text-brand-700"
          onClick={() => onChange(allSelected ? [] : [...columns])}
        >
          {allSelected ? 'Clear all' : 'Select all'}
        </button>
      </div>
      <div className="max-h-40 overflow-y-auto rounded-lg border border-slate-300 bg-white p-2">
        {columns.length === 0 ? (
          <p className="px-2 py-1 text-xs text-slate-400">{emptyMessage}</p>
        ) : (
          <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
            {columns.map((column) => (
              <label
                key={column}
                className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm text-slate-700 hover:bg-slate-50"
              >
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                  checked={selected.includes(column)}
                  onChange={() => toggle(column)}
                />
                <span className="truncate">{column}</span>
              </label>
            ))}
          </div>
        )}
      </div>
      {hint ? <p className="mt-1 text-xs text-slate-400">{hint}</p> : null}
    </div>
  )
}
