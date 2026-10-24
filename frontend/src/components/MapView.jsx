import React, { useEffect } from 'react'
import { MapContainer, TileLayer, Polyline, CircleMarker, Popup, Tooltip, useMap } from 'react-leaflet'
import { CheckpointMarkers } from './CheckpointMarkers'

// Auto-fits map bounds whenever routes update
function MapBoundsUpdater({ routes, origin, destination }) {
  const map = useMap()

  useEffect(() => {
    if (!routes || routes.length === 0) {
      if (origin && destination) {
        map.fitBounds([
          [origin.lat, origin.lon],
          [destination.lat, destination.lon]
        ], { padding: [50, 50] })
      }
      return
    }

    const allCoords = []
    routes.forEach(r => {
      if (r.coordinates && r.coordinates.length > 0) {
        // Sample every 20th point to avoid passing 30,000 points to fitBounds
        const step = Math.max(1, Math.floor(r.coordinates.length / 50))
        for (let i = 0; i < r.coordinates.length; i += step) {
          allCoords.push(r.coordinates[i])
        }
      }
    })

    if (allCoords.length > 0) {
      map.fitBounds(allCoords, { padding: [60, 60], maxZoom: 12 })
    }
  }, [routes, origin, destination, map])

  return null
}

// Tells Leaflet to re-measure whenever the map's container changes size (e.g. the sidebar
// opening or closing), so tiles and layers fill the new area. Coalesced to one call per frame
// because the sidebar animates its width.
function MapResizeWatcher() {
  const map = useMap()

  useEffect(() => {
    let frame = null
    const observer = new ResizeObserver(() => {
      if (frame !== null) return
      frame = requestAnimationFrame(() => {
        frame = null
        map.invalidateSize({ pan: false })
      })
    })
    observer.observe(map.getContainer())
    return () => {
      observer.disconnect()
      if (frame !== null) cancelAnimationFrame(frame)
    }
  }, [map])

  return null
}

function formatDuration(seconds) {
  const hours = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  return `${hours}h ${mins}m`
}

// Hover summary shown on each route line
function RouteSummaryTooltip({ route }) {
  const summary = route.summary || {}
  return (
    <Tooltip sticky direction="top" offset={[0, -8]} className="route-tooltip">
      <div className="space-y-1 text-[11px] min-w-[190px]">
        <div className="flex items-center justify-between gap-3">
          <span className="font-semibold text-white">{route.name}</span>
          <span className={route.is_recommended ? 'text-emerald-400 font-semibold' : 'text-slate-400'}>
            {route.is_recommended ? 'Recommended' : `Rank #${route.rank}`}
          </span>
        </div>
        <div className="text-slate-300 font-mono">
          {route.distance_miles.toFixed(1)} mi | {formatDuration(route.duration_seconds)}
        </div>
        <div className="grid grid-cols-2 gap-x-3 font-mono text-slate-300">
          <span>Severe: <span className="text-red-400">{summary.severe_miles} mi</span></span>
          <span>High: <span className="text-orange-400">{summary.high_miles} mi</span></span>
          <span>Moderate: <span className="text-amber-400">{summary.moderate_miles} mi</span></span>
          <span>Avg risk: {summary.average_risk_score ?? 'n/a'} / 5</span>
        </div>
        {summary.unknown_miles > 0 && (
          <div className="text-slate-400">No forecast: {summary.unknown_miles} mi</div>
        )}
      </div>
    </Tooltip>
  )
}

export function MapView({
  routes,
  selectedRouteId,
  onSelectRoute,
  origin,
  destination,
  children
}) {
  // Default center: continental US
  const defaultCenter = [39.8283, -98.5795]
  const defaultZoom = 4

  const activeRoute = routes?.find(r => r.route_id === selectedRouteId) || routes?.[0]

  // Distinct styling for 3 routes
  const getRouteStyle = (r) => {
    const isSelected = r.route_id === (activeRoute?.route_id)
    const isRecommended = r.is_recommended

    if (isSelected) {
      return {
        color: isRecommended ? '#10b981' : '#38bdf8', // Emerald for recommended, Sky for alternate active
        weight: 5,
        opacity: 0.95,
        dashArray: null
      }
    }

    return {
      color: '#64748b', // Slate for inactive
      weight: 3,
      opacity: 0.5,
      dashArray: '6, 6'
    }
  }

  return (
    <div className="relative w-full h-full min-h-[480px] bg-[#0c0d10] overflow-hidden rounded-lg border border-white/10">
      <MapContainer
        center={defaultCenter}
        zoom={defaultZoom}
        zoomControl={true}
        // Draw route lines and checkpoint markers on one canvas instead of hundreds of SVG nodes
        preferCanvas={true}
        scrollWheelZoom={true}
        className="w-full h-full z-0"
      >
        {/* Esri World Dark Gray Base (Free, keyless, zero watermarks) */}
        <TileLayer
          attribution='&copy; Esri, HERE, Garmin, OpenStreetMap'
          url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
          maxZoom={16}
        />
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
          maxZoom={16}
          opacity={0.8}
        />

        <MapResizeWatcher />

        <MapBoundsUpdater
          routes={routes}
          origin={origin}
          destination={destination}
        />

        {/* 1. Render all 3 routes polylines */}
        {routes && routes.map((r) => {
          const style = getRouteStyle(r)
          return (
            <Polyline
              key={r.route_id}
              positions={r.coordinates}
              pathOptions={style}
              eventHandlers={{
                click: () => onSelectRoute && onSelectRoute(r.route_id)
              }}
            >
              <RouteSummaryTooltip route={r} />
            </Polyline>
          )
        })}

        {/* 2. Checkpoints for every route: others faded, the selected route drawn last (on top) */}
        {routes && routes
          .filter((r) => r.route_id !== activeRoute?.route_id)
          .map((r) => (
            <CheckpointMarkers key={r.route_id} checkpoints={r.checkpoints} routeId={r.route_id} routeName={r.name} muted />
          ))}
        {activeRoute && activeRoute.checkpoints && (
          <CheckpointMarkers
            key={activeRoute.route_id}
            checkpoints={activeRoute.checkpoints}
            routeId={activeRoute.route_id}
            routeName={activeRoute.name}
          />
        )}

        {/* 3. Render Origin & Destination Markers */}
        {origin && (
          <CircleMarker
            center={[origin.lat, origin.lon]}
            radius={8}
            pathOptions={{ color: '#ffffff', fillColor: '#38bdf8', fillOpacity: 1, weight: 2 }}
          >
            <Popup>
              <div className="p-1 text-xs">
                <span className="font-semibold text-white">Origin:</span> {origin.display_name}
              </div>
            </Popup>
          </CircleMarker>
        )}

        {destination && (
          <CircleMarker
            center={[destination.lat, destination.lon]}
            radius={8}
            pathOptions={{ color: '#ffffff', fillColor: '#10b981', fillOpacity: 1, weight: 2 }}
          >
            <Popup>
              <div className="p-1 text-xs">
                <span className="font-semibold text-white">Destination:</span> {destination.display_name}
              </div>
            </Popup>
          </CircleMarker>
        )}

        {/* 4. Children (Heatmap canvas layer) */}
        {children}
      </MapContainer>

      {/* Map Legend Overlay */}
      <div className="absolute top-3 right-3 z-[1000] card-chai p-2.5 text-[11px] text-slate-300 space-y-1.5 shadow-lg pointer-events-auto">
        <div className="font-semibold text-white text-[10px] uppercase tracking-wider border-b border-white/5 pb-1">
          Route & Risk Legend
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3.5 h-1 bg-emerald-500 rounded-sm"></span>
          <span>Recommended Route</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3.5 h-1 bg-sky-400 rounded-sm"></span>
          <span>Selected Route</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3.5 h-1 bg-slate-500 rounded-sm border-dashed"></span>
          <span>Alternative Routes</span>
        </div>
        <div className="border-t border-white/5 pt-1.5 space-y-1">
          <div className="text-[10px] text-slate-400 uppercase tracking-wider">
            Checkpoint Risk
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
            <span>Low</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500"></span>
            <span>Moderate</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-orange-500"></span>
            <span>High</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500"></span>
            <span>Severe</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-red-900 border border-red-700"></span>
            <span className="font-semibold text-red-400">No Travel</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-slate-500"></span>
            <span>Unknown (no forecast)</span>
          </div>
        </div>
      </div>
    </div>
  )
}
