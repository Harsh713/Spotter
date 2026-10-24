"""
URL configuration for config project.
"""
from django.urls import path, include
from django.http import JsonResponse

def root_api_index(request):
    return JsonResponse({
        "service": "Weather-Aware Truck Routing API",
        "status": "online",
        "frontend_url": "http://localhost:5173",
        "endpoints": {
            "health": "/api/health/",
            "calculate_routes": "/api/routes/calculate/"
        },
        "message": "Backend API is running. Access the web interface at http://localhost:5173"
    })

urlpatterns = [
    path('', root_api_index, name='root-index'),
    path('api/', include('truck_routing.urls')),
]
