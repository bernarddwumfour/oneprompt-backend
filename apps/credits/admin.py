from django.contrib import admin

from apps.credits.models import CreditLedgerEntry, CreditWallet


@admin.register(CreditWallet)
class CreditWalletAdmin(admin.ModelAdmin):
    list_display = ("user", "currency", "balance", "reserved", "created_at")
    search_fields = ("user__email",)
    readonly_fields = ("id", "user", "balance", "reserved", "created_at", "updated_at")


@admin.register(CreditLedgerEntry)
class CreditLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("entry_type", "amount", "wallet", "idempotency_key", "created_at")
    list_filter = ("entry_type", "created_at")
    search_fields = ("wallet__user__email", "idempotency_key")
    ordering = ("-created_at",)
    readonly_fields = (
        "id", "wallet", "entry_type", "amount", "idempotency_key",
        "reference", "reason", "created_by", "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
