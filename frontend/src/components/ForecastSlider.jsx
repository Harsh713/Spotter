import React, { useEffect, useRef, useState } from 'react'
import { Play, Pause, RotateCcw, Wind, CloudRain, Snowflake, ShieldAlert, Layers, FastForward } from 'lucide-react'
import { Card } from './ui/Card'
import { Button } from './ui/Button'
import { Segmented } from './ui/Segmented'
import { cn } from '../lib/utils'
import { METRIC_LEGENDS, RISK_LEVELS, UNKNOWN_RISK } from '../lib/risk'

function formatTimelineDate(timestamp, hour) {
  if (!timestamp) return `T+${hour}h`
  try {
    const dt = new Date(timestamp)
    const formatted = dt.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
      timeZone: 'UTC'
    })
    return `T+${hour}h | ${formatted} UTC`
  } catch {
    return `T+${hour}h`
  }
}

export function ForecastSlider({
  corridorHeatmap,
  currentHour = 0,
  onHourChange,
  activeMetric = 'risk',
  onMetricChange,
  showHeatmap = true,
  onToggleHeatmap,
  className
}) {
  const [isPlaying, setIsPlaying] = useState(false)
  const [speed, setSpeed] = useState(1) // 1x or 2x
  const timerRef = useRef(null)

  const timestamps = corridorHeatmap?.timestamps || []
  const currentTimestamp = timestamps[currentHour] || null
  const maxHours = 48

  // Automated playback loop
  useEffect(() => {
    if (isPlaying) {
      const intervalMs = speed === 1 ? 400 : 200
      timerRef.current = setInterval(() => {
        onHourChange((prev) => {
          if (prev >= maxHours) {
            return 0
          }
          return prev + 1
        })
      }, intervalMs)
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current)
      }
    }
  }, [isPlaying, speed, onHourChange, maxHours])

  const handleTogglePlay = () => {
    setIsPlaying((prev) => !prev)
  }

  const handleReset = () => {
    setIsPlaying(false)
    onHourChange(0)
  }

  const handleSpeedToggle = () => {
    setSpeed((s) => (s === 1 ? 2 : 1))
  }

  // Metric options for Segmented switcher
  const metricOptions = [
    { value: 'risk', label: 'Overall Risk', icon: <ShieldAlert className="w-3.5 h-3.5 text-red-400" /> },
    { value: 'wind', label: 'Wind', icon: <Wind className="w-3.5 h-3.5 text-amber-400" /> },
    { value: 'rain', label: 'Rain', icon: <CloudRain className="w-3.5 h-3.5 text-sky-400" /> },
    { value: 'snow', label: 'Snow', icon: <Snowflake className="w-3.5 h-3.5 text-cyan-300" /> }
  ]

  const currentLegend = METRIC_LEGENDS[activeMetric] || METRIC_LEGENDS.risk

  return (
    <Card className={cn('card-chai p-3 space-y-2.5 backdrop-blur-md bg-[#0c0d10]/90 shadow-2xl', className)}>
      {/* Top Header: Metric Switcher and Layer Toggles */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-2">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
            Weather Layer
          </span>
          <Segmented
            options={metricOptions}
            value={activeMetric}
            onChange={onMetricChange}
            className="text-xs"
          />
        </div>

        <div className="flex items-center gap-1.5">
          <Button
            variant={showHeatmap ? 'solid' : 'outline'}
            size="sm"
            onClick={onToggleHeatmap}
            className="h-7 px-2 text-[11px] gap-1"
            title="Toggle corridor weather heatmap overlay"
          >
            <Layers className="w-3 h-3" />
            <span>Heatmap {showHeatmap ? 'On' : 'Off'}</span>
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={handleSpeedToggle}
            className="h-7 px-2 text-[11px] gap-1 text-slate-300"
            title="Toggle playback speed"
          >
            <FastForward className="w-3 h-3 text-slate-400" />
            <span>{speed}x</span>
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={handleReset}
            className="h-7 px-2 text-[11px] gap-1 text-slate-300"
            title="Reset to Departure (T+0h)"
          >
            <RotateCcw className="w-3 h-3 text-slate-400" />
            <span>T+0h</span>
          </Button>
        </div>
      </div>

      {/* Center Row: Play Button, Time Scrubber, and Timestamp Display */}
      <div className="flex items-center gap-3">
        <Button
          variant={isPlaying ? 'danger' : 'solid'}
          size="sm"
          onClick={handleTogglePlay}
          className="h-8 w-8 rounded-full p-0 flex items-center justify-center shrink-0 shadow-md"
          title={isPlaying ? 'Pause playback' : 'Play 48-hour forecast animation'}
        >
          {isPlaying ? (
            <Pause className="w-3.5 h-3.5 fill-current" />
          ) : (
            <Play className="w-3.5 h-3.5 fill-current translate-x-0.5" />
          )}
        </Button>

        <div className="flex-1 space-y-1">
          <div className="flex items-center justify-between text-[11px]">
            <span className="font-semibold text-emerald-400 tracking-wide font-mono">
              {formatTimelineDate(currentTimestamp, currentHour)}
            </span>
            <span className="text-slate-400 font-mono text-[10px]">
              Step: {currentHour} / 48 hrs
            </span>
          </div>

          <div className="relative flex items-center">
            <input
              type="range"
              min="0"
              max={maxHours}
              step="1"
              value={currentHour}
              onChange={(e) => onHourChange(Number(e.target.value))}
              className="w-full h-1.5 bg-neutral-800 rounded-lg appearance-none cursor-pointer accent-emerald-400 focus:outline-none focus:ring-1 focus:ring-emerald-400/50"
            />
          </div>

          {/* Time markers */}
          <div className="flex justify-between text-[9px] text-slate-500 font-mono pt-0.5">
            <span>Departure (0h)</span>
            <span>+12h</span>
            <span>+24h (Day 2)</span>
            <span>+36h</span>
            <span>+48h (Day 3)</span>
          </div>
        </div>
      </div>

      {/* Bottom Row: Discrete legend using the risk table thresholds */}
      <div className="space-y-1 pt-1 border-t border-white/5">
        <div className="text-[9px] text-slate-400 uppercase tracking-wider">{currentLegend.title}</div>
        <div className="grid grid-cols-5 gap-1">
          {RISK_LEVELS.map((level, i) => (
            <div key={level.label} className="space-y-0.5">
              <div className="h-1.5 rounded-full" style={{ background: level.color }} title={level.label} />
              <div className="text-[9px] text-slate-400 font-medium text-center">{currentLegend.labels[i]}</div>
            </div>
          ))}
        </div>
        {activeMetric === 'risk' && (
          <div className="flex items-center gap-1.5 text-[9px] text-slate-400">
            <span className="h-1.5 w-4 rounded-full" style={{ background: UNKNOWN_RISK.color }} />
            <span>No forecast</span>
          </div>
        )}
      </div>
    </Card>
  )
}
