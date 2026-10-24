import React from 'react'
import { cn } from '../../lib/utils'

export function Button({
  className,
  variant = 'solid',
  size = 'default',
  type = 'button',
  disabled = false,
  children,
  ...props
}) {
  const baseStyles = 'inline-flex items-center justify-center font-medium transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 disabled:pointer-events-none disabled:opacity-50 select-none'

  const variants = {
    solid: 'bg-white text-slate-950 hover:bg-slate-200 active:bg-slate-300 rounded-md font-semibold text-xs shadow-sm',
    outline: 'border border-white/10 bg-white/5 text-slate-100 hover:bg-white/10 hover:border-white/20 active:bg-white/15 rounded-md text-xs',
    ghost: 'text-slate-300 hover:text-white hover:bg-white/5 active:bg-white/10 rounded-md text-xs',
    danger: 'border border-red-500/20 bg-red-500/10 text-red-400 hover:bg-red-500/20 rounded-md text-xs'
  }

  const sizes = {
    sm: 'h-7 px-2.5 text-xs',
    default: 'h-9 px-3.5 text-xs',
    lg: 'h-10 px-5 text-sm'
  }

  return (
    <button
      type={type}
      disabled={disabled}
      className={cn(baseStyles, variants[variant], sizes[size], className)}
      {...props}
    >
      {children}
    </button>
  )
}
