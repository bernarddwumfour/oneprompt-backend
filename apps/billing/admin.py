from django.contrib import admin

from apps.billing.models import CreditPack, Payment, Purchase


@admin.register(CreditPack)
class CreditPackAdmin(admin.ModelAdmin):
    list_display = (
        "label", "currency", "amount_credits", "price_minor_units",
        "is_active", "sort_order",
    )
    list_editable = ("is_active", "sort_order")
    list_filter = ("currency", "is_active")


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = (
        "reference", "user", "credit_pack", "status", "currency",
        "created_at", "confirmed_at",
    )
    list_filter = ("status", "currency", "created_at")
    search_fields = ("reference", "user__email")
    readonly_fields = (
        "id", "user", "credit_pack", "reference", "status", "currency",
        "amount_minor_units", "created_at", "confirmed_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("purchase", "paystack_reference", "paystack_status", "verified_at")
    search_fields = ("paystack_reference", "purchase__reference")
    readonly_fields = (
        "id", "purchase", "paystack_reference", "paystack_status",
        "raw_webhook_payload", "verified_at",
    )
    ordering = ("-verified_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
