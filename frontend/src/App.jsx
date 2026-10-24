import React, { useState, useEffect, useCallback, useRef } from 'react'
import {
  Truck,
  PanelLeftClose,
  PanelLeftOpen,
  Compass,
  RotateCw
} from 'lucide-react'
import { TripForm } from './components/TripForm'
import { RouteCards } from './components/RouteCards'
import { MapView } from './components/MapView'
import { WeatherHeatmap } from './components/WeatherHeatmap'
import { ForecastSlider } from './components/ForecastSlider'
import { Alert } from './components/ui/Alert'
import { Button } from './components/ui/Button'
import { calculateTruckRoutes, checkBackendHealth } from './services/api'

export default function App() {
  const [routesData, setRoutesData] = useState(null)
  // The origin/destination text that produced routesData, so the form can show how each resolved
  const [resolvedQuery, setResolvedQuery] = useState(null)
  const [selectedRouteId, setSelectedRouteId] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  // True while the current trip is being re-sampled at a new interval (route cards stay visible)
  const [isResampling, setIsResampling] = useState(false)
  // Parameters of the last successful calculation, reused when only the interval changes
  const lastParamsRef = useRef(null)
  // Incremented per request so a slower, older response never overwrites a newer one
  const requestIdRef = useRef(0)
  const [error, setError] = useState(null)
  const [backendStatus, setBackendStatus] = useState('checking') // 'online' | 'offline' | 'checking'
  const [sidebarOpen, setSidebarOpen] = useState(true)

  // Forecast slider and heatmap states
  const [currentHour, setCurrentHour] = useState(0)
  const [activeMetric, setActiveMetric] = useState('risk')
  const [showHeatmap, setShowHeatmap] = useState(true)

  const handleCalculateRoutes = useCallback(async (params) => {
    const requestId = ++requestIdRef.current
    setIsLoading(true)
    setIsResampling(false)
    setError(null)

    try {
      const data = await calculateTruckRoutes(params)
      if (requestId !== requestIdRef.current) return
      setRoutesData(data)
      setResolvedQuery({ origin: params.origin, destination: params.destination })
      lastParamsRef.current = params

      // Automatically select the recommended route
      const recommended = data.routes?.find((r) => r.is_recommended)
      if (recommended) {
        setSelectedRouteId(recommended.route_id)
      } else if (data.routes?.length > 0) {
        setSelectedRouteId(data.routes[0].route_id)
      }

      // Reset forecast timeline to departure (T+0h)
      setCurrentHour(0)
    } catch (err) {
      if (requestId !== requestIdRef.current) return
      console.error('Route calculation error:', err)
      setError(err.message || 'Unable to calculate routes. Check backend connectivity.')
    } finally {
      if (requestId === requestIdRef.current) setIsLoading(false)
    }
  }, [])

  // Re-samples the trip already on screen when the checkpoint interval changes. Routes are cached
  // by the backend, so this is fast; the selected route and forecast hour are kept.
  const handleIntervalChange = useCallback(async (interval) => {
    const last = lastParamsRef.current
    if (!last || last.sampling_interval_miles === interval) return

    const params = { ...last, sampling_interval_miles: interval }
    const requestId = ++requestIdRef.current
    setIsResampling(true)
    setError(null)

    try {
      const data = await calculateTruckRoutes(params)
      if (requestId !== requestIdRef.current) return
      setRoutesData(data)
      lastParamsRef.current = params
      setSelectedRouteId((prev) =>
        data.routes?.some((r) => r.route_id === prev)
          ? prev
          : (data.routes?.find((r) => r.is_recommended) || data.routes?.[0])?.route_id ?? null
      )
    } catch (err) {
      if (requestId !== requestIdRef.current) return
      setError(err.message || 'Unable to update checkpoints. Check backend connectivity.')
    } finally {
      if (requestId === requestIdRef.current) setIsResampling(false)
    }
  }, [])

  // Health check on initial load
  useEffect(() => {
    let isMounted = true
    const checkHealth = async () => {
      try {
        const res = await checkBackendHealth()
        if (isMounted) {
          if (res.status === 'healthy') {
            setBackendStatus('online')
          } else {
            setBackendStatus('offline')
          }
        }
      } catch {
        if (isMounted) setBackendStatus('offline')
      }
    }
    checkHealth()
    return () => {
      isMounted = false
    }
  }, [])

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-[#0c0d10] text-slate-100 font-sans">
      {/* Top Navigation Bar */}
      <header className="h-14 shrink-0 border-b border-white/10 bg-[#0c0d10]/95 backdrop-blur-md px-4 flex items-center justify-between z-20">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setSidebarOpen((prev) => !prev)}
            className="h-8 w-8 p-0 text-slate-400 hover:text-white"
            title="Toggle trip panel"
          >
            {sidebarOpen ? (
              <PanelLeftClose className="w-4 h-4" />
            ) : (
              <PanelLeftOpen className="w-4 h-4" />
            )}
          </Button>

          <div className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
              <Truck className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xs font-bold uppercase tracking-wider text-white">
                  Spotter
                </h1>
                <span className="text-[10px] text-slate-400">|</span>
                <span className="text-xs font-medium text-slate-200">
                  Weather-Aware Truck Routing
                </span>
              </div>
              <p className="text-[10px] text-slate-400 hidden md:block">
                Safest route by weather, load weight and travel time
              </p>
            </div>
          </div>
        </div>

        {/* Header Right Actions */}
        <div className="flex items-center gap-2.5">
          {backendStatus === 'online' ? (
            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[11px] font-mono">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              <span>Backend Connected</span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 text-[11px] font-mono">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
              <span>{backendStatus === 'checking' ? 'Checking...' : 'Backend Offline'}</span>
            </div>
          )}
        </div>
      </header>

      {/* Main Workspace Body */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Left trip panel: form, warnings and route cards */}
        <aside
          className={`
            fixed lg:static top-14 bottom-0 left-0 z-30
            w-full sm:w-[460px] lg:w-[480px] shrink-0
            border-r border-white/10 bg-[#0c0d10]
            flex flex-col
            transition-transform duration-300 ease-in-out
            ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:-ml-[480px]'}
          `}
        >
          {/* Scrollable Container */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {/* 1. Trip Form Inputs */}
            <TripForm
              onSubmit={handleCalculateRoutes}
              onIntervalChange={handleIntervalChange}
              isResampling={isResampling}
              isLoading={isLoading}
              error={error}
              resolved={
                routesData && resolvedQuery
                  ? {
                      originQuery: resolvedQuery.origin,
                      destinationQuery: resolvedQuery.destination,
                      origin: routesData.origin?.display_name,
                      destination: routesData.destination?.display_name
                    }
                  : null
              }
            />

            {/* Data quality warnings from the backend (simulated or missing forecasts) */}
            {routesData && !isLoading && routesData.warnings?.map((warning) => (
              <Alert key={warning} variant="warning">
                {warning}
              </Alert>
            ))}

            {/* 2. Loading State */}
            {isLoading && (
              <div className="card-chai p-4 text-center space-y-2 border-emerald-500/30">
                <div className="flex items-center justify-center gap-2 text-emerald-400">
                  <RotateCw className="w-4 h-4 animate-spin" />
                  <span className="text-xs font-semibold uppercase tracking-wider">
                    Analyzing Corridors and Weather
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Querying Open-Meteo forecasts, evaluating wind thresholds by load weight, and ranking optimal routes...
                </p>
              </div>
            )}

            {/* 3. Generated Route Cards */}
            {routesData && !isLoading && (
              <div className="space-y-4 pt-1">
                <RouteCards
                  routes={routesData.routes}
                  selectedRouteId={selectedRouteId}
                  onSelectRoute={setSelectedRouteId}
                />
              </div>
            )}
          </div>
        </aside>

        {/* Map, corridor heatmap and forecast slider */}
        <main className="flex-1 relative h-full bg-[#090a0d] overflow-hidden">
          {/* Leaflet Map */}
          <MapView
            routes={routesData?.routes}
            selectedRouteId={selectedRouteId}
            onSelectRoute={setSelectedRouteId}
            origin={routesData?.origin}
            destination={routesData?.destination}
          >
            {/* Canvas-based corridor weather heatmap */}
            {routesData?.corridor_heatmap && (
              <WeatherHeatmap
                corridorHeatmap={routesData.corridor_heatmap}
                currentHour={currentHour}
                activeMetric={activeMetric}
                visible={showHeatmap}
              />
            )}
          </MapView>

          {/* Floating Bottom Forecast Timeline Scrubber */}
          {routesData?.corridor_heatmap && (
            <div className="absolute bottom-4 left-4 right-4 md:left-6 md:right-6 lg:left-8 lg:right-8 z-[1000] max-w-3xl mx-auto pointer-events-auto">
              <ForecastSlider
                corridorHeatmap={routesData.corridor_heatmap}
                currentHour={currentHour}
                onHourChange={setCurrentHour}
                activeMetric={activeMetric}
                onMetricChange={setActiveMetric}
                showHeatmap={showHeatmap}
                onToggleHeatmap={() => setShowHeatmap((prev) => !prev)}
              />
            </div>
          )}

          {/* Empty State Overlay when no routes loaded */}
          {!routesData && !isLoading && (
            <div className="absolute inset-0 flex items-center justify-center p-6 pointer-events-none z-[1000]">
              <div className="card-chai max-w-sm p-6 text-center space-y-3 shadow-2xl pointer-events-auto bg-[#0c0d10]/95 backdrop-blur-md">
                <div className="h-10 w-10 mx-auto rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                  <Compass className="w-5 h-5" />
                </div>
                <div className="space-y-1">
                  <h3 className="text-sm font-semibold text-white">
                    Plan a Trip
                  </h3>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    Configure origin, destination, load weight, and departure schedule in the left drawer, then click Calculate Safe Routes.
                  </p>
                </div>
                <Button
                  variant="solid"
                  size="sm"
                  onClick={() =>
                    handleCalculateRoutes({
                      origin: 'Chicago, IL',
                      destination: 'Denver, CO',
                      departure_time: new Date().toISOString(),
                      load_weight_lbs: 42000,
                      sampling_interval_miles: 25,
                      scenario: 'live'
                    })
                  }
                  className="w-full text-xs"
                >
                  Load Demo Corridor (Chicago to Denver)
                </Button>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
