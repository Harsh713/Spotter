from typing import List, Dict, Any, Tuple
from .risk_engine import UNKNOWN_RISK

def summarize_route_risk(
    route: Dict[str, Any],
    checkpoints: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Computes cumulative mileage breakdown by risk level and weighted average risk score for a single route.
    """
    if not checkpoints:
        return {
            "severe_miles": 0.0,
            "no_travel_miles": 0.0,
            "high_miles": 0.0,
            "moderate_miles": 0.0,
            "low_miles": 0.0,
            "unknown_miles": 0.0,
            "average_risk_score": None,
            "has_no_travel": False,
            "checkpoints_count": 0
        }

    total_dist = route.get("distance_miles", 0.0)
    num_pts = len(checkpoints)

    severe_mi = 0.0
    no_travel_mi = 0.0
    high_mi = 0.0
    mod_mi = 0.0
    low_mi = 0.0
    unknown_mi = 0.0
    weighted_score_sum = 0.0

    for i in range(num_pts):
        chk = checkpoints[i]
        risk = chk.get("risk", {}).get("overall_risk", "Low")
        score = chk.get("risk", {}).get("overall_risk_score", 1)

        # Determine segment distance represented by this checkpoint
        if num_pts == 1:
            seg_dist = total_dist
        elif i == 0:
            seg_dist = (checkpoints[1]["mile_marker"] - checkpoints[0]["mile_marker"]) / 2.0
        elif i == num_pts - 1:
            seg_dist = (checkpoints[-1]["mile_marker"] - checkpoints[-2]["mile_marker"]) / 2.0
        else:
            seg_dist = (checkpoints[i + 1]["mile_marker"] - checkpoints[i - 1]["mile_marker"]) / 2.0

        seg_dist = max(0.0, seg_dist)

        # Missing forecasts are tracked separately and never averaged in as Low risk
        if risk == UNKNOWN_RISK or score is None:
            unknown_mi += seg_dist
            continue

        weighted_score_sum += score * seg_dist

        if risk == "No Travel":
            no_travel_mi += seg_dist
            severe_mi += seg_dist  # No Travel counts as Severe tier (or worse)
        elif risk == "Severe":
            severe_mi += seg_dist
        elif risk == "High":
            high_mi += seg_dist
        elif risk == "Moderate":
            mod_mi += seg_dist
        else:
            low_mi += seg_dist

    known_dist = severe_mi + high_mi + mod_mi + low_mi
    avg_score = round(weighted_score_sum / known_dist, 2) if known_dist > 0 else None

    return {
        "severe_miles": round(severe_mi, 1),
        "no_travel_miles": round(no_travel_mi, 1),
        "high_miles": round(high_mi, 1),
        "moderate_miles": round(mod_mi, 1),
        "low_miles": round(low_mi, 1),
        "unknown_miles": round(unknown_mi, 1),
        "average_risk_score": avg_score,
        "has_no_travel": no_travel_mi > 0.0,
        "checkpoints_count": num_pts
    }

def rank_routes(routes_with_checkpoints: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ranks routes according to the 4-tier preference hierarchy:
      1. Fewest Severe miles (including No Travel)
      2. Fewest High miles
      3. Lowest average risk
      4. Shortest travel times

    Marks rank #1 with `is_recommended: True` and adds comparison metrics.
    """
    if not routes_with_checkpoints:
        return []

    # Calculate summaries for each route
    for item in routes_with_checkpoints:
        route = item["route"]
        chk_list = item["checkpoints"]
        item["summary"] = summarize_route_risk(route, chk_list)

    # Multi-tier sorting key:
    # (severe_miles, high_miles, average_risk_score, duration_seconds)
    def sorting_key(item: Dict[str, Any]) -> Tuple[float, float, float, float]:
        summary = item["summary"]
        route = item["route"]
        # Route with No Travel gets highest severity penalty
        severe_metric = summary["severe_miles"] + (10000.0 if summary["has_no_travel"] else 0.0)
        # A route with no usable forecast at all cannot be shown to be safe
        avg = summary["average_risk_score"]
        return (
            severe_metric,
            summary["high_miles"],
            avg if avg is not None else 5.0,
            float(route.get("duration_seconds", 0.0))
        )

    sorted_routes = sorted(routes_with_checkpoints, key=sorting_key)

    # Assign ranks and badges
    best_item = sorted_routes[0]
    best_summary = best_item["summary"]
    best_route = best_item["route"]

    for idx, item in enumerate(sorted_routes):
        is_rec = (idx == 0)
        item["rank"] = idx + 1
        item["is_recommended"] = is_rec

        if is_rec:
            # Generate justification statement
            if best_summary["average_risk_score"] is None:
                reason = "No forecast data was available for any route; weather risk could not be assessed."
            elif best_summary["has_no_travel"]:
                reason = (
                    f"No safe route: every option crosses No Travel conditions. This route is the least risky "
                    f"({best_summary['no_travel_miles']} No Travel mi), but delaying departure is advised."
                )
            elif best_summary["severe_miles"] == 0.0 and best_summary["high_miles"] == 0.0:
                reason = "Optimal Safe Corridor: Zero severe or high weather risk miles throughout the entire trip."
            elif best_summary["severe_miles"] == 0.0:
                reason = f"Safest Choice: 0 severe miles and only {best_summary['high_miles']} high-risk miles."
            else:
                reason = f"Best Route: Minimizes severe exposure to {best_summary['severe_miles']} miles, offering the lowest risk profile."
        else:
            # Comparison note relative to recommended
            diff_time_mins = int((item["route"]["duration_seconds"] - best_route["duration_seconds"]) / 60)
            time_str = f"{abs(diff_time_mins)} min {'slower' if diff_time_mins > 0 else 'faster'}"
            extra_severe = round(item["summary"]["severe_miles"] - best_summary["severe_miles"], 1)
            if extra_severe > 0:
                reason = f"Alternative: Has +{extra_severe} more severe weather miles ({time_str})."
            else:
                reason = f"Alternative Route ({time_str})."

        unknown_mi = item["summary"]["unknown_miles"]
        if unknown_mi > 0:
            reason += f" Forecast unavailable for {unknown_mi} mi; risk on those miles was not assessed."
        item["recommendation_reason"] = reason

    return sorted_routes
