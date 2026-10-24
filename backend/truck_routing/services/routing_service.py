import math
import requests
import polyline
from typing import List, Dict, Any, Tuple, Optional, Set
from django.core.cache import cache
from .common import USER_AGENT
from .geocoding_service import geocode_location

OSRM_BASE_URL = "http://router.project-osrm.org/route/v1/driving"
METERS_TO_MILES = 0.000621371

# OSRM snaps each input point to the nearest road it knows. If that road is further than this,
# the location has no drivable road nearby and any "route" would end in the wrong place.
MAX_SNAP_METERS = 40000
# Waypoint detours are tried at these fractions of the straight-line trip length, on both sides.
WAYPOINT_OFFSET_FRACTIONS = (0.15, 0.3)
# Alternatives longer than this multiple of the shortest route are not realistic options.
MAX_DETOUR_RATIO = 1.5
# A candidate sharing more than this fraction of its path with an accepted route is a duplicate.
MAX_OVERLAP_FRACTION = 0.8
OVERLAP_GRID_DEGREES = 0.02  # ~1.4 mi cells for path overlap comparison
# Routes depend only on origin and destination, so re-running the same trip with a different
# sampling interval, load weight, departure time or weather mode reuses them.
ROUTE_CACHE_TTL_SECONDS = 60 * 60


class NoRouteError(ValueError):
    """Raised when no drivable road route exists between the requested locations."""


class RoutingServiceError(RuntimeError):
    """Raised when the routing API cannot be reached or returns an unusable response."""


def _decode_polyline(encoded: str) -> List[List[float]]:
    """Decodes an encoded polyline into a list of [lat, lon] coordinates."""
    try:
        decoded = polyline.decode(encoded)
        return [[round(pt[0], 5), round(pt[1], 5)] for pt in decoded]
    except Exception:
        return []

def simplify_coordinates(coords: List[List[float]], tolerance_deg: float = 0.002) -> List[List[float]]:
    """
    Ramer-Douglas-Peucker simplification for map display. The default tolerance (~0.1 mi)
    is invisible at the zoom levels used for long-haul routes but removes ~90% of vertices.
    Full-resolution geometry should still be used for checkpoint sampling.
    """
    if len(coords) < 3:
        return coords

    keep = [False] * len(coords)
    keep[0] = keep[-1] = True
    stack = [(0, len(coords) - 1)]
    tol_sq = tolerance_deg ** 2

    while stack:
        start, end = stack.pop()
        (y1, x1), (y2, x2) = coords[start], coords[end]
        dx, dy = x2 - x1, y2 - y1
        seg_len_sq = dx * dx + dy * dy
        max_dist_sq, max_idx = 0.0, -1

        for i in range(start + 1, end):
            py, px = coords[i]
            if seg_len_sq == 0:
                dist_sq = (px - x1) ** 2 + (py - y1) ** 2
            else:
                t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg_len_sq))
                dist_sq = (px - (x1 + t * dx)) ** 2 + (py - (y1 + t * dy)) ** 2
            if dist_sq > max_dist_sq:
                max_dist_sq, max_idx = dist_sq, i

        if max_dist_sq > tol_sq:
            keep[max_idx] = True
            stack.append((start, max_idx))
            stack.append((max_idx, end))

    return [pt for pt, k in zip(coords, keep) if k]

def _query_osrm(coords: List[Tuple[float, float]], alternatives: bool) -> Optional[Dict[str, Any]]:
    """
    Queries OSRM for routes through `coords` ((lat, lon) tuples; OSRM expects lon,lat in the URL).
    Returns the parsed response, or None if the routing API could not be reached.
    """
    coord_str = ";".join(f"{lon:.5f},{lat:.5f}" for lat, lon in coords)
    params = {
        "overview": "full",
        "geometries": "polyline",
        "steps": "false",
        "annotations": "duration",
        "alternatives": "true" if alternatives else "false"
    }
    try:
        resp = requests.get(f"{OSRM_BASE_URL}/{coord_str}", params=params,
                            headers={"User-Agent": USER_AGENT}, timeout=15)
        return resp.json()
    except Exception:
        return None


def _build_route(osrm_route: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Converts an OSRM route into the internal route dict, or None if its geometry is unusable."""
    coords = _decode_polyline(osrm_route.get("geometry", ""))
    if len(coords) < 2:
        return None

    # Per-segment travel times (one per pair of consecutive vertices) drive checkpoint ETAs
    segment_durations = [d for leg in osrm_route.get("legs", []) for d in leg.get("annotation", {}).get("duration", [])]
    if len(segment_durations) != len(coords) - 1:
        segment_durations = None

    duration = round(osrm_route["duration"])
    return {
        "distance_miles": round(osrm_route["distance"] * METERS_TO_MILES, 1),
        "duration_seconds": duration,
        "duration_hours": round(duration / 3600.0, 2),
        "coordinates": coords,
        "segment_durations": segment_durations
    }


def _overlap_cells(coords: List[List[float]]) -> Set[Tuple[int, int]]:
    return {(int(lat // OVERLAP_GRID_DEGREES), int(lon // OVERLAP_GRID_DEGREES)) for lat, lon in coords}


def _overlap_fraction(coords: List[List[float]], accepted_cells: Set[Tuple[int, int]]) -> float:
    """Share of the candidate's path that runs within ~1 grid cell of an accepted route."""
    step = max(1, len(coords) // 300)
    sample = coords[::step]
    shared = 0
    for lat, lon in sample:
        cy, cx = int(lat // OVERLAP_GRID_DEGREES), int(lon // OVERLAP_GRID_DEGREES)
        if any((cy + dy, cx + dx) in accepted_cells for dy in (-1, 0, 1) for dx in (-1, 0, 1)):
            shared += 1
    return shared / len(sample)


def _detour_waypoints(lat1: float, lon1: float, lat2: float, lon2: float) -> List[Tuple[str, Tuple[float, float]]]:
    """
    Waypoints perpendicular to the trip at distances proportional to its length, labelled by the
    side of the trip they actually fall on.
    """
    mid_lat, mid_lon = (lat1 + lat2) / 2, (lon1 + lon2) / 2
    # Work in a locally flat frame where one unit is the same distance east-west and north-south
    cos_lat = math.cos(math.radians(mid_lat)) or 1e-6
    dx, dy = (lon2 - lon1) * cos_lat, lat2 - lat1
    length = math.hypot(dx, dy) or 1e-6
    perp_x, perp_y = -dy / length, dx / length
    mostly_east_west = abs(dx) >= abs(dy)

    waypoints = []
    for fraction in WAYPOINT_OFFSET_FRACTIONS:
        for sign in (1, -1):
            off = sign * fraction * length
            wp_lat, wp_lon = mid_lat + perp_y * off, mid_lon + (perp_x * off) / cos_lat
            if mostly_east_west:
                side = "Northern" if wp_lat > mid_lat else "Southern"
            else:
                side = "Eastern" if wp_lon > mid_lon else "Western"
            waypoints.append((side, (wp_lat, wp_lon)))
    return waypoints


def get_three_routes(origin_str: str, destination_str: str) -> Dict[str, Any]:
    """
    Geocodes origin and destination and returns up to 3 distinct real road routes from OSRM:
    OSRM's own alternatives first, then detours through waypoints on either side of the trip.
    Near-duplicate and unrealistically long alternatives are rejected. Fewer than 3 routes are
    returned when the road network has no more distinct options; no routes are ever invented.
    Returns:
    {
        "origin": {"lat": float, "lon": float, "display_name": str},
        "destination": {"lat": float, "lon": float, "display_name": str},
        "routes": [route, ...]
    }
    """
    origin = geocode_location(origin_str)
    destination = geocode_location(destination_str)
    lat1, lon1 = origin["lat"], origin["lon"]
    lat2, lon2 = destination["lat"], destination["lon"]

    cache_key = f"routes:{lat1:.5f},{lon1:.5f}:{lat2:.5f},{lon2:.5f}"
    cached_routes = cache.get(cache_key)
    if cached_routes is not None:
        return {"origin": origin, "destination": destination, "routes": cached_routes}

    direct = _query_osrm([(lat1, lon1), (lat2, lon2)], alternatives=True)
    if direct is None:
        raise RoutingServiceError("The routing service is unavailable. Please try again shortly.")
    if direct.get("code") != "Ok" or not direct.get("routes"):
        raise NoRouteError("No drivable road route exists between these locations.")

    snaps = direct.get("waypoints", [])
    if snaps:
        for label, wp in (("origin", snaps[0]), ("destination", snaps[-1])):
            # OSRM snaps both ends onto one connected road network, so a far snap means either the
            # point is far from any road or the two places are not linked by road (e.g. across an ocean)
            if wp.get("distance", 0) > MAX_SNAP_METERS:
                raise NoRouteError(
                    f"No drivable road route connects these locations: the nearest road reachable from the "
                    f"other end is about {wp['distance'] * METERS_TO_MILES:,.0f} mi from the {label}."
                )

    routes: List[Dict[str, Any]] = []
    accepted_cells: Set[Tuple[int, int]] = set()

    def accept(candidate: Optional[Dict[str, Any]], name: str) -> None:
        if candidate is None or len(routes) >= 3:
            return
        if routes:
            if candidate["distance_miles"] > MAX_DETOUR_RATIO * routes[0]["distance_miles"]:
                return
            if _overlap_fraction(candidate["coordinates"], accepted_cells) > MAX_OVERLAP_FRACTION:
                return
        candidate["route_id"] = f"route_{len(routes) + 1}"
        candidate["name"] = name
        routes.append(candidate)
        accepted_cells.update(_overlap_cells(candidate["coordinates"]))

    # OSRM returns its fastest route first
    for i, r in enumerate(direct["routes"]):
        accept(_build_route(r), "Fastest Route" if i == 0 else f"Alternate Route {i}")

    for side, wp in _detour_waypoints(lat1, lon1, lat2, lon2):
        if len(routes) >= 3:
            break
        if any(r["name"] == f"{side} Alternate" for r in routes):
            continue  # already have a distinct route on this side; try the other side
        detour = _query_osrm([(lat1, lon1), wp, (lat2, lon2)], alternatives=False)
        if detour and detour.get("code") == "Ok" and detour.get("routes"):
            accept(_build_route(detour["routes"][0]), f"{side} Alternate")

    cache.set(cache_key, routes, ROUTE_CACHE_TTL_SECONDS)
    return {
        "origin": origin,
        "destination": destination,
        "routes": routes
    }
