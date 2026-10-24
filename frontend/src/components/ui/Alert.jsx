import React from 'react'
import { cn } from '../../lib/utils'

export function Alert({
  children,
  variant = 'warning',
  className,
  icon,
  ...props
}) {
  const variants = {
    info: 'border-blue-500/30 text-blue-300 bg-blue-950/20',
    warning: 'border-amber-500/30 text-amber-300 bg-amber-950/20',
    danger: 'border-red-500/40 text-red-300 bg-red-950/30'
  }

  return (
    <div
      role="alert"
      className={cn(
        'flex items-start gap-2.5 rounded-md border p-2.5 text-xs leading-relaxed',
        variants[variant],
        className
      )}
      {...props}
    >
      {icon && <span className="mt-0.5 shrink-0">{icon}</span>}
      <div className="flex-1">{children}</div>
    </div>
  )
}
