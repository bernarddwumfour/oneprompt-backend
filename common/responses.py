"""
APIResponse factory — the single response builder used by every view.

Per BACKEND-RULES.main.md §5: every endpoint returns the standard envelope
{"success": bool, "message": str, "data": ...}. Never call JsonResponse
directly.
"""

from http import HTTPStatus

from django.http import JsonResponse


class APIResponse:
    """Standard JSON response envelope for all API endpoints."""

    @staticmethod
    def success(data=None, message="Success", status=HTTPStatus.OK):
        body = {"success": True, "message": message}
        if data is not None:
            body["data"] = data
        return JsonResponse(body, status=status)

    @staticmethod
    def created(data=None, message="Created"):
        return APIResponse.success(data=data, message=message, status=HTTPStatus.CREATED)

    @staticmethod
    def bad_request(message="Bad request", errors=None):
        body = {"success": False, "message": message}
        if errors:
            body["errors"] = errors
        return JsonResponse(body, status=HTTPStatus.BAD_REQUEST)

    @staticmethod
    def unauthorized(message="Authentication required"):
        return JsonResponse(
            {"success": False, "message": message},
            status=HTTPStatus.UNAUTHORIZED,
        )

    @staticmethod
    def forbidden(message="Insufficient permissions"):
        return JsonResponse(
            {"success": False, "message": message},
            status=HTTPStatus.FORBIDDEN,
        )

    @staticmethod
    def not_found(message="Not found"):
        return JsonResponse(
            {"success": False, "message": message},
            status=HTTPStatus.NOT_FOUND,
        )

    @staticmethod
    def conflict(message="Conflict", errors=None):
        body = {"success": False, "message": message}
        if errors:
            body["errors"] = errors
        return JsonResponse(body, status=HTTPStatus.CONFLICT)

    @staticmethod
    def validation_error(errors):
        return JsonResponse(
            {"success": False, "message": "Validation failed", "errors": errors},
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
        )

    @staticmethod
    def server_error(message="Internal server error"):
        return JsonResponse(
            {"success": False, "message": message},
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
