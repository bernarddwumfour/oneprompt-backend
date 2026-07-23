from django.urls import path

from apps.providers.views.capability_views import capabilities_view

urlpatterns = [
    path("", capabilities_view, name="capabilities"),
]
