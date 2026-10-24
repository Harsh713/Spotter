import React from 'react'
import { Chip } from './ui/Chip'
import { ShieldCheck, ShieldAlert, Clock, Navigation, CheckCircle2 } from 'lucide-react'
import { cn } from '../lib/utils'

export function RouteCards({ routes, selectedRouteId, onSelectRoute }) {
  if (!routes || routes.length === 0) return null

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between border-b border-white/5 pb-2">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-white uppercase tracking-wider">
          <Navigation className="w-3.5 h-3.5 text-slate-400" />
          <span>Route Options ({routes.length})</span>
        </div>
        <span className="text-[10px] text-slate-400 font-mono">
          Click card to inspect
        </span>
      </div>

      <div className="space-y-2.5">
        {routes.map((r) => {
          const isSelected = r.route_id === selectedRouteId
          const isRecommended = r.is_recommended
          const summary = r.summary || {}
          const totalMi = r.distance_miles || 1
          const hours = Math.floor(r.duration_seconds / 3600)
          const mins = Math.floor((r.duration_seconds % 3600) / 60)

          // Proportional percentages for the risk progress bar
          const lowPct = ((summary.low_miles || 0) / totalMi) * 100
          const modPct = ((summary.moderate_miles || 0) / totalMi) * 100
          const highPct = ((summary.high_miles || 0) / totalMi) * 100
          const severePct = ((summary.severe_miles || 0) / totalMi) * 100
          const unknownPct = ((summary.unknown_miles || 0) / totalMi) * 100

          return (
            <div
              key={r.route_id}
              onClick={() => onSelectRoute(r.route_id)}
              className={cn(
                'card-chai p-3.5 cursor-pointer transition-all duration-150 relative space-y-2.5',
                isSelected
                  ? 'border-emerald-500/50 bg-[#161a22] ring-1 ring-emerald-500/30'
                  : 'hover:border-white/20'
              )}
            >
              {/* Card Header */}
              <div className="flex items-start justify-between gap-2">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-xs text-slate-400 font-semibold">
                      Option {r.rank}:
                    </span>
                    <h4 className="text-xs font-bold text-white leading-tight">
                      {r.name}
                    </h4>
                  </div>
                  <div className="flex items-center gap-3 text-[11px] text-slate-300 font-mono">
                    <span>{r.distance_miles.toFixed(1)} mi</span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3 text-slate-400" />
                      {hours}h {mins}m
                    </span>
                  </div>
                </div>

                {/* Recommended Badge / Rank */}
                <div>
                  {isRecommended && summary.has_no_travel ? (
                    // Top-ranked but still crosses No Travel conditions: not presented as safe
                    <Chip variant="notravel" size="default">
                      <ShieldAlert className="w-3 h-3" />
                      Least Risky
                    </Chip>
                  ) : isRecommended ? (
                    <Chip variant="recommended" size="default">
                      <ShieldCheck className="w-3 h-3" />
                      Recommended
                    </Chip>
                  ) : (
                    <span className="text-[10px] text-slate-400 font-mono uppercase tracking-wider">
                      Rank #{r.rank}
                    </span>
                  )}
                </div>
              </div>

              {/* Safety Verdict Banner */}
              <div
                className={cn(
                  'p-2 rounded text-[11px] leading-relaxed border',
                  isRecommended && summary.has_no_travel
                    ? 'border-red-500/30 bg-red-950/30 text-red-300'
                    : isRecommended
                      ? 'border-emerald-500/20 bg-emerald-950/20 text-emerald-300'
                      : 'border-white/5 bg-black/30 text-slate-300'
                )}
              >
                <div className="flex items-start gap-1.5">
                  {isRecommended && summary.has_no_travel ? (
                    <ShieldAlert className="w-3.5 h-3.5 text-red-400 shrink-0 mt-0.5" />
                  ) : isRecommended ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                  ) : (
                    <span className="w-1.5 h-1.5 rounded-full bg-slate-500 shrink-0 mt-1.5"></span>
                  )}
                  <span>{r.recommendation_reason}</span>
                </div>
              </div>

              {/* Mileage Breakdown Row */}
              <div className="grid grid-cols-4 gap-1.5 text-center text-[10px] font-mono border-t border-white/5 pt-2">
                <div className="space-y-0.5">
                  <span className="text-slate-400 block text-[9px] uppercase">Severe</span>
                  <span
                    className={cn(
                      'font-semibold block',
                      summary.severe_miles > 0 ? 'text-red-400 font-bold' : 'text-slate-400'
                    )}
                  >
                    {summary.severe_miles} mi
                  </span>
                </div>

                <div className="space-y-0.5 border-l border-white/5">
                  <span className="text-slate-400 block text-[9px] uppercase">High</span>
                  <span
                    className={cn(
                      'font-semibold block',
                      summary.high_miles > 0 ? 'text-orange-400' : 'text-slate-400'
                    )}
                  >
                    {summary.high_miles} mi
                  </span>
                </div>

                <div className="space-y-0.5 border-l border-white/5">
                  <span className="text-slate-400 block text-[9px] uppercase">Moderate</span>
                  <span className="text-amber-400 font-semibold block">
                    {summary.moderate_miles} mi
                  </span>
                </div>

                <div className="space-y-0.5 border-l border-white/5">
                  <span className="text-slate-400 block text-[9px] uppercase">Avg Risk</span>
                  <span className="text-white font-semibold block">
                    {summary.average_risk_score ?? 'n/a'} / 5
                  </span>
                </div>
              </div>

              {/* Stacked Risk Proportion Bar */}
              <div className="w-full h-1.5 rounded-full overflow-hidden flex bg-neutral-800">
                <div style={{ width: `${lowPct}%` }} className="bg-emerald-500" title="Low Risk Miles" />
                <div style={{ width: `${modPct}%` }} className="bg-amber-500" title="Moderate Risk Miles" />
                <div style={{ width: `${highPct}%` }} className="bg-orange-500" title="High Risk Miles" />
                <div style={{ width: `${severePct}%` }} className="bg-red-500" title="Severe Risk Miles" />
                <div style={{ width: `${unknownPct}%` }} className="bg-slate-500" title="Forecast Unavailable Miles" />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
