import re
import time
import threading
import requests
from functools import lru_cache
from typing import Dict, Any, Optional
from .common import USER_AGENT

# Cache of major US freight hubs for instant response and zero rate-limiting during testing/demo
KNOWN_HUBS: Dict[str, Dict[str, Any]] = {
    "chicago, il": {"lat": 41.8781, "lon": -87.6298, "display_name": "Chicago, Illinois, USA"},
    "chicago": {"lat": 41.8781, "lon": -87.6298, "display_name": "Chicago, Illinois, USA"},
    "denver, co": {"lat": 39.7392, "lon": -104.9903, "display_name": "Denver, Colorado, USA"},
    "denver": {"lat": 39.7392, "lon": -104.9903, "display_name": "Denver, Colorado, USA"},
    "seattle, wa": {"lat": 47.6062, "lon": -122.3321, "display_name": "Seattle, Washington, USA"},
    "seattle": {"lat": 47.6062, "lon": -122.3321, "display_name": "Seattle, Washington, USA"},
    "dallas, tx": {"lat": 32.7767, "lon": -96.7970, "display_name": "Dallas, Texas, USA"},
    "dallas": {"lat": 32.7767, "lon": -96.7970, "display_name": "Dallas, Texas, USA"},
    "minneapolis, mn": {"lat": 44.9778, "lon": -93.2650, "display_name": "Minneapolis, Minnesota, USA"},
    "minneapolis": {"lat": 44.9778, "lon": -93.2650, "display_name": "Minneapolis, Minnesota, USA"},
    "kansas city, mo": {"lat": 39.0997, "lon": -94.5786, "display_name": "Kansas City, Missouri, USA"},
    "kansas city": {"lat": 39.0997, "lon": -94.5786, "display_name": "Kansas City, Missouri, USA"},
    "omaha, ne": {"lat": 41.2565, "lon": -95.9345, "display_name": "Omaha, Nebraska, USA"},
    "omaha": {"lat": 41.2565, "lon": -95.9345, "display_name": "Omaha, Nebraska, USA"},
    "new york, ny": {"lat": 40.7128, "lon": -74.0060, "display_name": "New York, New York, USA"},
    "new york": {"lat": 40.7128, "lon": -74.0060, "display_name": "New York, New York, USA"},
    "los angeles, ca": {"lat": 34.0522, "lon": -118.2437, "display_name": "Los Angeles, California, USA"},
    "los angeles": {"lat": 34.0522, "lon": -118.2437, "display_name": "Los Angeles, California, USA"},
    "salt lake city, ut": {"lat": 40.7608, "lon": -111.8910, "display_name": "Salt Lake City, Utah, USA"},
    "salt lake city": {"lat": 40.7608, "lon": -111.8910, "display_name": "Salt Lake City, Utah, USA"},
    "atlanta, ga": {"lat": 33.7490, "lon": -84.3880, "display_name": "Atlanta, Georgia, USA"},
    "atlanta": {"lat": 33.7490, "lon": -84.3880, "display_name": "Atlanta, Georgia, USA"},
}

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
PHOTON_URL = "https://photon.komoot.io/api/"

# Lookup is US-first: a place outside the US wins only when it is clearly more prominent
# (Nominatim importance, 0-1) than the best US match. So "Delhi" or "Toronto" resolve abroad,
# while "Springfield" or "Vancouver" stay in the US; "Delhi, NY" or "Paris, TX" pick the US one.
FOREIGN_IMPORTANCE_MARGIN = 0.2
# Nominatim's usage policy allows at most one request per second
NOMINATIM_MIN_INTERVAL_SECONDS = 1.0

_nominatim_lock = threading.Lock()
_nominatim_last_call = 0.0


def _nominatim_search(query: str, us_only: bool) -> Optional[Dict[str, Any]]:
    """Best Nominatim match for `query` (optionally US-only), or None."""
    global _nominatim_last_call
    params = {"q": query, "format": "json", "limit": 1, "addressdetails": 1}
    if us_only:
        params["countrycodes"] = "us"
    with _nominatim_lock:
        wait = NOMINATIM_MIN_INTERVAL_SECONDS - (time.monotonic() - _nominatim_last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            resp = requests.get(NOMINATIM_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=5)
            data = resp.json() if resp.status_code == 200 else []
        except Exception:
            data = []
        finally:
            _nominatim_last_call = time.monotonic()
    if not data:
        return None
    first = data[0]
    return {
        "lat": float(first["lat"]),
        "lon": float(first["lon"]),
        "display_name": first.get("display_name", query),
        "country_code": (first.get("address") or {}).get("country_code", "").upper(),
        "importance": float(first.get("importance") or 0.0),
    }


def _photon_search(query: str) -> Optional[Dict[str, Any]]:
    """Fallback geocoder: prefers a US candidate, otherwise the top worldwide match."""
    try:
        resp = requests.get(PHOTON_URL, params={"q": query, "limit": 5},
                            headers={"User-Agent": USER_AGENT}, timeout=5)
        features = resp.json().get("features", []) if resp.status_code == 200 else []
    except Exception:
        features = []
    if not features:
        return None
    feature = next((f for f in features if f.get("properties", {}).get("countrycode") == "US"), features[0])
    lon, lat = feature["geometry"]["coordinates"]
    props = feature.get("properties", {})
    name_parts = [props.get("name"), props.get("city"), props.get("state"), props.get("country")]
    return {
        "lat": float(lat),
        "lon": float(lon),
        "display_name": ", ".join(p for p in name_parts if p) or query,
        "country_code": (props.get("countrycode") or "").upper(),
    }


def _public(result: Dict[str, Any]) -> Dict[str, Any]:
    return {k: result[k] for k in ("lat", "lon", "display_name", "country_code")}


@lru_cache(maxsize=512)
def _geocode_place(query: str) -> Dict[str, Any]:
    us = _nominatim_search(query, us_only=True)
    world = _nominatim_search(query, us_only=False)

    if us and world and world["country_code"] != "US":
        if world["importance"] >= us["importance"] + FOREIGN_IMPORTANCE_MARGIN:
            return _public(world)
        return _public(us)
    if us or world:
        return _public(us or world)

    fallback = _photon_search(query)
    if fallback:
        return fallback
    raise ValueError(f"Could not find '{query}'. Check the spelling, or enter 'City, ST', 'City, Country' or coordinates.")


def geocode_location(query: str) -> Dict[str, Any]:
    """
    Resolves a location string to latitude, longitude, display name and country code.
    Supports:
    1. Direct coordinate strings: "lat, lon"
    2. Cached known US freight hubs (fast, rate-limit immune)
    3. OpenStreetMap Nominatim, US-first (see FOREIGN_IMPORTANCE_MARGIN)
    4. Photon (Komoot OSM) fallback
    Whether a drivable road route exists is decided later by the routing service.
    """
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("Location query cannot be empty.")

    # 1. Direct coordinates: "lat, lon"
    coord_match = re.match(r"^([-+]?\d{1,2}(?:\.\d+)?)[,\s]+([-+]?\d{1,3}(?:\.\d+)?)$", clean_query)
    if coord_match:
        lat = float(coord_match.group(1))
        lon = float(coord_match.group(2))
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            raise ValueError(f"Coordinates {lat}, {lon} are out of range (latitude -90 to 90, longitude -180 to 180).")
        return {"lat": lat, "lon": lon, "display_name": f"{lat:.4f}, {lon:.4f}", "country_code": ""}

    # 2. Cached hubs
    lookup_key = clean_query.lower()
    if lookup_key in KNOWN_HUBS:
        return {**KNOWN_HUBS[lookup_key], "country_code": "US"}

    # 3-4. Geocoding APIs (results cached per query)
    return dict(_geocode_place(clean_query))
