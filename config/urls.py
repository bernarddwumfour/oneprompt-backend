"""
URL configuration for the OnePrompt backend.

Per BACKEND-RULES.main.md §3: every API route lives under /api/, no DRF
routers, manual path()/include() only. Each app's own urls.py is still
empty (Stage 1) — see plans/0001-repo-scaffolding-auth-ledger-mvp-chat.md.
"""

from django.contrib import admin
from django.urls import include, path

from apps.accounts.views.auth_views import me_view
from apps.conversations.views.message_views import cancel_invocation_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "api/v1/",
        include(
            [
                path("auth/", include("apps.accounts.urls")),
                path("me", me_view, name="me"),
                path("wallet/", include("apps.credits.urls")),
                path("conversations/", include("apps.conversations.urls")),
                path("capabilities", include("apps.providers.urls")),
                path("billing/", include("apps.billing.urls")),
                path("operations/", include("apps.operations.urls")),
                path(
                    "invocations/<uuid:invocation_id>/cancel",
                    cancel_invocation_view,
                    name="cancel-invocation",
                ),
            ]
        ),
    ),
]
