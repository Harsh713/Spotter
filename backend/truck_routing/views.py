import logging
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import RouteCalculationRequestSerializer
from .services.routing_service import RoutingServiceError
from .services.sampling_service import parse_departure_time
from .services.trip_planner import plan_trip

logger = logging.getLogger(__name__)

class HealthCheckView(APIView):
    """
    Health check endpoint returning service status.
    """
    def get(self, request):
        return Response({
            "status": "healthy",
            "service": "Weather-Aware Truck Routing API",
            "version": "1.0.0"
        }, status=status.HTTP_200_OK)

class RouteCalculationView(APIView):
    """
    Calculates up to 3 routes with weather checkpoints, load-adjusted risk, a recommendation
    and the 0-48h corridor heatmap (see services/trip_planner.py).
    """
    def post(self, request):
        serializer = RouteCalculationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "status": "error",
                "message": "Invalid request parameters",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            result = plan_trip(
                origin=data["origin"],
                destination=data["destination"],
                # Parsed once so checkpoint ETAs and heatmap hour 0 share the same reference time
                departure=parse_departure_time(data.get("departure_time")),
                load_weight_lbs=data["load_weight_lbs"],
                sampling_interval_miles=data["sampling_interval_miles"],
                scenario=data["scenario"]
            )
            return Response({"status": "success", **result}, status=status.HTTP_200_OK)

        except RoutingServiceError as rse:
            return Response({
                "status": "error",
                "message": str(rse)
            }, status=status.HTTP_502_BAD_GATEWAY)
        except ValueError as ve:
            return Response({
                "status": "error",
                "message": str(ve)
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Unexpected error calculating truck routes")
            return Response({
                "status": "error",
                "message": f"Server error: {e}" if settings.DEBUG else "Unexpected server error while calculating routes."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
