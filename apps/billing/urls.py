from django.urls import path

from apps.billing.views.purchase_views import (
    create_purchase_view,
    credit_packs_view,
    purchase_detail_view,
)
from apps.billing.views.webhook_views import paystack_webhook_view

urlpatterns = [
    path("credit-packs", credit_packs_view, name="credit-packs"),
    path("purchases", create_purchase_view, name="create-purchase"),
    path("purchases/<uuid:purchase_id>", purchase_detail_view, name="purchase-detail"),
    path("webhooks/paystack", paystack_webhook_view, name="paystack-webhook"),
]
