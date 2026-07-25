from django.contrib import admin

from apps.support.models import SupportTicket, TicketMessage


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("subject", "user", "status", "created_at", "updated_at")
    list_filter = ("status",)
    search_fields = ("subject", "user__email")


@admin.register(TicketMessage)
class TicketMessageAdmin(admin.ModelAdmin):
    list_display = ("ticket", "author", "created_at")
    search_fields = ("content", "author__email")
