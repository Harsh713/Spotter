from django.urls import path
from .views import HealthCheckView, RouteCalculationView

urlpatterns = [
    path('health/', HealthCheckView.as_view(), name='health'),
    path('routes/calculate/', RouteCalculationView.as_view(), name='route-calculate'),
]
