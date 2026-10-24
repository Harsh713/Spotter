import React, { useState } from 'react'
import { Card, CardBody, CardTitle } from './ui/Card'
import { Button } from './ui/Button'
import { Input } from './ui/Input'
import { Segmented } from './ui/Segmented'
import { Chip } from './ui/Chip'
import { Alert } from './ui/Alert'
import { PRESET_SCENARIOS } from '../services/api'
import {
  MapPin,
  Calendar,
  Scale,
  Sliders,
  Play,
  Loader2,
  AlertTriangle,
  Navigation
} from 'lucide-react'

// Departures must fall within the forecast window the backend accepts (now to 5 days ahead)
const MAX_DEPARTURE_DAYS_AHEAD = 5

// Formats a Date as local time for a datetime-local input
function toLocalInputValue(d) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// Default departure: next whole hour, local time
function getDefaultDateTime() {
  const d = new Date()
  d.setHours(d.getHours() + 1, 0, 0, 0)
  return toLocalInputValue(d)
}

function getDepartureBounds() {
  const now = new Date()
  const max = new Date(now.getTime() + MAX_DEPARTURE_DAYS_AHEAD * 24 * 3600 * 1000)
  return { min: toLocalInputValue(now), max: toLocalInputValue(max) }
}

// Shows which place a location query resolved to, while the input still holds that query
function ResolvedPlace({ query, value, name }) {
  if (!name || !query || value.trim() !== query.trim()) return null
  return (
    <p className="text-[10px] text-slate-400 truncate" title={name}>
      Resolved: <span className="text-slate-300">{name}</span>
    </p>
  )
}

export function TripForm({ onSubmit, onIntervalChange, isResampling, isLoading, error, resolved }) {
  const [origin, setOrigin] = useState('Chicago, IL')
  const [destination, setDestination] = useState('Denver, CO')
  const [departureTime, setDepartureTime] = useState(getDefaultDateTime)
  const [loadWeightLbs, setLoadWeightLbs] = useState(42000)
  const [samplingInterval, setSamplingInterval] = useState(25)
  const [scenario, setScenario] = useState('live')
  const [isLocating, setIsLocating] = useState(false)
  const [locatingError, setLocatingError] = useState(null)

  const handleUseCurrentLocation = () => {
    if (!navigator.geolocation) {
      setLocatingError('Geolocation is not supported by your browser')
      return
    }

    setIsLocating(true)
    setLocatingError(null)

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setIsLocating(false)
        const lat = pos.coords.latitude.toFixed(4)
        const lon = pos.coords.longitude.toFixed(4)
        setOrigin(`${lat}, ${lon}`)
      },
      (err) => {
        setIsLocating(false)
        setLocatingError(`Unable to retrieve GPS: ${err.message}`)
      },
      { timeout: 10000, enableHighAccuracy: true }
    )
  }

  const handlePresetSelect = (preset) => {
    setOrigin(preset.origin)
    setDestination(preset.destination)
    setLoadWeightLbs(preset.load_weight_lbs)
    setSamplingInterval(preset.sampling_interval_miles)
    setScenario(preset.scenario)
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!origin.trim() || !destination.trim()) return

    onSubmit({
      origin: origin.trim(),
      destination: destination.trim(),
      departure_time: new Date(departureTime).toISOString(),
      load_weight_lbs: Number(loadWeightLbs),
      sampling_interval_miles: Number(samplingInterval),
      scenario
    })
  }

  // Weight rule helper indicator
  const getWeightBracketInfo = () => {
    const w = Number(loadWeightLbs)
    if (w > 40000) {
      return {
        variant: 'severe',
        label: '>40,000 lb Bracket',
        rule: '35-44 mph wind escalates to Severe'
      }
    }
    if (w > 30000) {
      return {
        variant: 'high',
        label: '30,000-40,000 lb Bracket',
        rule: '45-54 mph wind escalates to No Travel'
      }
    }
    return {
      variant: 'low',
      label: '<30,000 lb (Standard)',
      rule: 'Baseline wind rules apply'
    }
  }

  const weightInfo = getWeightBracketInfo()

  return (
    <Card className="w-full">
      <CardBody className="p-4 space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/5 pb-2.5">
          <div className="flex items-center gap-2">
            <Sliders className="w-4 h-4 text-slate-400" />
            <CardTitle>Trip Parameters</CardTitle>
          </div>
        </div>

        {/* 1-Click Freight Corridor Presets */}
        <div className="space-y-1.5">
          <label className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">
            Corridor Presets
          </label>
          <div className="flex flex-wrap gap-1.5">
            {PRESET_SCENARIOS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => handlePresetSelect(p)}
                className="px-2 py-1 rounded border border-white/10 bg-white/5 text-[11px] text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
              >
                {p.title}
              </button>
            ))}
          </div>
        </div>

        {/* Input Form */}
        <form onSubmit={handleSubmit} className="space-y-3.5">
          {/* Origin & Destination */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <label className="text-[11px] text-slate-400 flex items-center gap-1">
                  <MapPin className="w-3 h-3 text-slate-400" />
                  Origin
                </label>
                <button
                  type="button"
                  onClick={handleUseCurrentLocation}
                  disabled={isLocating}
                  className="text-[10px] text-emerald-400 hover:text-emerald-300 flex items-center gap-1 underline transition-colors"
                  title="Detect coordinates from browser GPS"
                >
                  <Navigation className="w-2.5 h-2.5" />
                  <span>{isLocating ? 'Locating...' : 'Use Live GPS'}</span>
                </button>
              </div>
              <Input
                value={origin}
                onChange={(e) => setOrigin(e.target.value)}
                placeholder="City, State or Coordinates"
                required
              />
              <ResolvedPlace query={resolved?.originQuery} value={origin} name={resolved?.origin} />
            </div>

            <div className="space-y-1">
              <label className="text-[11px] text-slate-400 flex items-center gap-1">
                <MapPin className="w-3 h-3 text-emerald-400" />
                Destination
              </label>
              <Input
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
                placeholder="City, State or Coordinates"
                required
              />
              <ResolvedPlace query={resolved?.destinationQuery} value={destination} name={resolved?.destination} />
            </div>
          </div>

          {locatingError && (
            <p className="text-[10px] text-red-400 font-mono">
              {locatingError}
            </p>
          )}

          <p className="text-[10px] text-slate-400 font-mono">
            Enter a city and state (e.g. Chicago, IL), a ZIP code, or coordinates. US matches are preferred; add a country for places abroad (e.g. Toronto, Canada). Routes must be drivable by road.
          </p>

          {/* Departure Date/Time */}
          <div className="space-y-1">
            <label className="text-[11px] text-slate-400 flex items-center gap-1">
              <Calendar className="w-3 h-3 text-slate-400" />
              Departure Date & Time
            </label>
            <Input
              type="datetime-local"
              value={departureTime}
              min={getDepartureBounds().min}
              max={getDepartureBounds().max}
              onChange={(e) => setDepartureTime(e.target.value)}
              required
            />
          </div>

          {/* Load Weight with Dynamic Rule Trigger Display */}
          <div className="space-y-1.5 border border-white/5 rounded-md p-2.5 bg-black/20">
            <div className="flex items-center justify-between text-xs">
              <label className="text-[11px] text-slate-400 flex items-center gap-1">
                <Scale className="w-3 h-3 text-slate-400" />
                Load Weight
              </label>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-semibold text-white">
                  {Number(loadWeightLbs).toLocaleString()} lbs
                </span>
                <Chip variant={weightInfo.variant} size="sm">
                  {weightInfo.label}
                </Chip>
              </div>
            </div>

            <input
              type="range"
              min="0"
              max="80000"
              step="1000"
              value={loadWeightLbs}
              onChange={(e) => setLoadWeightLbs(Number(e.target.value))}
              className="w-full h-1.5 bg-neutral-800 rounded-lg appearance-none cursor-pointer accent-white"
            />

            <p className="text-[10px] text-slate-400 font-mono">
              Applied Rule: {weightInfo.rule}
            </p>
          </div>

          {/* Sampling Interval Selector */}
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <label className="text-[11px] text-slate-400">
                Weather Sampling Interval
              </label>
              <span className={`text-[10px] ${isResampling ? 'text-emerald-400' : 'text-slate-400'}`}>
                {isResampling ? 'Updating checkpoints...' : 'Checkpoints spaced along corridor'}
              </span>
            </div>
            <Segmented
              className="w-full grid grid-cols-3 text-center"
              options={[
                { label: 'Every 10 mi', value: 10 },
                { label: 'Every 25 mi', value: 25 },
                { label: 'Every 50 mi', value: 50 }
              ]}
              value={samplingInterval}
              onChange={(value) => {
                setSamplingInterval(value)
                // Applies immediately to the trip already on screen
                onIntervalChange?.(Number(value))
              }}
            />
          </div>

          {/* Weather Mode / Scenario Toggle */}
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <label className="text-[11px] text-slate-400">
                Weather Mode
              </label>
              <span className="text-[10px] text-slate-400">
                Live Open-Meteo or Demo Scenarios
              </span>
            </div>
            <Segmented
              className="w-full grid grid-cols-4 text-center"
              options={[
                { label: 'Live', value: 'live' },
                { label: 'High Wind', value: 'high_wind' },
                { label: 'Blizzard', value: 'blizzard' },
                { label: 'Rainstorm', value: 'rainstorm' }
              ]}
              value={scenario}
              onChange={setScenario}
            />
          </div>

          {/* Error Notice */}
          {error && (
            <Alert variant="danger" icon={<AlertTriangle className="w-3.5 h-3.5" />}>
              {error}
            </Alert>
          )}

          {/* Submit Button */}
          <Button
            type="submit"
            disabled={isLoading}
            variant="solid"
            className="w-full h-9 flex items-center justify-center gap-2 mt-2"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Analyzing 3 Routes & Weather...</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Analyze Routes & Weather</span>
              </>
            )}
          </Button>
        </form>
      </CardBody>
    </Card>
  )
}
