import React from 'react'
import { cn } from '../../lib/utils'

export function Segmented({ options, value, onChange, className }) {
  return (
    <div
      role="radiogroup"
      className={cn(
        'inline-flex items-center rounded-md border border-white/10 bg-black/40 p-0.5 text-xs',
        className
      )}
    >
      {options.map((opt) => {
        const isSelected = opt.value === value
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={isSelected}
            onClick={() => onChange(opt.value)}
            className={cn(
              'px-2.5 py-1 rounded text-xs font-medium transition-all duration-150 select-none flex items-center gap-1.5',
              isSelected
                ? 'bg-neutral-800 text-white shadow-sm border border-white/10'
                : 'text-slate-400 hover:text-slate-200'
            )}
          >
            {opt.icon && <span className="w-3.5 h-3.5 flex items-center justify-center">{opt.icon}</span>}
            <span>{opt.label}</span>
          </button>
        )
      })}
    </div>
  )
}
