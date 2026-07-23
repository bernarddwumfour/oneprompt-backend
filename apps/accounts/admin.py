from django.contrib import admin

from apps.accounts.models import EmailVerificationToken, RefreshToken, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "full_name", "country", "is_email_verified", "is_staff", "date_joined")
    list_filter = ("is_email_verified", "is_staff", "country")
    search_fields = ("email", "full_name")
    ordering = ("-date_joined",)


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "token", "created_at", "expires_at", "used_at")
    readonly_fields = ("id", "user", "token", "created_at", "expires_at", "used_at")
    search_fields = ("user__email", "token")


@admin.register(RefreshToken)
class RefreshTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "jti", "expires_at", "created_at")
    readonly_fields = ("id", "user", "jti", "expires_at", "created_at")
    search_fields = ("user__email",)
