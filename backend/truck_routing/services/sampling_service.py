from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from .common import haversine_miles

def parse_departure_time(departure_time_input: Any) -> datetime:
    """Parses departure time into an aware UTC datetime object."""
    if isinstance(departure_time_input, datetime):
        if departure_time_input.tzinfo is None:
            return departure_time_input.replace(tzinfo=timezone.utc)
        return departure_time_input.astimezone(timezone.utc)

    if isinstance(departure_time_input, str):
        # Support common ISO formats: 2026-10-24T08:00, 2026-10-24 08:00:00, etc.
        clean_str = departure_time_input.replace("Z", "+00:00").strip()
        try:
            dt = datetime.fromisoformat(clean_str)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass

    # Default fallback: current UTC time rounded up to nearest hour
    now = datetime.now(timezone.utc)
    return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

SAMPLING_INTERVALS_MILES = (10, 25, 50)
# Keeps very long (e.g. cross-continent) trips within the weather API's per-minute limits.
# 10 mi spacing is kept for trips up to 2,500 mi, which covers nearly all US trips.
MAX_CHECKPOINTS_PER_ROUTE = 250


def choose_sampling_interval(requested_miles: int, longest_route_miles: float) -> int:
    """
    The requested interval, widened to the next option (25, then 50 mi) when the longest
    route would otherwise exceed MAX_CHECKPOINTS_PER_ROUTE checkpoints.
    """
    options = [i for i in SAMPLING_INTERVALS_MILES if i >= requested_miles] or [SAMPLING_INTERVALS_MILES[-1]]
    for interval in options:
        if longest_route_miles / interval <= MAX_CHECKPOINTS_PER_ROUTE:
            return interval
    return options[-1]


def sample_route_checkpoints(
    coordinates: List[List[float]],
    total_distance_miles: float,
    total_duration_seconds: float,
    departure_time: Any,
    interval_miles: int = 25,
    segment_durations: Optional[List[float]] = None
) -> List[Dict[str, Any]]:
    """
    Discretizes a route polyline into checkpoints spaced every `interval_miles` (10, 25, or 50 miles)
    and computes the Estimated Arrival Time (ETA) at each checkpoint.

    `segment_durations` holds the routing engine's travel time (seconds) for each pair of
    consecutive vertices, so ETAs reflect slow urban and mountain segments. Without it, time is
    distributed in proportion to distance.

    Returns a list of checkpoint dictionaries:
    [
        {
            "checkpoint_index": 0,
            "mile_marker": 0.0,
            "lat": 41.8781,
            "lon": -87.6298,
            "eta_iso": "2026-10-24T08:00:00Z",
            "eta_display": "Oct 24, 08:00 AM UTC",
            "elapsed_seconds": 0,
            "elapsed_time_display": "0h 0m"
        },
        ...
    ]
    """
    if not coordinates or len(coordinates) < 2:
        raise ValueError("Route must contain at least 2 coordinate points to sample checkpoints.")

    # Validate interval options strictly against requirements (10, 25, 50 miles)
    valid_intervals = [10, 25, 50]
    if interval_miles not in valid_intervals:
        interval_miles = 25

    dep_dt = parse_departure_time(departure_time)

    # 1. Compute cumulative distance along each vertex of the polyline
    cum_distances = [0.0]
    for i in range(1, len(coordinates)):
        lat_prev, lon_prev = coordinates[i - 1][0], coordinates[i - 1][1]
        lat_curr, lon_curr = coordinates[i][0], coordinates[i][1]
        seg_dist = haversine_miles(lat_prev, lon_prev, lat_curr, lon_curr)
        cum_distances.append(cum_distances[-1] + seg_dist)

    poly_total_dist = cum_distances[-1] or 1.0
    # Scaling factor to match route engine's official total mileage
    scale_factor = (total_distance_miles / poly_total_dist) if total_distance_miles > 0 else 1.0
    scaled_cum_dist = [d * scale_factor for d in cum_distances]

    # Cumulative travel time at each vertex, scaled to the route's official total duration
    cum_times: Optional[List[float]] = None
    if segment_durations and len(segment_durations) == len(coordinates) - 1:
        cum_times = [0.0]
        for seg_dur in segment_durations:
            cum_times.append(cum_times[-1] + max(0.0, seg_dur))
        time_scale = (total_duration_seconds / cum_times[-1]) if cum_times[-1] > 0 else 0.0
        cum_times = [t * time_scale for t in cum_times]

    # 2. Determine target mile markers: 0, interval, 2*interval, ..., and destination
    target_miles: List[float] = []
    current_m = 0.0
    while current_m < total_distance_miles:
        target_miles.append(round(current_m, 1))
        current_m += interval_miles

    # Always ensure the final destination checkpoint is included
    if not target_miles or abs(target_miles[-1] - total_distance_miles) > 1.0:
        target_miles.append(round(total_distance_miles, 1))

    # 3. Interpolate coordinates and calculate ETAs for each target mile marker
    checkpoints = []
    seg_idx = 0
    num_pts = len(coordinates)

    for chk_idx, target_m in enumerate(target_miles):
        # Clamp target to total distance
        clamped_m = min(target_m, total_distance_miles)

        # Advance seg_idx to find bounding segment
        while seg_idx < num_pts - 2 and scaled_cum_dist[seg_idx + 1] < clamped_m:
            seg_idx += 1

        d_start = scaled_cum_dist[seg_idx]
        d_end = scaled_cum_dist[seg_idx + 1]
        seg_len = d_end - d_start

        if seg_len > 0:
            t = max(0.0, min(1.0, (clamped_m - d_start) / seg_len))
        else:
            t = 0.0

        lat_a, lon_a = coordinates[seg_idx]
        lat_b, lon_b = coordinates[seg_idx + 1]

        chk_lat = round(lat_a + t * (lat_b - lat_a), 5)
        chk_lon = round(lon_a + t * (lon_b - lon_a), 5)

        # Calculate ETA from cumulative travel time along the route
        if cum_times is not None:
            elapsed = cum_times[seg_idx] + t * (cum_times[seg_idx + 1] - cum_times[seg_idx])
        else:
            progress_ratio = (clamped_m / total_distance_miles) if total_distance_miles > 0 else 0.0
            elapsed = progress_ratio * total_duration_seconds
        elapsed_sec = int(round(elapsed))
        checkpoint_eta = dep_dt + timedelta(seconds=elapsed_sec)

        hours_elapsed = elapsed_sec // 3600
        mins_elapsed = (elapsed_sec % 3600) // 60

        checkpoints.append({
            "checkpoint_index": chk_idx,
            "mile_marker": round(clamped_m, 1),
            "lat": chk_lat,
            "lon": chk_lon,
            "eta_iso": checkpoint_eta.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "eta_display": checkpoint_eta.strftime("%b %d, %I:%M %p UTC"),
            "elapsed_seconds": elapsed_sec,
            "elapsed_time_display": f"{hours_elapsed}h {mins_elapsed}m"
        })

    return checkpoints
