from datetime import datetime
from typing import List, Dict, Any, Optional

from .routing_service import get_three_routes, simplify_coordinates
from .sampling_service import sample_route_checkpoints, choose_sampling_interval
from .weather_service import enrich_checkpoints_with_weather, fetch_forecasts
from .risk_engine import evaluate_weather_risk
from .scenario_service import build_storm
from .recommendation import rank_routes
from .corridor_service import sample_corridor_points, generate_corridor_heatmap_timeline


def _format_route(item: Dict[str, Any]) -> Dict[str, Any]:
    """Response shape for one ranked route (display geometry is simplified)."""
    r = item["route"]
    return {
        "route_id": r["route_id"],
        "name": r["name"],
        "distance_miles": r["distance_miles"],
        "duration_seconds": r["duration_seconds"],
        "duration_hours": r["duration_hours"],
        "rank": item["rank"],
        "is_recommended": item["is_recommended"],
        "recommendation_reason": item.get("recommendation_reason", ""),
        "summary": item["summary"],
        "coordinates": simplify_coordinates(r["coordinates"]),
        "checkpoints": item["checkpoints"]
    }


def _build_warnings(
    *,
    requested_interval: int,
    interval: int,
    longest_miles: float,
    no_safe_route: bool,
    route_count: int,
    scenario: str,
    unavailable_checkpoints: int,
    total_checkpoints: int,
    unavailable_heatmap_cells: int
) -> List[str]:
    warnings = []
    if interval != requested_interval:
        warnings.append(
            f"Checkpoint spacing widened from {requested_interval} to {interval} mi for this "
            f"{longest_miles:,.0f}-mi trip to stay within weather service limits."
        )
    if no_safe_route:
        warnings.append(
            "No safe route: every route crosses No Travel conditions at the planned departure time. "
            "Consider delaying departure; use the forecast slider to see when conditions improve."
        )
    if route_count < 3:
        warnings.append(
            f"Only {route_count} distinct road route{'s' if route_count != 1 else ''} found between these "
            "locations; other options were near-duplicates or unrealistically long detours."
        )
    if scenario != "live":
        warnings.append(f"Simulated '{scenario}' weather scenario: readings are synthetic, not a live forecast.")
    if unavailable_checkpoints:
        warnings.append(
            f"Forecast unavailable for {unavailable_checkpoints} of {total_checkpoints} checkpoints "
            "(weather service error or ETA outside the forecast window). Those checkpoints are shown as Unknown."
        )
    if unavailable_heatmap_cells:
        warnings.append("Some heatmap hours have no forecast coverage and are shown as Unknown.")
    return warnings


def plan_trip(
    origin: str,
    destination: str,
    departure: datetime,
    load_weight_lbs: float,
    sampling_interval_miles: int,
    scenario: str = "live"
) -> Dict[str, Any]:
    """
    Full trip analysis:
      1. Up to 3 distinct road routes (routing API, cached per origin/destination)
      2. Checkpoints every 10/25/50 mi with ETAs from per-segment travel times
      3. Weather at each checkpoint's ETA (one batched forecast fetch, or the simulated storm)
      4. Risk per checkpoint with load-weight rules, then the 4-tier route ranking
      5. The 0-48 h corridor heatmap
    `departure` is an aware UTC datetime shared by checkpoint ETAs and heatmap hour 0.
    Raises NoRouteError / ValueError for unplannable trips and RoutingServiceError when the
    routing API is unavailable.
    """
    route_result = get_three_routes(origin, destination)
    routes = route_result["routes"]
    origin_info = route_result["origin"]
    dest_info = route_result["destination"]

    longest_miles = max(r["distance_miles"] for r in routes)
    interval = choose_sampling_interval(sampling_interval_miles, longest_miles)

    route_checkpoints = [
        sample_route_checkpoints(
            coordinates=r["coordinates"],
            total_distance_miles=r["distance_miles"],
            total_duration_seconds=r["duration_seconds"],
            departure_time=departure,
            interval_miles=interval,
            segment_durations=r.get("segment_durations")
        )
        for r in routes
    ]
    corridor_points = sample_corridor_points(routes)

    # Live mode fetches forecasts for every checkpoint and heatmap point in one batched pass;
    # demo scenarios use a single simulated storm that both checkpoints and heatmap sample
    forecasts: Optional[Dict[Any, Any]] = None
    storm: Optional[Dict[str, Any]] = None
    if scenario == "live":
        all_points = [(c["lat"], c["lon"]) for chks in route_checkpoints for c in chks]
        all_points += [(p["lat"], p["lon"]) for p in corridor_points]
        forecasts = fetch_forecasts(all_points)
    else:
        storm = build_storm((origin_info["lat"], origin_info["lon"]),
                            (dest_info["lat"], dest_info["lon"]), departure)

    routes_with_checkpoints = []
    unavailable_checkpoints = 0
    total_checkpoints = 0
    for r, checkpoints in zip(routes, route_checkpoints):
        enriched = enrich_checkpoints_with_weather(checkpoints, scenario=scenario, forecasts=forecasts, storm=storm)
        for chk in enriched:
            chk["risk"] = evaluate_weather_risk(chk["weather"], load_weight_lbs)
            total_checkpoints += 1
            if chk["risk"]["overall_risk_score"] is None:
                unavailable_checkpoints += 1
        routes_with_checkpoints.append({"route": r, "checkpoints": enriched})

    ranked_routes = rank_routes(routes_with_checkpoints)

    heatmap = generate_corridor_heatmap_timeline(
        corridor_points=corridor_points,
        departure_time=departure,
        load_weight_lbs=load_weight_lbs,
        scenario=scenario,
        forecasts=forecasts,
        storm=storm
    )

    # Every route crosses No Travel conditions when even the top-ranked one does
    no_safe_route = ranked_routes[0]["summary"]["has_no_travel"]

    return {
        "origin": origin_info,
        "destination": dest_info,
        "departure_time": departure.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "load_weight_lbs": load_weight_lbs,
        "sampling_interval_miles": interval,
        "requested_sampling_interval_miles": sampling_interval_miles,
        "scenario": scenario,
        "warnings": _build_warnings(
            requested_interval=sampling_interval_miles,
            interval=interval,
            longest_miles=longest_miles,
            no_safe_route=no_safe_route,
            route_count=len(routes),
            scenario=scenario,
            unavailable_checkpoints=unavailable_checkpoints,
            total_checkpoints=total_checkpoints,
            unavailable_heatmap_cells=heatmap["unavailable_cells"],
        ),
        "no_safe_route": no_safe_route,
        "routes": [_format_route(item) for item in ranked_routes],
        "corridor_heatmap": heatmap
    }
