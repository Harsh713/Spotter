import React from 'react'
import { CircleMarker, Popup } from 'react-leaflet'
import { Chip } from './ui/Chip'
import { Alert } from './ui/Alert'
import { Wind, CloudRain, Snowflake, Clock, AlertTriangle } from 'lucide-react'
import { RISK_COLORS } from '../lib/risk'

const formatReading = (value, unit) => (value === null || value === undefined ? 'n/a' : `${value} ${unit}`)

const CHIP_VARIANTS = {
  Low: 'low',
  Moderate: 'moderate',
  High: 'high',
  Severe: 'severe',
  'No Travel': 'notravel'
}

// `muted` renders a route's checkpoints small and faded, for routes other than the selected one
export function CheckpointMarkers({ checkpoints, routeId, routeName, muted = false }) {
  if (!checkpoints || checkpoints.length === 0) return null

  return (
    <>
      {checkpoints.map((chk, idx) => {
        const risk = chk.risk || {}
        const weather = chk.weather || {}
        const overallRisk = risk.overall_risk || 'Low'
        const fillColor = RISK_COLORS[overallRisk] || RISK_COLORS.Unknown
        const isEnd = idx === 0 || idx === checkpoints.length - 1

        return (
          <CircleMarker
            key={`chk-${routeId}-${idx}-${chk.mile_marker}`}
            center={[chk.lat, chk.lon]}
            radius={muted ? 3.5 : isEnd ? 7 : 5}
            pathOptions={{
              color: '#ffffff',
              opacity: muted ? 0.5 : 1,
              weight: muted ? 1 : isEnd ? 2 : 1.5,
              fillColor,
              fillOpacity: muted ? 0.55 : 0.95
            }}
          >
            <Popup className="chai-popup" minWidth={260} maxWidth={320}>
              <div className="card-chai p-3 space-y-2.5 text-xs text-slate-100">
                {routeName && (
                  <div className="text-[10px] uppercase tracking-wider text-slate-400">{routeName}</div>
                )}
                {/* Header with Mile Marker and Risk Chip */}
                <div className="flex items-center justify-between border-b border-white/10 pb-2">
                  <div className="flex items-center gap-1.5 font-semibold text-white">
                    <span className="font-mono text-xs text-slate-300">
                      Mile {chk.mile_marker.toFixed(1)}
                    </span>
                    {isEnd && (
                      <span className="text-[10px] text-slate-400 font-normal">
                        ({idx === 0 ? 'Origin' : 'Destination'})
                      </span>
                    )}
                  </div>
                  <Chip variant={CHIP_VARIANTS[overallRisk] || 'neutral'} size="sm">
                    {overallRisk}
                  </Chip>
                </div>

                {/* ETA Details */}
                <div className="flex items-center gap-1.5 text-slate-300">
                  <Clock className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  <span>ETA:</span>
                  <span className="font-mono font-medium text-white">
                    {chk.eta_display}
                  </span>
                  <span className="text-slate-400 text-[10px]">
                    (+{chk.elapsed_time_display})
                  </span>
                </div>

                {/* Weather Metrics Grid */}
                <div className="grid grid-cols-3 gap-1.5 p-2 rounded bg-black/40 border border-white/5 text-center">
                  <div className="space-y-0.5">
                    <div className="flex items-center justify-center gap-1 text-[10px] text-slate-400">
                      <Wind className="w-3 h-3 text-sky-400" />
                      <span>Wind</span>
                    </div>
                    <div className="font-mono text-xs font-semibold text-white">
                      {formatReading(weather.wind_speed_mph, 'mph')}
                    </div>
                    <div className="text-[9px] text-slate-400">
                      {risk.wind_risk || 'Low'}
                    </div>
                  </div>

                  <div className="space-y-0.5 border-x border-white/5">
                    <div className="flex items-center justify-center gap-1 text-[10px] text-slate-400">
                      <CloudRain className="w-3 h-3 text-blue-400" />
                      <span>Rain</span>
                    </div>
                    <div className="font-mono text-xs font-semibold text-white">
                      {formatReading(weather.rain_in_per_hr, 'in/h')}
                    </div>
                    <div className="text-[9px] text-slate-400">
                      {risk.rain_risk || 'Low'}
                    </div>
                  </div>

                  <div className="space-y-0.5">
                    <div className="flex items-center justify-center gap-1 text-[10px] text-slate-400">
                      <Snowflake className="w-3 h-3 text-indigo-300" />
                      <span>Snow</span>
                    </div>
                    <div className="font-mono text-xs font-semibold text-white">
                      {formatReading(weather.snow_in_per_hr, 'in/h')}
                    </div>
                    <div className="text-[9px] text-slate-400">
                      {risk.snow_risk || 'Low'}
                    </div>
                  </div>
                </div>

                {/* Condition Summary */}
                <div className="flex items-center justify-between text-[11px] text-slate-400 px-0.5">
                  <span>Condition:</span>
                  <span className="text-slate-200 font-medium">
                    {weather.condition || 'Clear'}
                    {weather.temperature_f !== null && weather.temperature_f !== undefined && ` (${weather.temperature_f} F)`}
                  </span>
                </div>

                {/* Load Rule Trigger Alert */}
                {risk.load_rule_applied && (
                  <Alert variant="danger" icon={<AlertTriangle className="w-3.5 h-3.5 text-red-400" />}>
                    <p className="text-[10px] font-medium leading-tight">
                      {risk.load_rule_description}
                    </p>
                  </Alert>
                )}
              </div>
            </Popup>
          </CircleMarker>
        )
      })}
    </>
  )
}
