from django.urls import path

from apps.operations.views.billing_views import (
    credit_pack_bulk_action_view,
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
from apps.operations.views.staff_views import (
    staff_activate_view,
    staff_bulk_action_view,
    staff_deactivate_view,
    staff_list_view,
)
from apps.operations.views.support_views import (
    admin_ticket_bulk_action_view,
    admin_ticket_detail_view,
    admin_ticket_list_view,
    admin_ticket_reply_view,
    admin_ticket_status_view,
)
from apps.operations.views.customer_views import (
    customer_activate_view,
    customer_bulk_action_view,
    customer_correct_view,
    customer_deactivate_view,
    customer_detail_view,
    customer_list_view,
)
from apps.operations.views.analytics_views import (
    analytics_providers_view,
    analytics_trends_view,
)
from apps.operations.views.audit_views import audit_log_list_view
from apps.operations.views.invocation_views import invocation_list_view
from apps.operations.views.ledger_views import ledger_list_view
from apps.operations.views.overview_views import overview_view
from apps.operations.views.provider_views import (
    capability_route_bulk_action_view,
    capability_route_list_view,
    capability_route_update_view,
)

urlpatterns = [
    # Overview
    path("overview", overview_view, name="operations-overview"),
    # Customers
    path("customers", customer_list_view, name="operations-customers"),
    path("customers/bulk-action", customer_bulk_action_view, name="operations-customers-bulk-action"),
    path("customers/<uuid:user_id>", customer_detail_view, name="operations-customer-detail"),
    path("customers/<uuid:user_id>/correct", customer_correct_view, name="operations-customer-correct"),
    path("customers/<uuid:user_id>/activate", customer_activate_view, name="operations-customer-activate"),
    path("customers/<uuid:user_id>/deactivate", customer_deactivate_view, name="operations-customer-deactivate"),
    # Invocations
    path("invocations", invocation_list_view, name="operations-invocations"),
    # Capability routes
    path("capability-routes", capability_route_list_view, name="operations-capability-routes"),
    path("capability-routes/bulk-action", capability_route_bulk_action_view, name="operations-capability-routes-bulk-action"),
    path("capability-routes/<uuid:route_id>", capability_route_update_view, name="operations-capability-route-update"),
    # Ledger
    path("ledger", ledger_list_view, name="operations-ledger"),
    # Purchases & billing
    path("purchases", purchase_list_view, name="operations-purchases"),
    path("purchases/<uuid:purchase_id>/refund", purchase_refund_view, name="operations-purchase-refund"),
    path("credit-packs", credit_packs_admin_view, name="operations-credit-packs"),
    path("credit-packs/bulk-action", credit_pack_bulk_action_view, name="operations-credit-packs-bulk-action"),
    path("credit-packs/<uuid:pack_id>", credit_pack_update_view, name="operations-credit-pack-update"),
    # Conversations
    path("conversations", conversation_list_view, name="operations-conversations"),
    path("conversations/<uuid:conversation_id>", conversation_detail_view, name="operations-conversation-detail"),
    path("settings", platform_settings_view, name="operations-settings"),
    path("staff", staff_list_view, name="operations-staff"),
    path("staff/<uuid:user_id>/activate", staff_activate_view, name="operations-staff-activate"),
    path("staff/<uuid:user_id>/deactivate", staff_deactivate_view, name="operations-staff-deactivate"),
    path("staff/bulk-action", staff_bulk_action_view, name="operations-staff-bulk-action"),
    path("support/tickets", admin_ticket_list_view, name="operations-support-tickets"),
    path("support/tickets/bulk-action", admin_ticket_bulk_action_view, name="operations-support-tickets-bulk-action"),
    path("support/tickets/<uuid:ticket_id>", admin_ticket_detail_view, name="operations-support-ticket-detail"),
    path("support/tickets/<uuid:ticket_id>/reply", admin_ticket_reply_view, name="operations-support-ticket-reply"),
    path("support/tickets/<uuid:ticket_id>/status", admin_ticket_status_view, name="operations-support-ticket-status"),
    path("analytics/trends", analytics_trends_view, name="operations-analytics-trends"),
    path("analytics/providers", analytics_providers_view, name="operations-analytics-providers"),
    path("audit-logs", audit_log_list_view, name="operations-audit-logs"),
]
