from django.contrib import admin

from apps.platform.models import PlatformSettings


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    list_display = ("mode", "updated_at", "updated_by")
    readonly_fields = ("id", "updated_at")
