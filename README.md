# Weather-Aware Truck Routing

A React + Django web app that helps a truck driver choose the safest route. It compares up to three road routes, samples the weather forecast at each checkpoint for the time the truck will actually be there, classifies risk with the assessment's weather and load-weight rules, and recommends the route that balances weather risk and travel time.

- **Hosted app:** _add URL_
- **Loom walkthrough:** _add link_

## Features

- **Trip input:** origin and destination (city and state, city and country, ZIP/postal code, or `lat, lon`), departure date and time, and load weight.
- **Three route options** from the OSRM routing API: OSRM's own alternatives first, then detours through waypoints on either side of the trip. Near-duplicate and unrealistically long alternatives are rejected, and routes are never invented. If a trip has fewer distinct road options, fewer routes are shown with a warning.
- **Checkpoints every 10, 25 or 50 miles.** Each checkpoint's ETA is the departure time plus OSRM's per-segment travel time to that point. Changing the interval re-samples the current trip immediately, without pressing Analyze.
- **Weather at each checkpoint's ETA** from the Open-Meteo hourly forecast: wind, rain (large-scale plus convective showers) and snowfall.
- **Risk classification** per checkpoint using the risk table and load rules below. The overall risk is the worst of wind, rain and snow.
- **Recommendation** using the four-tier ranking: fewest Severe miles, then fewest High miles, then lowest average risk, then shortest travel time. If every route crosses No Travel conditions, the top route is labelled "Least Risky" and the app advises delaying departure.
- **Map** (Leaflet) showing all routes, checkpoints for every route colour-coded by risk, checkpoint popups (ETA, readings, load rule applied) and a summary for each route on hover.
- **Corridor weather heatmap with a 0-48 hour forecast slider.** Stations every 25 miles along every route, with layers for overall risk, wind, rain and snow, plus play/pause. Colours use the same thresholds as the risk table.
- **Honest data handling.** A checkpoint with no forecast (weather service error, or an ETA beyond the 7-day forecast) is shown as **Unknown**, never as Low, and the API returns warnings that the UI displays.
- **Demo scenarios** (High Wind, Blizzard, Rainstorm) replace live weather with one simulated storm, so the risk rules and ranking can be demonstrated even when live weather is calm. Results are clearly labelled as simulated.

## Risk rules

Each condition is classified separately; a checkpoint's overall risk is the most severe of the three.

| Condition | Low | Moderate | High | Severe | No Travel |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Wind | < 25 mph | 25-34 | 35-44 | 45-54 | >= 55 mph |
| Rain | < 0.10 in/hr | 0.10-0.25 | 0.25-0.50 | 0.50-1.00 | > 1.00 |
| Snow | < 0.5 in/hr | 0.5-1.0 | 1.0-2.0 | 2.0-3.0 | > 3.0 |

**Load rules** (applied to wind):
- >= 55 mph: No Travel for any load.
- 45-54 mph with a load over 30,000 lb: No Travel.
- 35-44 mph with a load over 40,000 lb: Severe.

**Boundaries:** a value exactly on a shared boundary takes the higher category (wind 25 / 35 / 45 / 55 mph, rain 0.10 / 0.25 / 0.50 in/hr, snow 0.5 / 1.0 / 2.0 in/hr). The exceptions are 1.00 in/hr rain and 3.0 in/hr snow, which stay Severe because the table defines No Travel as strictly greater than those values.

## Route recommendation

Routes are ranked lexicographically:

1. Fewest Severe miles. No Travel miles count as Severe, and any route with No Travel miles ranks below every route without them.
2. Fewest High miles.
3. Lowest average risk score (1-5), weighted by the miles each checkpoint represents. Miles with no forecast are excluded from the average and reported separately.
4. Shortest travel time.

Each checkpoint represents the miles halfway to its neighbours on either side.

## Assumptions and limitations

- **Wind** is Open-Meteo's sustained wind at 10 m (`windspeed_10m`), not gusts.
- **ETAs** assume continuous driving at OSRM's estimated segment speeds (OSRM's public server uses a car profile), with no hours-of-service rest breaks.
- **Forecasts** are read for the hour containing each ETA. Departures must be between 1 hour ago and 5 days ahead, so the 48-hour slider and the trip stay inside Open-Meteo's 7-day forecast. ETAs that still fall outside it are shown as Unknown.
- **Geography:** the interface is US-focused (default map view, presets, miles and pounds), but any trip that can be driven by road works. Location lookup is US-first: a foreign match is chosen only when it is clearly more prominent, so "Toronto" or "Delhi" resolve abroad while "Springfield" or "Paris, TX" stay in the US. The resolved place is shown under each input. Trips with no road connection (for example New York to London) are rejected with a clear error.
- **Long trips:** if a route would exceed 250 checkpoints (over 2,500 miles at 10-mile spacing), spacing widens to 25 or 50 miles with a warning, to stay within Open-Meteo's free-tier limits.
- **Demo storm:** centred on the trip midpoint, with a radius of 30% of the straight-line trip length. It starts at 40% strength, reaches full strength by hour 12, holds until hour 30 and fades out by hour 48. Checkpoints and the heatmap sample the same model, so they always agree.
- **Rate limits:** the free Open-Meteo and Nominatim services limit request rates. Rate-limited weather batches are retried twice with backoff; anything still missing is shown as Unknown.

## Performance

- Forecast points from all routes and the heatmap are snapped to a ~7-mile grid, deduplicated and fetched from Open-Meteo in parallel batches of 50 locations.
- Caches (in-process): forecasts for 30 minutes, routes for 1 hour per origin and destination, and place lookups for the life of the process. Changing the interval, load weight, departure time or weather mode for the same trip makes no external API calls.
- Route lines sent to the browser are simplified (about 10,000 points per route down to about 300) and responses are gzip-compressed. Full geometry is still used for sampling.
- On the map, lines and markers are drawn on a canvas, heatmap redraws are limited to one per animation frame, and each heatmap colour is rendered once and reused.

## Tech stack

| Layer | Technology |
| :--- | :--- |
| Frontend | React 19, Vite 8, Tailwind CSS 3, Leaflet 1.9 with react-leaflet 5, lucide-react icons |
| Backend | Python, Django 6.1, Django REST Framework 3.18, django-cors-headers |
| Routing | [OSRM](https://project-osrm.org/) public demo server |
| Geocoding | [Nominatim](https://nominatim.org/) (OpenStreetMap), with [Photon](https://photon.komoot.io/) as fallback |
| Weather | [Open-Meteo](https://open-meteo.com/) hourly forecast API |
| Basemap | Esri World Dark Gray tiles |

No API keys are needed. The backend has no database; all state is cached in memory.

## Running locally

**Prerequisites:** Python 3.12+ and Node.js 20+.

**Backend** (from the repository root):

```bash
python -m venv venv
```

```bash
venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

```bash
venv\Scripts\python.exe backend\manage.py runserver 8000
```

On macOS or Linux, use `venv/bin/python` and forward slashes. The API runs at http://localhost:8000/api/ (health check: `/api/health/`). No environment variables are needed for local development.

**Frontend** (in a second terminal):

```bash
cd frontend
```

```bash
npm install
```

```bash
npm run dev
```

Open http://localhost:5173. The frontend calls `http://localhost:8000/api` unless `VITE_API_BASE_URL` is set.

**Docker** (alternative): `docker compose up --build` starts the backend on port 8000 and the frontend dev server on port 5173.

**Production mode locally:** build the frontend with `VITE_API_BASE_URL=/api npm run build`. Django then serves it at http://localhost:8000/ from the same origin as the API.

## Configuration

Production settings come from environment variables (see `backend/.env.example`).

| Variable | Purpose | Default |
| :--- | :--- | :--- |
| `DJANGO_DEBUG` | Set to `false` in production | `true` |
| `DJANGO_SECRET_KEY` | Required when debug is off | development-only key when debug is on |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated backend hostnames | `localhost,127.0.0.1` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated frontend origins allowed to call the API | `http://localhost:5173,http://127.0.0.1:5173` |
| `DJANGO_LOG_LEVEL` | Log level | `INFO` |
| `FRONTEND_DIST_DIR` | Built frontend that Django serves at `/` (via WhiteNoise) | `frontend/dist`; `/app/frontend_dist` in Docker |
| `VITE_API_BASE_URL` | Frontend build: base URL of the API | `http://localhost:8000/api` |

## Deployment

The app deploys as **one web service**. The Docker image builds the React frontend and Django serves it (via WhiteNoise) together with the API, so there is a single URL and no cross-origin setup.

- `Dockerfile`: builds the frontend with `VITE_API_BASE_URL=/api`, then runs gunicorn with **one worker and 8 threads**. The route, weather and place caches live in process memory, so a single process lets every request share them. It listens on the platform's `$PORT`.
- `render.yaml`: a Render Blueprint for the free plan. It sets `DJANGO_DEBUG=false`, generates `DJANGO_SECRET_KEY`, and uses `/api/health/` as the health check. Render's hostname is added to `ALLOWED_HOSTS` automatically through `RENDER_EXTERNAL_HOSTNAME`.

To deploy on Render: **New > Blueprint**, select this repository, then **Apply**. Free instances sleep after about 15 minutes without traffic, so the first request after that takes 30-60 seconds while the service wakes up.

Other platforms work the same way: build the `Dockerfile`, and set `DJANGO_DEBUG=false`, `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS`.

## Tests

```bash
venv\Scripts\python.exe backend\manage.py test truck_routing
```

The suite has 52 tests and runs offline, with the routing, geocoding and weather APIs mocked. It covers the risk thresholds, boundary values and load rules, the four ranking tiers, ETA calculation, Unknown handling, forecast batching, caching and retries, route deduplication, departure validation and the API contract.

Frontend checks:

```bash
cd frontend
```

```bash
npm run lint
```

```bash
npm run build
```

## API

### `GET /api/health/`

Returns `{"status": "healthy", ...}`.

### `POST /api/routes/calculate/`

Request:

```json
{
  "origin": "Chicago, IL",
  "destination": "Denver, CO",
  "departure_time": "2026-10-25T14:00:00Z",
  "load_weight_lbs": 42000,
  "sampling_interval_miles": 25,
  "scenario": "live"
}
```

| Field | Required | Notes |
| :--- | :--- | :--- |
| `origin`, `destination` | yes | Place name, ZIP/postal code, or `lat, lon` |
| `departure_time` | no | ISO 8601, from 1 hour ago to 5 days ahead; defaults to the next whole hour |
| `load_weight_lbs` | no | 0-120,000; default 40,000 |
| `sampling_interval_miles` | no | 10, 25 or 50; default 25 |
| `scenario` | no | `live` (default), `high_wind`, `blizzard` or `rainstorm` |

Response (main fields):

- `origin`, `destination`: resolved coordinates, display name and country code.
- `routes`: ranked routes, each with `name`, `distance_miles`, `duration_seconds`, `rank`, `is_recommended`, `recommendation_reason`, `summary` (miles per risk level including `unknown_miles`, plus `average_risk_score`), `coordinates` (simplified), and `checkpoints`. Each checkpoint has its mile marker, position, ETA, `weather` (with `source`: `open-meteo`, `simulated` or `unavailable`) and `risk`.
- `corridor_heatmap`: `timestamps` for hours 0-48, and `points`, each with `wind`, `rain`, `snow` and `risk` arrays indexed by hour (`null` where no forecast exists).
- `warnings`: data-quality and safety notices.
- `no_safe_route`: `true` when every route crosses No Travel conditions.
- `sampling_interval_miles` and `requested_sampling_interval_miles`: these differ when a long trip's spacing was widened.

Errors return `{"status": "error", "message": ...}`: 400 for invalid input, unknown places or trips with no road route, and 502 when the routing service is unavailable.

## Project structure

```
backend/
  config/                     Django settings and URLs
  truck_routing/
    views.py                  Request validation and error mapping
    serializers.py            Input validation (including the departure window)
    services/
      trip_planner.py         The pipeline: routes, checkpoints, weather, risk, ranking, heatmap
      geocoding_service.py    US-first place lookup
      routing_service.py      OSRM routes, alternatives, deduplication, route cache
      sampling_service.py     Checkpoints and ETAs
      weather_service.py      Batched, cached Open-Meteo forecasts
      risk_engine.py          Risk table and load rules
      recommendation.py       Four-tier ranking and route summaries
      corridor_service.py     Heatmap stations and 0-48 h timeline
      scenario_service.py     Simulated demo storm
      common.py               Shared helpers
    tests.py                  Test suite
frontend/
  src/
    App.jsx                   Layout and state
    components/               Trip form, route cards, map, checkpoints, heatmap, forecast slider
    lib/risk.js               Risk colours and thresholds shared by the map and legends
    services/api.js           API client
```
