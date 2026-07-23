from decimal import Decimal

from django.test import TestCase

from apps.credits.services import ledger_service as L
from apps.credits.tests.factories import CreditWalletFactory


class LedgerInvariantTests(TestCase):
    def setUp(self):
        self.wallet = CreditWalletFactory()

    def test_balance_equals_sum_of_balance_affecting_entries(self):
        L.purchase_credit(wallet=self.wallet, amount=Decimal("10.00"), idempotency_key="p1", reference={})
        L.promotional_credit(wallet=self.wallet, amount=Decimal("5.00"), idempotency_key="p2", reference={})
        L.refund(wallet=self.wallet, amount=Decimal("1.00"), idempotency_key="p3", reference={})

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("16.00"))

    def test_reserve_then_partial_capture_resolves_hold_and_releases_remainder(self):
        L.purchase_credit(wallet=self.wallet, amount=Decimal("10.00"), idempotency_key="fund1", reference={})
        reservation = L.reserve(wallet=self.wallet, amount=Decimal("2.00"), idempotency_key="res1", reference={})
        L.capture(reservation_entry=reservation, actual_amount=Decimal("1.50"), idempotency_key="cap1")

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("8.50"))
        self.assertEqual(self.wallet.reserved, Decimal("0.00"))

    def test_reserve_then_release_returns_reserved_to_zero_balance_unaffected(self):
        L.purchase_credit(wallet=self.wallet, amount=Decimal("10.00"), idempotency_key="fund2", reference={})
        reservation = L.reserve(wallet=self.wallet, amount=Decimal("3.00"), idempotency_key="res2", reference={})
        L.release(reservation_entry=reservation, idempotency_key="rel1")

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("10.00"))
        self.assertEqual(self.wallet.reserved, Decimal("0.00"))

    def test_capture_handles_overage_without_driving_reserved_negative(self):
        """actual_amount exceeding the original reservation must still fully
        resolve the hold, not just subtract actual_amount from it."""
        L.purchase_credit(wallet=self.wallet, amount=Decimal("10.00"), idempotency_key="fund3", reference={})
        reservation = L.reserve(wallet=self.wallet, amount=Decimal("1.00"), idempotency_key="res3", reference={})
        L.capture(reservation_entry=reservation, actual_amount=Decimal("2.00"), idempotency_key="cap2")

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("8.00"))
        self.assertEqual(self.wallet.reserved, Decimal("0.00"))

    def test_duplicate_idempotency_key_on_purchase_is_a_no_op(self):
        L.purchase_credit(wallet=self.wallet, amount=Decimal("10.00"), idempotency_key="dup1", reference={})
        L.purchase_credit(wallet=self.wallet, amount=Decimal("10.00"), idempotency_key="dup1", reference={})

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("10.00"))

    def test_duplicate_idempotency_key_on_capture_is_a_no_op(self):
        L.purchase_credit(wallet=self.wallet, amount=Decimal("10.00"), idempotency_key="fund4", reference={})
        reservation = L.reserve(wallet=self.wallet, amount=Decimal("2.00"), idempotency_key="res4", reference={})
        L.capture(reservation_entry=reservation, actual_amount=Decimal("2.00"), idempotency_key="cap3")
        L.capture(reservation_entry=reservation, actual_amount=Decimal("2.00"), idempotency_key="cap3")

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("8.00"))
        self.assertEqual(self.wallet.reserved, Decimal("0.00"))

    def test_capturing_an_already_released_reservation_raises(self):
        L.purchase_credit(wallet=self.wallet, amount=Decimal("10.00"), idempotency_key="fund5", reference={})
        reservation = L.reserve(wallet=self.wallet, amount=Decimal("2.00"), idempotency_key="res5", reference={})
        L.release(reservation_entry=reservation, idempotency_key="rel2")

        with self.assertRaises(L.ReservationConflict):
            L.capture(reservation_entry=reservation, actual_amount=Decimal("1.00"), idempotency_key="cap4")

    def test_reserve_beyond_available_balance_raises(self):
        L.purchase_credit(wallet=self.wallet, amount=Decimal("5.00"), idempotency_key="fund6", reference={})

        with self.assertRaises(ValueError):
            L.reserve(wallet=self.wallet, amount=Decimal("10.00"), idempotency_key="res6", reference={})

    def test_admin_correct_requires_a_reason(self):
        with self.assertRaises(ValueError):
            L.admin_correct(
                wallet=self.wallet,
                amount=Decimal("1.00"),
                direction="credit",
                reason="",
                actor=None,
                idempotency_key="admin1",
            )
