import React from 'react'
import { cn } from '../../lib/utils'

export function Chip({
  children,
  variant = 'neutral',
  size = 'default',
  className,
  ...props
}) {
  const variants = {
    neutral: 'border-white/10 text-slate-300 bg-white/5',
    low: 'border-emerald-500/30 text-emerald-400 bg-emerald-500/10',
    moderate: 'border-amber-500/30 text-amber-400 bg-amber-500/10',
    high: 'border-orange-500/30 text-orange-400 bg-orange-500/10',
    severe: 'border-red-500/30 text-red-400 bg-red-500/10',
    notravel: 'border-red-700/50 text-red-300 bg-red-950/40 font-bold',
    recommended: 'border-emerald-400/40 text-emerald-300 bg-emerald-950/30 font-semibold'
  }

  const sizes = {
    sm: 'text-[10px] px-1.5 py-0.2',
    default: 'text-xs px-2 py-0.5',
    lg: 'text-xs px-2.5 py-1'
  }

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded border font-medium uppercase tracking-wider select-none',
        variants[variant],
        sizes[size],
        className
      )}
      {...props}
    >
      {children}
    </span>
  )
}
