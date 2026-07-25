"""Staff management — promote/demote admin users."""

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.accounts.models import User
from apps.operations.selectors.operations_selectors import search_customers
from common.audit import log_admin_action
from common.decorators import jwt_required, role_required
from common.responses import APIResponse
from common.utils import parse_pagination


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def staff_list_view(request):
    search = request.GET.get("search", "")
    try:
        page, limit = parse_pagination(request)
    except ValueError as e:
        return APIResponse.bad_request(str(e))
    result = search_customers(search=search, page=page, limit=limit)
    return APIResponse.success(data=result)


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
def staff_promote_view(request, user_id):
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return APIResponse.not_found("User not found.")
    if user.is_staff:
        return APIResponse.bad_request("User is already an admin.")
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    log_admin_action(
        actor=request.user, app_name="accounts", action="staff_promoted",
        description=f"{request.user.email} granted admin to {user.email}",
        request=request,
    )
    return APIResponse.success(message=f"{user.email} is now an admin.")


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
def staff_demote_view(request, user_id):
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return APIResponse.not_found("User not found.")
    if not user.is_staff:
        return APIResponse.bad_request("User is not an admin.")
    if user.id == request.user.id:
        return APIResponse.bad_request("You cannot demote yourself.")
    if User.objects.filter(is_staff=True).count() <= 1:
        return APIResponse.bad_request("Cannot demote the last remaining admin.")
    user.is_staff = False
    user.save(update_fields=["is_staff"])
    log_admin_action(
        actor=request.user, app_name="accounts", action="staff_demoted",
        description=f"{request.user.email} revoked admin from {user.email}",
        request=request,
    )
    return APIResponse.success(message=f"{user.email} is no longer an admin.")
