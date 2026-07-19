from django.urls import path

from .views import public_readiness, system_readiness

urlpatterns = [
    path("health/ready/", public_readiness, name="public-readiness"),
    path("admin/system/readiness/", system_readiness, name="system-readiness"),
]
