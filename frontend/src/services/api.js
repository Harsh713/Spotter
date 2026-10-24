const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

export const PRESET_SCENARIOS = [
  {
    id: 'chicago-denver',
    title: 'Chicago to Denver',
    subtitle: 'I-80 corridor (High wind and mountain snow)',
    origin: 'Chicago, IL',
    destination: 'Denver, CO',
    load_weight_lbs: 42000,
    sampling_interval_miles: 25,
    scenario: 'live'
  },
  {
    id: 'seattle-dallas',
    title: 'Seattle to Dallas',
    subtitle: 'Long-haul freight cross-country',
    origin: 'Seattle, WA',
    destination: 'Dallas, TX',
    load_weight_lbs: 35000,
    sampling_interval_miles: 50,
    scenario: 'live'
  },
  {
    id: 'minneapolis-nyc',
    title: 'Minneapolis to New York',
    subtitle: 'Northern interstate to East Coast',
    origin: 'Minneapolis, MN',
    destination: 'New York, NY',
    load_weight_lbs: 45000,
    sampling_interval_miles: 25,
    scenario: 'live'
  }
]

export async function checkBackendHealth() {
  try {
    const res = await fetch(`${API_BASE_URL}/health/`)
    if (!res.ok) throw new Error(`Health check failed with status: ${res.status}`)
    return await res.json()
  } catch (err) {
    console.error('Backend health check error:', err)
    return { status: 'offline', error: err.message }
  }
}

export async function calculateTruckRoutes(params) {
  const payload = {
    origin: params.origin,
    destination: params.destination,
    departure_time: params.departure_time || new Date().toISOString(),
    load_weight_lbs: Number(params.load_weight_lbs) || 40000,
    sampling_interval_miles: Number(params.sampling_interval_miles) || 25,
    scenario: params.scenario || 'live'
  }

  const res = await fetch(`${API_BASE_URL}/routes/calculate/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  })

  const data = await res.json()

  if (!res.ok) {
    let errorMsg = data.message || 'Failed to calculate truck routes'
    if (data.errors) {
      const details = Object.entries(data.errors)
        .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
        .join(' | ')
      errorMsg = `${errorMsg} (${details})`
    }
    throw new Error(errorMsg)
  }

  return data
}
