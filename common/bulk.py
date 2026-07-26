"""Shared bulk-action helpers — serialize results, reuse across admin sections.

Per plan 0008: every bulk endpoint returns the same envelope shape so the
frontend's dual-toast pattern (success_count / failed_count) works identically
across staff, customers, support, providers, and credit packs.
"""


def serialize_bulk_result(results: dict) -> dict:
    """Shape a per-item {success, failed, total} dict into the bulk response envelope.

    *results* must be a dict with:
        success: list[dict]  — each dict at minimum {"id": str, "name": str}
        failed:  list[dict]  — each dict at minimum {"id": str, "name": str, "reason": str}
        total:   int         — total number of IDs submitted

    Returns the standardised envelope ready for APIResponse.success(data=…).
    """
    return {
        "success": results["success"],
        "failed": results["failed"],
        "total": results["total"],
        "success_count": len(results["success"]),
        "failed_count": len(results["failed"]),
    }
