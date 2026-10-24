from typing import Dict, Any, Tuple

# Risk Levels & Numerical Severity Scores
RISK_SCORES: Dict[str, int] = {
    "Low": 1,
    "Moderate": 2,
    "High": 3,
    "Severe": 4,
    "No Travel": 5
}

SCORE_TO_RISK: Dict[int, str] = {v: k for k, v in RISK_SCORES.items()}

RISK_COLORS: Dict[str, str] = {
    "Low": "#10B981",       # Green
    "Moderate": "#F59E0B",  # Amber / Yellow
    "High": "#F97316",      # Orange
    "Severe": "#EF4444",    # Red
    "No Travel": "#7F1D1D",  # Dark Crimson / Maroon
    "Unknown": "#64748B"     # Slate: forecast unavailable
}

# Assigned when no forecast exists for a checkpoint. It has no numeric score, so it never
# counts as Low risk and is excluded from the average risk score.
UNKNOWN_RISK = "Unknown"

def classify_wind_risk(wind_mph: float, load_weight_lbs: float) -> Tuple[str, bool, str]:
    """
    Classifies wind risk applying the exact baseline thresholds and truck load weight rules.

    Thresholds:
      <25 mph: Low
      25–34 mph: Moderate
      35–44 mph: High
      45–54 mph: Severe
      ≥55 mph: No Travel

    Load rules:
      • ≥55 mph → No Travel for any load
      • 45–54 mph + >30,000 lb → No Travel
      • 35–44 mph + >40,000 lb → Severe

    Returns:
      (risk_level, load_rule_triggered, rule_description)
    """
    # Rule 1: ≥55 mph → No Travel for any load
    if wind_mph >= 55.0:
        return "No Travel", True, f"Wind speed {wind_mph:.1f} mph exceeds critical 55 mph threshold (No Travel for any load)."

    # Rule 2: 45–54 mph
    if 45.0 <= wind_mph < 55.0:
        if load_weight_lbs > 30000.0:
            return "No Travel", True, f"Wind speed {wind_mph:.1f} mph with load {load_weight_lbs:,.0f} lb (>30,000 lb) escalated from Severe to No Travel."
        return "Severe", False, f"Wind speed {wind_mph:.1f} mph qualifies as Severe risk."

    # Rule 3: 35–44 mph
    if 35.0 <= wind_mph < 45.0:
        if load_weight_lbs > 40000.0:
            return "Severe", True, f"Wind speed {wind_mph:.1f} mph with load {load_weight_lbs:,.0f} lb (>40,000 lb) escalated from High to Severe."
        return "High", False, f"Wind speed {wind_mph:.1f} mph qualifies as High risk."

    # Moderate: 25–34 mph
    if 25.0 <= wind_mph < 35.0:
        return "Moderate", False, f"Wind speed {wind_mph:.1f} mph qualifies as Moderate risk."

    # Low: <25 mph
    return "Low", False, f"Wind speed {wind_mph:.1f} mph qualifies as Low risk."

def classify_rain_risk(rain_in_per_hr: float) -> str:
    """
    Classifies rain risk according to specified thresholds:
      <0.10 in/hr: Low
      0.10–0.25 in/hr: Moderate
      0.25–0.50 in/hr: High
      0.50–1.00 in/hr: Severe
      >1.00 in/hr: No Travel
    """
    if rain_in_per_hr > 1.00:
        return "No Travel"
    if 0.50 <= rain_in_per_hr <= 1.00:
        return "Severe"
    if 0.25 <= rain_in_per_hr < 0.50:
        return "High"
    if 0.10 <= rain_in_per_hr < 0.25:
        return "Moderate"
    return "Low"

def classify_snow_risk(snow_in_per_hr: float) -> str:
    """
    Classifies snow risk according to specified thresholds:
      <0.5 in/hr: Low
      0.5–1.0 in/hr: Moderate
      1.0–2.0 in/hr: High
      2.0–3.0 in/hr: Severe
      >3.0 in/hr: No Travel
    """
    if snow_in_per_hr > 3.00:
        return "No Travel"
    if 2.00 <= snow_in_per_hr <= 3.00:
        return "Severe"
    if 1.00 <= snow_in_per_hr < 2.00:
        return "High"
    if 0.50 <= snow_in_per_hr < 1.00:
        return "Moderate"
    return "Low"

def evaluate_checkpoint_risk(
    wind_mph: float,
    rain_in_per_hr: float,
    snow_in_per_hr: float,
    load_weight_lbs: float
) -> Dict[str, Any]:
    """
    Computes condition-specific and overall risk classifications for a checkpoint.
    Overall risk is the maximum severity among Wind (with load adjustment), Rain, and Snow.
    """
    wind_risk, load_triggered, wind_desc = classify_wind_risk(wind_mph, load_weight_lbs)
    rain_risk = classify_rain_risk(rain_in_per_hr)
    snow_risk = classify_snow_risk(snow_in_per_hr)

    wind_score = RISK_SCORES[wind_risk]
    rain_score = RISK_SCORES[rain_risk]
    snow_score = RISK_SCORES[snow_risk]

    max_score = max(wind_score, rain_score, snow_score)
    overall_risk = SCORE_TO_RISK[max_score]

    # Identify primary driving risk factor
    factors = []
    if wind_score == max_score and wind_score > 1:
        factors.append(f"Wind ({wind_risk})")
    if rain_score == max_score and rain_score > 1:
        factors.append(f"Rain ({rain_risk})")
    if snow_score == max_score and snow_score > 1:
        factors.append(f"Snow ({snow_risk})")

    primary_factor = ", ".join(factors) if factors else "Normal Conditions"

    return {
        "overall_risk": overall_risk,
        "overall_risk_score": max_score,
        "color": RISK_COLORS[overall_risk],
        "wind_risk": wind_risk,
        "wind_risk_score": wind_score,
        "rain_risk": rain_risk,
        "rain_risk_score": rain_score,
        "snow_risk": snow_risk,
        "snow_risk_score": snow_score,
        "load_rule_applied": load_triggered,
        "load_rule_description": wind_desc,
        "primary_risk_factor": primary_factor
    }

def unknown_checkpoint_risk() -> Dict[str, Any]:
    """Risk record for a checkpoint whose weather forecast is unavailable."""
    return {
        "overall_risk": UNKNOWN_RISK,
        "overall_risk_score": None,
        "color": RISK_COLORS[UNKNOWN_RISK],
        "wind_risk": UNKNOWN_RISK,
        "wind_risk_score": None,
        "rain_risk": UNKNOWN_RISK,
        "rain_risk_score": None,
        "snow_risk": UNKNOWN_RISK,
        "snow_risk_score": None,
        "load_rule_applied": False,
        "load_rule_description": "Forecast unavailable for this location and time; risk could not be assessed.",
        "primary_risk_factor": "Forecast unavailable"
    }

def evaluate_weather_risk(weather: Dict[str, Any], load_weight_lbs: float) -> Dict[str, Any]:
    """Evaluates a weather record, returning Unknown risk when any reading is missing."""
    wind = weather.get("wind_speed_mph")
    rain = weather.get("rain_in_per_hr")
    snow = weather.get("snow_in_per_hr")
    if wind is None or rain is None or snow is None:
        return unknown_checkpoint_risk()
    return evaluate_checkpoint_risk(wind, rain, snow, load_weight_lbs)
