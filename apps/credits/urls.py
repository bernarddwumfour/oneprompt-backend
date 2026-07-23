from django.urls import path

from apps.credits.views.wallet_views import wallet_ledger_view, wallet_view

urlpatterns = [
    path("", wallet_view, name="wallet"),
    path("ledger", wallet_ledger_view, name="wallet-ledger"),
]
