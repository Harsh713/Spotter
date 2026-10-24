from datetime import timedelta
from typing import List, Dict, Any, Optional, Tuple
from .weather_service import fetch_forecasts, grid_key, extract_weather_at_hour, GridKey
from .risk_engine import evaluate_weather_risk
from .common import haversine_miles
from .sampling_service import parse_departure_time
from .scenario_service import simulated_weather, storm_from_points

# Spacing between heatmap stations along each route, and the dedupe cell size that merges
# stations where routes overlap (~14 mi, a little over half the spacing).
CORRIDOR_SPACING_MILES = 25.0
CORRIDOR_DEDUPE_DEGREES = 0.2
MAX_CORRIDOR_POINTS = 200


def _points_along(coords: List[List[float]], spacing_miles: float) -> List[Tuple[float, float]]:
    """Points every `spacing_miles` along a polyline (including both ends)."""
    points = [(coords[0][0], coords[0][1])]
    next_mark = spacing_miles
    travelled = 0.0
    for (lat_a, lon_a), (lat_b, lon_b) in zip(coords, coords[1:]):
        seg = haversine_miles(lat_a, lon_a, lat_b, lon_b)
        while seg > 0 and travelled + seg >= next_mark:
            t = (next_mark - travelled) / seg
            points.append((lat_a + t * (lat_b - lat_a), lon_a + t * (lon_b - lon_a)))
            next_mark += spacing_miles
        travelled += seg
    points.append((coords[-1][0], coords[-1][1]))
    return points


def sample_corridor_points(
    routes: List[Dict[str, Any]],
    spacing_miles: float = CORRIDOR_SPACING_MILES,
    max_points: int = MAX_CORRIDOR_POINTS
) -> List[Dict[str, float]]:
    """
    Heatmap stations every `spacing_miles` along every route, so the heatmap covers the whole
    trip corridor. Stations where routes overlap are merged. For very long trips the spacing
    widens until the station count fits `max_points`.
    """
    routes = [r for r in routes if len(r.get("coordinates", [])) >= 2]
    if not routes:
        return []

    while True:
        seen = set()
        stations = []
        for r in routes:
            for lat, lon in _points_along(r["coordinates"], spacing_miles):
                cell = (round(lat / CORRIDOR_DEDUPE_DEGREES), round(lon / CORRIDOR_DEDUPE_DEGREES))
                if cell not in seen:
                    seen.add(cell)
                    stations.append({"lat": round(lat, 4), "lon": round(lon, 4)})
        if len(stations) <= max_points:
            return stations
        spacing_miles *= len(stations) / max_points


def generate_corridor_heatmap_timeline(
    corridor_points: List[Dict[str, float]],
    departure_time: Any,
    load_weight_lbs: float = 40000.0,
    scenario: Optional[str] = None,
    forecasts: Optional[Dict[GridKey, Optional[Dict[str, Any]]]] = None,
    storm: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generates a 0-48 hour hourly weather forecast matrix across all corridor points.
    `departure_time` must be the same aware UTC datetime used for checkpoint ETAs so that
    slider hour 0 lines up with departure. In live mode, hours or points without forecast
    coverage are returned with null readings and risk_level "Unknown".
    Returns one array per metric per point, indexed by hour (0-48); null means no forecast:
    {
      "hours_count": 49,
      "timestamps": ["2026-10-24T08:00:00Z", ...],
      "unavailable_cells": 0,
      "points": [
        {"point_id": 0, "lat": 41.8781, "lon": -87.6298,
         "wind": [15.0, ...], "rain": [0.0, ...], "snow": [0.0, ...], "risk": [1, ...]}
      ]
    }
    """
    is_live = not scenario or scenario == "live"
    if is_live and forecasts is None:
        forecasts = fetch_forecasts((pt["lat"], pt["lon"]) for pt in corridor_points)

    dep_dt = parse_departure_time(departure_time)
    if not is_live and storm is None:
        storm = storm_from_points(corridor_points, dep_dt)
    hours = list(range(49))
    hour_times = [dep_dt + timedelta(hours=h) for h in hours]
    timestamps = [t.strftime("%Y-%m-%dT%H:00:00Z") for t in hour_times]

    points_data = []
    unavailable_cells = 0

    for idx, pt in enumerate(corridor_points):
        lat = pt["lat"]
        lon = pt["lon"]
        hourly = forecasts.get(grid_key(lat, lon)) if is_live else None
        series = {"wind": [], "rain": [], "snow": [], "risk": []}

        for h, target_dt in zip(hours, hour_times):
            if is_live:
                weather = extract_weather_at_hour(hourly, target_dt)
            else:
                weather = simulated_weather(lat, lon, target_dt, scenario, storm)

            risk_score = evaluate_weather_risk(weather, load_weight_lbs)["overall_risk_score"]
            if risk_score is None:
                unavailable_cells += 1

            series["wind"].append(weather["wind_speed_mph"])
            series["rain"].append(weather["rain_in_per_hr"])
            series["snow"].append(weather["snow_in_per_hr"])
            series["risk"].append(risk_score)

        points_data.append({"point_id": idx, "lat": lat, "lon": lon, **series})

    return {
        "hours_count": len(hours),
        "timestamps": timestamps,
        "unavailable_cells": unavailable_cells,
        "points": points_data
    }
