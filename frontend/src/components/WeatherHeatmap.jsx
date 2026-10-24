import { useEffect, useRef } from 'react'
import L from 'leaflet'
import { useMap } from 'react-leaflet'
import { RISK_LEVELS, UNKNOWN_RISK, classifyWind, classifyRain, classifySnow } from '../lib/risk'

// Station radius in miles. Stations are ~25 mi apart, so this radius makes them blend into a
// continuous corridor at every zoom level.
const STATION_RADIUS_MILES = 18
const MILES_PER_DEGREE_LAT = 69
const LEVEL_INTENSITY = { 1: 0.35, 2: 0.55, 3: 0.7, 4: 0.8, 5: 0.9 }

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16)
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 }
}

const LEVEL_RGB = Object.fromEntries(RISK_LEVELS.map((level) => [level.score, hexToRgb(level.color)]))
const UNKNOWN_RGB = hexToRgb(UNKNOWN_RISK.color)

// Colour for one station at one hour, classified with the same thresholds as the risk table.
// Returns null when there is nothing to draw (no precipitation, or no reading for that metric).
function getMetricColor(activeMetric, pt, hour) {
  if (activeMetric === 'risk') {
    const score = pt.risk?.[hour]
    if (score === null || score === undefined) return { ...UNKNOWN_RGB, intensity: 0.3 }
    return { ...LEVEL_RGB[score], intensity: LEVEL_INTENSITY[score] }
  }

  const value = pt[activeMetric]?.[hour]
  if (value === null || value === undefined) return null
  if ((activeMetric === 'rain' || activeMetric === 'snow') && value <= 0) return null

  const classify = { wind: classifyWind, rain: classifyRain, snow: classifySnow }[activeMetric]
  if (!classify) return null
  const level = classify(value)
  return { ...LEVEL_RGB[level], intensity: LEVEL_INTENSITY[level] }
}

export function WeatherHeatmap({
  corridorHeatmap,
  currentHour = 0,
  activeMetric = 'risk',
  visible = true,
  opacity = 0.70
}) {
  const map = useMap()
  const canvasRef = useRef(null)

  // Keep latest props in ref so canvas listeners don't rebind on every slider tick
  const stateRef = useRef({
    corridorHeatmap,
    currentHour,
    activeMetric,
    visible,
    opacity
  })

  useEffect(() => {
    stateRef.current = {
      corridorHeatmap,
      currentHour,
      activeMetric,
      visible,
      opacity
    }
  }, [corridorHeatmap, currentHour, activeMetric, visible, opacity])

  useEffect(() => {
    const container = map.getContainer()
    if (!container) return

    // Own map pane between the tiles (200) and the route lines (400) so the heatmap is drawn
    // above the basemap. The pane moves with the map, so the canvas is re-anchored on every draw.
    const pane = map.getPane('corridorHeatmap') || map.createPane('corridorHeatmap')
    pane.style.zIndex = '350'
    pane.style.pointerEvents = 'none'

    const canvas = document.createElement('canvas')
    // leaflet-zoom-hide hides the canvas during zoom animations; it is redrawn on zoomend
    canvas.className = 'leaflet-corridor-heatmap-layer leaflet-zoom-hide'
    canvas.style.position = 'absolute'
    canvas.style.pointerEvents = 'none'
    pane.appendChild(canvas)
    canvasRef.current = canvas

    // Pre-rendered radial gradient per colour and size; rebuilt only when zoom changes the radius
    const sprites = new Map()
    const getSprite = (color, radius, userOpacity, dpr) => {
      const key = `${color.r},${color.g},${color.b},${color.intensity},${radius.toFixed(1)},${userOpacity},${dpr}`
      let sprite = sprites.get(key)
      if (!sprite) {
        if (sprites.size > 200) sprites.clear()
        const size = Math.ceil(radius * 2 * dpr)
        sprite = document.createElement('canvas')
        sprite.width = size
        sprite.height = size
        const sctx = sprite.getContext('2d')
        const c = size / 2
        const alpha = color.intensity * Math.max(0.1, Math.min(1.0, userOpacity))
        const grad = sctx.createRadialGradient(c, c, 0, c, c, c)
        grad.addColorStop(0, `rgba(${color.r}, ${color.g}, ${color.b}, ${alpha})`)
        grad.addColorStop(0.35, `rgba(${color.r}, ${color.g}, ${color.b}, ${alpha * 0.65})`)
        grad.addColorStop(0.75, `rgba(${color.r}, ${color.g}, ${color.b}, ${alpha * 0.2})`)
        grad.addColorStop(1, `rgba(${color.r}, ${color.g}, ${color.b}, 0)`)
        sctx.fillStyle = grad
        sctx.fillRect(0, 0, size, size)
        sprites.set(key, sprite)
      }
      return sprite
    }

    const draw = () => {
      if (!canvas) return
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      const { corridorHeatmap: heatmap, currentHour: hour, activeMetric: metric, visible: isVisible, opacity: userOpacity } = stateRef.current

      const rect = container.getBoundingClientRect()
      const dpr = window.devicePixelRatio || 1

      // Pin the canvas to the viewport's top-left corner inside the panning map pane
      L.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([0, 0]))
      canvas.style.width = `${rect.width}px`
      canvas.style.height = `${rect.height}px`

      // Ensure canvas resolution matches display
      const targetW = Math.round(rect.width * dpr)
      const targetH = Math.round(rect.height * dpr)
      if (canvas.width !== targetW || canvas.height !== targetH) {
        canvas.width = targetW
        canvas.height = targetH
      }

      ctx.save()
      ctx.scale(dpr, dpr)
      ctx.clearRect(0, 0, rect.width, rect.height)

      if (!isVisible || !heatmap || !heatmap.points || heatmap.points.length === 0) {
        ctx.restore()
        return
      }

      // Convert the station radius from miles to pixels at the current zoom and map centre
      const center = map.getCenter()
      const radiusPx = Math.abs(
        map.latLngToContainerPoint([center.lat + STATION_RADIUS_MILES / MILES_PER_DEGREE_LAT, center.lng]).y -
        map.latLngToContainerPoint(center).y
      )
      const radius = Math.max(10, Math.min(160, radiusPx))
      const hourIndex = Math.max(0, Math.min(48, Math.round(hour)))

      heatmap.points.forEach((pt) => {
        const color = getMetricColor(metric, pt, hourIndex)
        if (!color) return

        const containerPt = map.latLngToContainerPoint([pt.lat, pt.lon])

        // Skip points outside canvas viewport plus margin
        if (
          containerPt.x < -radius ||
          containerPt.x > rect.width + radius ||
          containerPt.y < -radius ||
          containerPt.y > rect.height + radius
        ) {
          return
        }

        const sprite = getSprite(color, radius, userOpacity, dpr)
        ctx.drawImage(sprite, containerPt.x - radius, containerPt.y - radius, radius * 2, radius * 2)
      })

      ctx.restore()
    }

    // Coalesce bursts of pan events and slider updates into at most one draw per animation frame
    let frame = null
    const scheduleDraw = () => {
      if (frame !== null) return
      frame = requestAnimationFrame(() => {
        frame = null
        draw()
      })
    }

    map.on('move', scheduleDraw)
    map.on('zoomend', draw)
    map.on('resize', scheduleDraw)

    // Initial draw
    draw()

    // Store draw trigger so state updates can directly invoke it
    canvas._triggerDraw = scheduleDraw

    return () => {
      if (frame !== null) cancelAnimationFrame(frame)
      map.off('move', scheduleDraw)
      map.off('zoomend', draw)
      map.off('resize', scheduleDraw)
      if (canvas.parentNode) {
        canvas.parentNode.removeChild(canvas)
      }
    }
  }, [map])

  // Re-draw whenever hour, metric, or heatmap updates
  useEffect(() => {
    if (canvasRef.current && canvasRef.current._triggerDraw) {
      canvasRef.current._triggerDraw()
    }
  }, [corridorHeatmap, currentHour, activeMetric, visible, opacity])

  return null
}
