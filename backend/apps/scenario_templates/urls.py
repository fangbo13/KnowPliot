# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ScenarioTemplateViewSet

router = DefaultRouter()
router.register(r"", ScenarioTemplateViewSet, basename="template")

urlpatterns = [
    path("", include(router.urls)),
]
