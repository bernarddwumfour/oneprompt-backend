from django.contrib import admin

from apps.providers.models import CapabilityRoute


@admin.register(CapabilityRoute)
class CapabilityRouteAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "slug",
        "provider_key",
        "upstream_model",
        "is_active",
        "is_default",
        "sort_order",
    )
    list_filter = ("is_active", "provider_key")
    list_editable = ("is_active", "is_default", "sort_order")
    search_fields = ("label", "slug", "upstream_model")
    ordering = ("sort_order", "label")
