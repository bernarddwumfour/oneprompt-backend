from django.urls import path

from apps.operations.views.billing_views import (
    credit_pack_update_view,
    credit_packs_admin_view,
    purchase_list_view,
    purchase_refund_view,
)
from apps.operations.views.conversation_views import (
    conversation_detail_view,
    conversation_list_view,
)
from apps.operations.views.settings_views import platform_settings_view
from apps.operations.views.customer_views import (
    customer_correct_view,
    customer_detail_view,
    customer_list_view,
)
from apps.operations.views.invocation_views import invocation_list_view
from apps.operations.views.ledger_views import ledger_list_view
from apps.operations.views.overview_views import overview_view
from apps.operations.views.provider_views import (
    capability_route_list_view,
    capability_route_update_view,
)

urlpatterns = [
    # Overview
    path("overview", overview_view, name="operations-overview"),
    # Customers
    path("customers", customer_list_view, name="operations-customers"),
    path("customers/<uuid:user_id>", customer_detail_view, name="operations-customer-detail"),
    path("customers/<uuid:user_id>/correct", customer_correct_view, name="operations-customer-correct"),
    # Invocations
    path("invocations", invocation_list_view, name="operations-invocations"),
    # Capability routes
    path("capability-routes", capability_route_list_view, name="operations-capability-routes"),
    path("capability-routes/<uuid:route_id>", capability_route_update_view, name="operations-capability-route-update"),
    # Ledger
    path("ledger", ledger_list_view, name="operations-ledger"),
    # Purchases & billing
    path("purchases", purchase_list_view, name="operations-purchases"),
    path("purchases/<uuid:purchase_id>/refund", purchase_refund_view, name="operations-purchase-refund"),
    path("credit-packs", credit_packs_admin_view, name="operations-credit-packs"),
    path("credit-packs/<uuid:pack_id>", credit_pack_update_view, name="operations-credit-pack-update"),
    # Conversations
    path("conversations", conversation_list_view, name="operations-conversations"),
    path("conversations/<uuid:conversation_id>", conversation_detail_view, name="operations-conversation-detail"),
    path("settings", platform_settings_view, name="operations-settings"),

]
