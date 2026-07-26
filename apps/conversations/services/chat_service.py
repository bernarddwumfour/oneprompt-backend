"""
Chat service — the full send_message flow: estimate → reserve → stream → capture.

Per plan 0001 §Backend-architecture:
1. Estimate cost
2. Reserve credits (raises ValueError if insufficient — before any Message is
   created, and before the caller receives a generator to iterate)
3. Create user Message + ModelInvocation
4. Stream chunks, accumulate full text
5. On completion: create assistant Message, capture credits
6. On cancellation: release reserved credits, no assistant Message
7. On failure: release reserved credits

``send_message`` itself is a plain function, not a generator — all
validation and the credit reservation happen eagerly so a ValueError (unknown
capability, insufficient credits) can be caught by the caller *before* any
HTTP response has started streaming. Only the actual token-by-token work
happens in the returned generator (``_stream_and_settle``).
"""

import logging
from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone

from apps.conversations.models import Conversation, Message, ModelInvocation
from apps.credits.models import CreditWallet
from apps.credits.services.ledger_service import capture, release, reserve
from apps.providers.models import CapabilityRoute
from apps.providers.registry import get_default_route, get_provider

logger = logging.getLogger(__name__)


def send_message(
    *,
    conversation: Conversation,
    user,
    prompt: str,
    capability: str | None = None,
    capabilities: list[str] | None = None,
    message_content: str | None = None,
):
    """Validate, reserve credits, and return a generator of SSE
    ``(event_type, data_dict)`` tuples for the caller to stream.

    Raises ValueError immediately (before returning) if:
    - The provider/capability is unknown or inactive
    - The wallet can't cover the estimated cost
    """
    requested_capabilities = list(
        dict.fromkeys(capabilities or ([capability] if capability else []))
    )
    if len(requested_capabilities) > 3:
        raise ValueError("You can reference at most 3 models.")

    if not requested_capabilities:
        default_route = get_default_route()
        if default_route is None:
            raise ValueError("No active capability routes configured.")
        requested_capabilities = [default_route.slug]

    wallet = CreditWallet.objects.get(user=user)
    history = _build_history(conversation)
    prepared = []

    for requested_capability in requested_capabilities:
        provider = get_provider(requested_capability)
        if provider is None:
            raise ValueError(f"Unknown capability: {requested_capability}")
        route = CapabilityRoute.objects.get(
            slug=requested_capability, is_active=True
        )
        prepared.append(
            {
                "capability": requested_capability,
                "provider": provider,
                "is_free": route.is_free,
                "estimated": (
                    Decimal("0.00")
                    if route.is_free
                    else provider.estimate(prompt=prompt, history=history)
                ),
            }
        )

    reserved = []
    try:
        for item in prepared:
            invocation = ModelInvocation.objects.create(
                conversation=conversation,
                capability=item["capability"],
                status="pending",
                credits_estimated=item["estimated"],
            )
            if item["is_free"]:
                invocation.status = "streaming"
                invocation.save(update_fields=["status"])
                reserved.append(
                    {
                        **item,
                        "invocation": invocation,
                        "reservation": None,
                    }
                )
                continue
            try:
                reservation = reserve(
                    wallet=wallet,
                    amount=item["estimated"],
                    idempotency_key=f"reserve:{invocation.id}",
                    reference={"invocation_id": str(invocation.id)},
                )
            except ValueError:
                invocation.delete()
                raise

            invocation.reservation_entry = reservation
            invocation.status = "streaming"
            invocation.save(update_fields=["reservation_entry", "status"])
            reserved.append(
                {
                    **item,
                    "invocation": invocation,
                    "reservation": reservation,
                }
            )
    except ValueError:
        for item in reserved:
            if item["reservation"] is not None:
                release(
                    reservation_entry=item["reservation"],
                    idempotency_key=f"release:{item['invocation'].id}",
                )
            item["invocation"].status = "cancelled"
            item["invocation"].completed_at = timezone.now()
            item["invocation"].save(update_fields=["status", "completed_at"])
        raise

    Message.objects.create(
        conversation=conversation,
        role="user",
        content=message_content or prompt,
    )

    return _stream_all(
        prepared=reserved,
        prompt=prompt,
        history=history,
    )


def _stream_all(*, prepared, prompt, history):
    """Stream up to three model responses for one persisted user message."""
    yield (
        "batch_start",
        {
            "invocations": [
                {
                    "invocation_id": str(item["invocation"].id),
                    "capability": item["capability"],
                }
                for item in prepared
            ]
        },
    )

    for item in prepared:
        capability = item["capability"]
        for event_type, data in _stream_and_settle(
            provider=item["provider"],
            prompt=prompt,
            history=history,
            invocation=item["invocation"],
            reservation=item["reservation"],
            is_free=item["is_free"],
        ):
            yield (
                event_type,
                {
                    **data,
                    "capability": capability,
                },
            )

    yield ("complete", {"count": len(prepared)})


def _stream_and_settle(
    *, provider, prompt, history, invocation, reservation, is_free=False
):
    """Generator — the actual SSE event stream for one invocation.

    Yields a ``start`` event first (carrying the invocation id, so the
    client can cancel a still-in-progress stream), then ``chunk`` events,
    then exactly one terminal event: ``done``, ``cancelled``, or ``error``.
    """
    yield ("start", {"invocation_id": str(invocation.id)})

    accumulated_text = ""
    try:
        for chunk in provider.stream_response(
            prompt=prompt, history=history, invocation_id=str(invocation.id)
        ):
            accumulated_text += chunk
            yield ("chunk", {"text": chunk})

        if cache.get(f"cancel:{invocation.id}"):
            # 6. Cancelled — release the full reservation, no assistant message
            if reservation is not None:
                release(
                    reservation_entry=reservation,
                    idempotency_key=f"release:{invocation.id}",
                )
            invocation.status = "cancelled"
            invocation.completed_at = timezone.now()
            invocation.save()
            yield (
                "cancelled",
                {"invocation_id": str(invocation.id), "content": accumulated_text},
            )
            return

        # 5. Success — capture
        usage = provider.normalize_usage(
            raw_usage={
                "output_text": accumulated_text,
                "prompt": prompt,
                "usage": getattr(provider, "last_usage", None),
            }
        )
        if is_free:
            usage["credits"] = Decimal("0.00")

        assistant_msg = Message.objects.create(
            conversation=invocation.conversation,
            role="assistant",
            content=accumulated_text,
        )

        capture_entry = None
        if reservation is not None:
            capture_entry = capture(
                reservation_entry=reservation,
                actual_amount=usage["credits"],
                idempotency_key=f"capture:{invocation.id}",
            )

        # Compute provider cost in USD from the route's wholesale rates
        provider_cost = _compute_provider_cost(
            invocation=invocation,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
        )

        invocation.status = "succeeded"
        invocation.message = assistant_msg
        invocation.input_tokens = usage["input_tokens"]
        invocation.output_tokens = usage["output_tokens"]
        invocation.credits_charged = usage["credits"]
        invocation.provider_cost_usd = provider_cost
        invocation.capture_entry = capture_entry
        invocation.completed_at = timezone.now()
        invocation.save()

        yield (
            "done",
            {
                "message_id": str(assistant_msg.id),
                "invocation_id": str(invocation.id),
                "credits_charged": str(usage["credits"]),
                "content": accumulated_text,
            },
        )

    except Exception as exc:
        # 7. Failure — release
        logger.error("Chat streaming failed for invocation %s: %s", invocation.id, exc)
        try:
            if reservation is not None:
                release(
                    reservation_entry=reservation,
                    idempotency_key=f"release:{invocation.id}",
                )
        except Exception as release_exc:
            logger.error("Failed to release reservation: %s", release_exc)

        invocation.status = "failed"
        invocation.error_message = str(exc)[:500]
        invocation.completed_at = timezone.now()
        invocation.save()

        yield ("error", {"message": "An error occurred during generation. Your credits have been released. Please try again."})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_provider_cost(
    *, invocation, input_tokens: int, output_tokens: int
) -> Decimal | None:
    """Calculate the wholesale USD cost of an invocation.

    Reads the CapabilityRoute's provider_cost_input/output rates.
    Returns None for stub routes (no real cost) or if the route isn't found.
    """
    from apps.providers.models import CapabilityRoute

    try:
        route = CapabilityRoute.objects.get(slug=invocation.capability)
    except CapabilityRoute.DoesNotExist:
        return None

    from apps.platform.selectors import get_platform_mode

    if route.provider_key == "stub" or get_platform_mode() == "test":
        return Decimal("0.0")

    cost = (
        Decimal(input_tokens) / 1000 * route.provider_cost_input
        + Decimal(output_tokens) / 1000 * route.provider_cost_output
    )
    return cost.quantize(Decimal("0.000001"))


def _build_history(conversation: Conversation) -> list[dict]:
    """Return conversation messages as a list of {role, content} dicts."""
    return [
        {"role": m.role, "content": m.content}
        for m in conversation.messages.order_by("created_at")
    ]
