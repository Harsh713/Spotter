from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from .common import haversine_miles

# Demonstration scenarios replace live forecasts with one simulated storm. Weather is a single
# function of (location, time), so checkpoints (sampled at their ETAs) and the heatmap (sampled
# at each slider hour) always agree.
SCENARIOS = ("high_wind", "blizzard", "rainstorm")

# Readings at the storm's centre at peak strength, and on its edge / outside it
STORM_PEAK = {
    "high_wind": {"wind_speed_mph": 60.0, "rain_in_per_hr": 0.2, "snow_in_per_hr": 0.0},
    "blizzard": {"wind_speed_mph": 38.0, "rain_in_per_hr": 0.0, "snow_in_per_hr": 3.5},
    "rainstorm": {"wind_speed_mph": 30.0, "rain_in_per_hr": 1.3, "snow_in_per_hr": 0.0},
}
CALM = {"wind_speed_mph": 12.0, "rain_in_per_hr": 0.0, "snow_in_per_hr": 0.0}
STORM_TEMPERATURE_F = {"high_wind": 52.0, "blizzard": 24.0, "rainstorm": 61.0}

# Storm radius as a share of the straight-line trip length (never smaller than this many miles)
STORM_RADIUS_FRACTION = 0.3
MIN_STORM_RADIUS_MILES = 40.0
# Strength over the 48 h window: builds from 40% at departure to full strength by hour 12,
# holds until hour 30, then fades out by hour 48.
RAMP_UP_HOURS, HOLD_UNTIL_HOURS, FADE_OUT_HOURS = 12.0, 30.0, 48.0
INITIAL_STRENGTH = 0.4


def build_storm(origin: Tuple[float, float], destination: Tuple[float, float], departure: datetime) -> Dict[str, Any]:
    """A storm centred on the trip midpoint, sized to the trip so it affects any route length."""
    trip_miles = haversine_miles(origin[0], origin[1], destination[0], destination[1])
    return {
        "lat": (origin[0] + destination[0]) / 2,
        "lon": (origin[1] + destination[1]) / 2,
        "radius_miles": max(MIN_STORM_RADIUS_MILES, STORM_RADIUS_FRACTION * trip_miles),
        "departure": departure,
    }


def storm_from_points(points: List[Dict[str, Any]], departure: datetime) -> Optional[Dict[str, Any]]:
    """Fallback storm built from the first and last of a list of {lat, lon} points."""
    if not points:
        return None
    first, last = points[0], points[-1]
    return build_storm((first["lat"], first["lon"]), (last["lat"], last["lon"]), departure)


def _time_strength(hours_since_departure: float) -> float:
    h = max(0.0, hours_since_departure)
    if h <= RAMP_UP_HOURS:
        return INITIAL_STRENGTH + (1 - INITIAL_STRENGTH) * h / RAMP_UP_HOURS
    if h <= HOLD_UNTIL_HOURS:
        return 1.0
    if h <= FADE_OUT_HOURS:
        return 1.0 - (h - HOLD_UNTIL_HOURS) / (FADE_OUT_HOURS - HOLD_UNTIL_HOURS)
    return 0.0


def simulated_weather(lat: float, lon: float, at: datetime, scenario: str, storm: Dict[str, Any]) -> Dict[str, Any]:
    """Simulated weather record (same shape as live records) for `scenario` at a place and time."""
    peak = STORM_PEAK[scenario]
    dist = haversine_miles(lat, lon, storm["lat"], storm["lon"])
    # Smooth falloff from full strength at the centre to calm at the storm's edge
    spatial = max(0.0, 1.0 - (dist / storm["radius_miles"]) ** 2)
    hours = (at - storm["departure"]).total_seconds() / 3600.0
    strength = spatial * _time_strength(hours)

    reading = {
        key: round(CALM[key] + (peak[key] - CALM[key]) * strength, 2 if key != "wind_speed_mph" else 1)
        for key in CALM
    }
    if strength < 0.15:
        condition, code = "Mainly Clear", 1
    elif scenario == "high_wind":
        condition, code = "High Winds", 3
    elif scenario == "blizzard":
        condition, code = "Heavy Snow" if strength > 0.6 else "Snow", 75 if strength > 0.6 else 73
    else:
        condition, code = "Heavy Rain" if strength > 0.6 else "Rain", 65 if strength > 0.6 else 63

    return {
        "source": "simulated",
        **reading,
        "temperature_f": STORM_TEMPERATURE_F[scenario],
        "weather_code": code,
        "condition": condition,
    }
