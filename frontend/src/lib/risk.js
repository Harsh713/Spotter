// Risk levels, colours and thresholds shared by the map, heatmap and legends.
// Thresholds mirror the assessment's risk table (backend/truck_routing/services/risk_engine.py).

export const RISK_LEVELS = [
  { score: 1, label: 'Low', color: '#10B981' },
  { score: 2, label: 'Moderate', color: '#F59E0B' },
  { score: 3, label: 'High', color: '#F97316' },
  { score: 4, label: 'Severe', color: '#EF4444' },
  { score: 5, label: 'No Travel', color: '#7F1D1D' }
]

export const UNKNOWN_RISK = { score: null, label: 'Unknown', color: '#64748B' }

export const RISK_COLORS = Object.fromEntries(
  [...RISK_LEVELS, UNKNOWN_RISK].map((level) => [level.label, level.color])
)

export function riskLevelForScore(score) {
  return RISK_LEVELS.find((level) => level.score === score) || UNKNOWN_RISK
}

// Base condition thresholds (before load-weight rules, which only the overall risk includes)
export function classifyWind(mph) {
  if (mph >= 55) return 5
  if (mph >= 45) return 4
  if (mph >= 35) return 3
  if (mph >= 25) return 2
  return 1
}

export function classifyRain(inPerHr) {
  if (inPerHr > 1.0) return 5
  if (inPerHr >= 0.5) return 4
  if (inPerHr >= 0.25) return 3
  if (inPerHr >= 0.1) return 2
  return 1
}

export function classifySnow(inPerHr) {
  if (inPerHr > 3.0) return 5
  if (inPerHr >= 2.0) return 4
  if (inPerHr >= 1.0) return 3
  if (inPerHr >= 0.5) return 2
  return 1
}

// Legend labels per heatmap metric, one per risk level (Low to No Travel)
export const METRIC_LEGENDS = {
  risk: {
    title: 'Overall risk (includes load rules)',
    labels: ['Low', 'Moderate', 'High', 'Severe', 'No Travel']
  },
  wind: {
    title: 'Wind, mph (base thresholds)',
    labels: ['< 25', '25-34', '35-44', '45-54', '55+']
  },
  rain: {
    title: 'Rain, in/hr',
    labels: ['< 0.10', '0.10-0.25', '0.25-0.50', '0.50-1.00', '> 1.00']
  },
  snow: {
    title: 'Snow, in/hr',
    labels: ['< 0.5', '0.5-1.0', '1.0-2.0', '2.0-3.0', '> 3.0']
  }
}
