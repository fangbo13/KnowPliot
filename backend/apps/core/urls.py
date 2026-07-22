from django.urls import path

from .views import public_readiness, system_readiness
from .prometheus import prometheus_metrics

urlpatterns = [
    path("health/ready/", public_readiness, name="public-readiness"),
    path("admin/system/readiness/", system_readiness, name="system-readiness"),
    path("internal/metrics/", prometheus_metrics, name="internal-metrics"),
]
