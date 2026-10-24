from datetime import timedelta
from django.utils import timezone
from rest_framework import serializers

# Open-Meteo forecasts run 7 days from today. Departure must leave room for the 48 h heatmap
# window, and may be slightly in the past to allow for clock skew and form-filling time.
MAX_DEPARTURE_AHEAD = timedelta(days=5)
MAX_DEPARTURE_PAST = timedelta(hours=1)

class RouteCalculationRequestSerializer(serializers.Serializer):
    origin = serializers.CharField(
        required=True,
        max_length=255,
        help_text="Origin address, city name, or coordinates (e.g., 'Chicago, IL' or '41.8781, -87.6298')"
    )
    destination = serializers.CharField(
        required=True,
        max_length=255,
        help_text="Destination address, city name, or coordinates (e.g., 'Denver, CO' or '39.7392, -104.9903')"
    )
    departure_time = serializers.DateTimeField(
        required=False,
        default=None,
        allow_null=True,
        help_text="Departure date/time in ISO-8601 format (e.g., '2026-10-24T08:00:00Z'). "
                  "Must be within the next 5 days; defaults to the next whole hour."
    )
    load_weight_lbs = serializers.FloatField(
        required=False,
        default=40000.0,
        min_value=0.0,
        max_value=120000.0,
        help_text="Total truck load weight in pounds (lbs), applied to wind risk escalation rules."
    )
    sampling_interval_miles = serializers.ChoiceField(
        choices=[10, 25, 50],
        default=25,
        required=False,
        help_text="Weather checkpoint sampling interval along the route (10, 25, or 50 miles)."
    )
    scenario = serializers.ChoiceField(
        choices=["live", "high_wind", "blizzard", "rainstorm"],
        default="live",
        required=False,
        help_text="Weather mode: 'live' queries Open-Meteo API; others inject deterministic scenario patterns for demonstration."
    )

    def validate_departure_time(self, value):
        if value is None:
            return value
        now = timezone.now()
        if value < now - MAX_DEPARTURE_PAST:
            raise serializers.ValidationError("Departure time is in the past. Choose a time from now onwards.")
        if value > now + MAX_DEPARTURE_AHEAD:
            raise serializers.ValidationError(
                "Departure time is more than 5 days ahead, beyond the weather forecast window."
            )
        return value

    def validate_origin(self, value):
        clean_val = value.strip()
        if not clean_val:
            raise serializers.ValidationError("Origin cannot be empty.")
        return clean_val

    def validate_destination(self, value):
        clean_val = value.strip()
        if not clean_val:
            raise serializers.ValidationError("Destination cannot be empty.")
        return clean_val
