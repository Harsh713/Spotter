import React from 'react'
import { cn } from '../../lib/utils'

export function Card({ className, ...props }) {
  return (
    <div
      data-slot="card"
      className={cn(
        'card-chai group relative flex flex-col overflow-hidden text-slate-100',
        className
      )}
      {...props}
    />
  )
}

export function CardBody({ className, ...props }) {
  return (
    <div
      data-slot="card-body"
      className={cn('flex min-w-0 flex-1 flex-col gap-1.5 p-4', className)}
      {...props}
    />
  )
}

export function CardTitle({ className, ...props }) {
  return (
    <h3
      data-slot="card-title"
      className={cn('text-sm font-semibold tracking-tight text-white', className)}
      {...props}
    />
  )
}

export function CardText({ className, ...props }) {
  return (
    <p
      data-slot="card-text"
      className={cn('text-xs leading-relaxed text-slate-400', className)}
      {...props}
    />
  )
}

export function CardFooter({ className, ...props }) {
  return (
    <div
      data-slot="card-footer"
      className={cn('mt-auto flex items-center justify-between gap-3 border-t border-white/5 pt-3', className)}
      {...props}
    />
  )
}
