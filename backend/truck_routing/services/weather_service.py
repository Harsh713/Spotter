import time
import logging
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Iterable, Tuple
from django.core.cache import cache
from .common import USER_AGENT
from .scenario_service import simulated_weather, storm_from_points

logger = logging.getLogger(__name__)

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Points are snapped to a 0.1 degree grid (~7 mi) before fetching. This is finer than the
# global weather models behind Open-Meteo and lets overlapping routes share forecasts.
GRID_DEGREES = 0.1
# Open-Meteo accepts comma-separated coordinate lists; keep URLs comfortably short.
BATCH_SIZE = 50
MAX_PARALLEL_BATCHES = 4
CACHE_TTL_SECONDS = 30 * 60
# Open-Meteo's free tier rate-limits bursts (HTTP 429); retry briefly before giving up on a batch
RETRY_DELAYS_SECONDS = (1.5, 4.0)
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
FORECAST_DAYS = 7
# Open-Meteo reports large-scale rain (`rain`) and convective rain (`showers`) separately;
# both count toward the rain risk rate.
HOURLY_VARIABLES = "temperature_2m,windspeed_10m,rain,showers,snowfall,weathercode"

WEATHER_SOURCE_LIVE = "open-meteo"
WEATHER_SOURCE_SIMULATED = "simulated"
WEATHER_SOURCE_UNAVAILABLE = "unavailable"

# WMO Weather interpretation codes
WMO_DESCRIPTIONS: Dict[int, str] = {
    0: "Clear Sky",
    1: "Mainly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing Rime Fog",
    51: "Light Drizzle",
    53: "Moderate Drizzle",
    55: "Dense Drizzle",
    61: "Slight Rain",
    63: "Moderate Rain",
    65: "Heavy Rain",
    71: "Slight Snow Fall",
    73: "Moderate Snow Fall",
    75: "Heavy Snow Fall",
    77: "Snow Grains",
    80: "Slight Rain Showers",
    81: "Moderate Rain Showers",
    82: "Violent Rain Showers",
    85: "Slight Snow Showers",
    86: "Heavy Snow Showers",
    95: "Thunderstorm",
    96: "Thunderstorm with Slight Hail",
    99: "Thunderstorm with Heavy Hail"
}

GridKey = Tuple[float, float]


def get_weather_condition_name(code: int) -> str:
    """Returns human-readable WMO weather code description."""
    return WMO_DESCRIPTIONS.get(code, "Clear")


def grid_key(lat: float, lon: float) -> GridKey:
    """Snaps a coordinate to the forecast grid cell it is looked up from."""
    return (
        round(round(lat / GRID_DEGREES) * GRID_DEGREES, 2),
        round(round(lon / GRID_DEGREES) * GRID_DEGREES, 2),
    )


def _cache_key(key: GridKey) -> str:
    return f"wx:{key[0]},{key[1]}"


def _index_hourly(hourly: Dict[str, Any]) -> Dict[str, Any]:
    """Adds a time -> index lookup so per-hour reads are O(1)."""
    hourly["_index"] = {t: i for i, t in enumerate(hourly.get("time", []))}
    return hourly


def _fetch_batch(keys: List[GridKey]) -> Dict[GridKey, Dict[str, Any]]:
    params = {
        "latitude": ",".join(str(k[0]) for k in keys),
        "longitude": ",".join(str(k[1]) for k in keys),
        "hourly": HOURLY_VARIABLES,
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "temperature_unit": "fahrenheit",
        "timezone": "UTC",
        "forecast_days": FORECAST_DAYS,
    }
    data = None
    for attempt, delay in enumerate((0.0,) + RETRY_DELAYS_SECONDS):
        time.sleep(delay)
        try:
            resp = requests.get(OPEN_METEO_FORECAST_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
            if resp.status_code in RETRYABLE_STATUS and attempt < len(RETRY_DELAYS_SECONDS):
                continue
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as exc:
            if attempt == len(RETRY_DELAYS_SECONDS):
                logger.warning("Open-Meteo batch of %d locations failed: %s", len(keys), exc)
    if data is None:
        return {}

    # A single location returns an object; multiple locations return a list in request order
    items = data if isinstance(data, list) else [data]
    results = {}
    for key, item in zip(keys, items):
        if isinstance(item, dict) and "hourly" in item:
            results[key] = _index_hourly(item["hourly"])
    return results


def fetch_forecasts(points: Iterable[Tuple[float, float]]) -> Dict[GridKey, Optional[Dict[str, Any]]]:
    """
    Fetches hourly forecasts for many (lat, lon) points at once.
    Points are deduplicated by grid cell, served from a TTL cache when possible, and the
    remainder is requested from Open-Meteo in parallel batches.
    Returns {grid_key: hourly dict or None if the forecast could not be retrieved}.
    """
    keys = list(dict.fromkeys(grid_key(lat, lon) for lat, lon in points))
    cached = cache.get_many([_cache_key(k) for k in keys])

    results: Dict[GridKey, Optional[Dict[str, Any]]] = {}
    missing: List[GridKey] = []
    for k in keys:
        hit = cached.get(_cache_key(k))
        if hit is not None:
            results[k] = hit
        else:
            missing.append(k)

    if missing:
        batches = [missing[i:i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
        fetched: Dict[GridKey, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_BATCHES) as pool:
            for batch_result in pool.map(_fetch_batch, batches):
                fetched.update(batch_result)
        cache.set_many({_cache_key(k): v for k, v in fetched.items()}, CACHE_TTL_SECONDS)
        for k in missing:
            results[k] = fetched.get(k)

    return results


def fetch_point_forecast(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """Fetches the hourly forecast for a single point (see fetch_forecasts)."""
    return fetch_forecasts([(lat, lon)])[grid_key(lat, lon)]


def unavailable_weather_point() -> Dict[str, Any]:
    """Weather record used when no forecast exists for a point/hour. Never treated as safe."""
    return {
        "source": WEATHER_SOURCE_UNAVAILABLE,
        "wind_speed_mph": None,
        "rain_in_per_hr": None,
        "snow_in_per_hr": None,
        "temperature_f": None,
        "weather_code": None,
        "condition": "Forecast unavailable"
    }


def extract_weather_at_hour(hourly: Optional[Dict[str, Any]], eta_dt: datetime) -> Dict[str, Any]:
    """
    Returns the forecast slice for the hour containing `eta_dt`, or an unavailable record if
    the forecast is missing or does not cover that hour (no clamping to other hours).
    """
    if not hourly:
        return unavailable_weather_point()

    index = hourly.get("_index") or _index_hourly(hourly)["_index"]
    idx = index.get(eta_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00"))
    if idx is None:
        return unavailable_weather_point()

    def value(name: str) -> Optional[float]:
        series = hourly.get(name) or []
        return series[idx] if idx < len(series) else None

    wind_spd, rain_rate, snow_rate = value("windspeed_10m"), value("rain"), value("snowfall")
    if wind_spd is None or rain_rate is None or snow_rate is None:
        return unavailable_weather_point()

    # Convective showers (thunderstorm downpours) are rain too; absent showers data counts as none
    rain_rate = float(rain_rate) + float(value("showers") or 0.0)

    temp_f = value("temperature_2m")
    code = int(value("weathercode") or 0)

    return {
        "source": WEATHER_SOURCE_LIVE,
        "wind_speed_mph": round(float(wind_spd), 1),
        "rain_in_per_hr": round(float(rain_rate), 2),
        "snow_in_per_hr": round(float(snow_rate), 2),
        "temperature_f": round(float(temp_f), 1) if temp_f is not None else None,
        "weather_code": code,
        "condition": get_weather_condition_name(code)
    }


def enrich_checkpoints_with_weather(
    checkpoints: List[Dict[str, Any]],
    scenario: Optional[str] = None,
    forecasts: Optional[Dict[GridKey, Optional[Dict[str, Any]]]] = None,
    storm: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Enriches each checkpoint with weather for its exact ETA.
    Live mode: uses `forecasts` (from fetch_forecasts) if given, otherwise fetches here.
    Checkpoints without forecast coverage are marked unavailable rather than assumed calm.
    Demo scenarios: samples the simulated `storm` (see scenario_service) at each ETA.
    """
    is_live = not scenario or scenario == "live"
    if is_live and forecasts is None:
        forecasts = fetch_forecasts((c["lat"], c["lon"]) for c in checkpoints)

    for chk in checkpoints:
        eta_dt = datetime.fromisoformat(chk["eta_iso"].replace("Z", "+00:00"))
        if is_live:
            hourly = forecasts.get(grid_key(chk["lat"], chk["lon"]))
            chk["weather"] = extract_weather_at_hour(hourly, eta_dt)
        else:
            if storm is None:
                departure = eta_dt - timedelta(seconds=chk.get("elapsed_seconds", 0))
                storm = storm_from_points(checkpoints, departure)
            chk["weather"] = simulated_weather(chk["lat"], chk["lon"], eta_dt, scenario, storm)

    return checkpoints
