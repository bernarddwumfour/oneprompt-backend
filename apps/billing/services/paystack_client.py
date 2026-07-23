"""PaystackClient — all Paystack API calls in one class.

Per BACKEND-RULES §10 service-client pattern and plan 0002:
- timeout on every call
- raises PaystackError on failure
- secret key from settings, never exposed
"""

import hashlib
import hmac
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class PaystackError(Exception):
    """Raised when a Paystack API call fails."""


class PaystackClient:
    def __init__(self):
        self.base_url = "https://api.paystack.co"
        self.headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
        }

    def initialize_transaction(
        self,
        *,
        email: str,
        amount_minor_units: int,
        currency: str,
        reference: str,
        callback_url: str,
    ) -> dict:
        """Initialize a Paystack transaction. Returns the full response dict."""
        url = f"{self.base_url}/transaction/initialize"
        body = {
            "email": email,
            "amount": amount_minor_units,
            "currency": currency,
            "reference": reference,
            "callback_url": callback_url,
        }
        return self._request("POST", url, json=body)

    def verify_transaction(self, *, reference: str) -> dict:
        """Verify a transaction with Paystack. Returns the full response dict."""
        url = f"{self.base_url}/transaction/verify/{reference}"
        return self._request("GET", url)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _request(self, method: str, url: str, **kwargs) -> dict:
        try:
            resp = requests.request(
                method, url, headers=self.headers, timeout=25, **kwargs
            )
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            raise PaystackError(f"Paystack unavailable: {e}") from e

        if not resp.ok:
            msg = data.get("message", "Paystack rejected request")
            raise PaystackError(msg)

        return data

    @staticmethod
    def verify_signature(raw_body: bytes, signature_header: str) -> bool:
        """Verify an X-Paystack-Signature header against *raw_body*.

        Returns True if the HMAC-SHA512 matches.
        """
        if not signature_header or not settings.PAYSTACK_SECRET_KEY:
            return False
        computed = hmac.new(
            key=settings.PAYSTACK_SECRET_KEY.encode(),
            msg=raw_body,
            digestmod=hashlib.sha512,
        ).hexdigest()
        return hmac.compare_digest(computed, signature_header)
