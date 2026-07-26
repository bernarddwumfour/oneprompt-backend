import json

from django.test import TestCase

from apps.accounts.tests.factories import UserFactory
from common.jwt import encode_access_token
from shared.models import SystemLog


class UserTicketViewsTests(TestCase):
    def setUp(self):
        self.owner = UserFactory(email="owner@example.com")
        self.intruder = UserFactory(email="intruder@example.com")
        self.owner_token = encode_access_token(self.owner)
        self.intruder_token = encode_access_token(self.intruder)

    def _create_ticket(self, token, subject="Help", content="I need help"):
        return self.client.post(
            "/api/v1/support/tickets",
            data=json.dumps({"subject": subject, "content": content}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def test_create_ticket(self):
        response = self._create_ticket(self.owner_token)
        self.assertEqual(response.status_code, 201)
        ticket = response.json()["data"]["ticket"]
        self.assertEqual(ticket["subject"], "Help")
        self.assertEqual(ticket["status"], "open")

    def test_create_requires_subject_and_content(self):
        self.assertEqual(self._create_ticket(self.owner_token, subject="").status_code, 400)
        self.assertEqual(self._create_ticket(self.owner_token, content="").status_code, 400)

    def test_list_only_shows_own_tickets(self):
        self._create_ticket(self.owner_token, subject="Owner's ticket")
        self._create_ticket(self.intruder_token, subject="Intruder's ticket")

        response = self.client.get(
            "/api/v1/support/tickets", HTTP_AUTHORIZATION=f"Bearer {self.owner_token}"
        )
        subjects = [t["subject"] for t in response.json()["data"]["tickets"]]
        self.assertEqual(subjects, ["Owner's ticket"])

    def test_owner_can_view_detail_intruder_cannot(self):
        ticket_id = self._create_ticket(self.owner_token).json()["data"]["ticket"]["id"]

        owner_resp = self.client.get(
            f"/api/v1/support/tickets/{ticket_id}", HTTP_AUTHORIZATION=f"Bearer {self.owner_token}"
        )
        intruder_resp = self.client.get(
            f"/api/v1/support/tickets/{ticket_id}", HTTP_AUTHORIZATION=f"Bearer {self.intruder_token}"
        )
        self.assertEqual(owner_resp.status_code, 200)
        self.assertEqual(intruder_resp.status_code, 404)

    def test_owner_can_reply_intruder_cannot(self):
        ticket_id = self._create_ticket(self.owner_token).json()["data"]["ticket"]["id"]

        owner_resp = self.client.post(
            f"/api/v1/support/tickets/{ticket_id}/messages",
            data=json.dumps({"content": "Any update?"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.owner_token}",
        )
        intruder_resp = self.client.post(
            f"/api/v1/support/tickets/{ticket_id}/messages",
            data=json.dumps({"content": "Sneaky reply"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.intruder_token}",
        )
        self.assertEqual(owner_resp.status_code, 201)
        self.assertEqual(intruder_resp.status_code, 404)

    def test_reply_shows_correct_author_flag(self):
        ticket_id = self._create_ticket(self.owner_token).json()["data"]["ticket"]["id"]
        detail = self.client.get(
            f"/api/v1/support/tickets/{ticket_id}", HTTP_AUTHORIZATION=f"Bearer {self.owner_token}"
        ).json()["data"]
        self.assertFalse(detail["messages"][0]["author_is_admin"])


class AdminTicketViewsTests(TestCase):
    def setUp(self):
        self.admin = UserFactory(email="admin@example.com", is_staff=True)
        self.user = UserFactory(email="user@example.com")
        self.admin_token = encode_access_token(self.admin)
        self.user_token = encode_access_token(self.user)

        create_resp = self.client.post(
            "/api/v1/support/tickets",
            data=json.dumps({"subject": "Help", "content": "I need help"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.user_token}",
        )
        self.ticket_id = create_resp.json()["data"]["ticket"]["id"]

    def test_list_and_detail_require_admin(self):
        self.assertEqual(
            self.client.get("/api/v1/operations/support/tickets", HTTP_AUTHORIZATION=f"Bearer {self.user_token}").status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/api/v1/operations/support/tickets", HTTP_AUTHORIZATION=f"Bearer {self.admin_token}").status_code,
            200,
        )

    def test_admin_can_view_any_ticket(self):
        response = self.client.get(
            f"/api/v1/operations/support/tickets/{self.ticket_id}",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["data"]["messages"]), 1)

    def test_admin_reply_is_flagged_as_admin(self):
        self.client.post(
            f"/api/v1/operations/support/tickets/{self.ticket_id}/reply",
            data=json.dumps({"content": "We're looking into it."}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        detail = self.client.get(
            f"/api/v1/operations/support/tickets/{self.ticket_id}",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        ).json()["data"]
        self.assertTrue(detail["messages"][-1]["author_is_admin"])

    def test_status_change_updates_and_logs(self):
        before = SystemLog.objects.count()
        response = self.client.patch(
            f"/api/v1/operations/support/tickets/{self.ticket_id}/status",
            data=json.dumps({"status": "resolved"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["ticket"]["status"], "resolved")
        self.assertEqual(SystemLog.objects.count(), before + 1)
        log = SystemLog.objects.latest("created_at")
        self.assertEqual(log.action, "ticket_status_change")

    def test_status_change_rejects_invalid_status(self):
        response = self.client.patch(
            f"/api/v1/operations/support/tickets/{self.ticket_id}/status",
            data=json.dumps({"status": "not-a-real-status"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        self.assertEqual(response.status_code, 400)

    def test_status_change_requires_admin(self):
        response = self.client.patch(
            f"/api/v1/operations/support/tickets/{self.ticket_id}/status",
            data=json.dumps({"status": "resolved"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.user_token}",
        )
        self.assertEqual(response.status_code, 403)

    # -- bulk -------------------------------------------------------------

    def _bulk(self, token, action, ids):
        return self.client.post(
            "/api/v1/operations/support/tickets/bulk-action",
            data=json.dumps({"action": action, "ids": ids}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def _second_ticket_id(self):
        resp = self.client.post(
            "/api/v1/support/tickets",
            data=json.dumps({"subject": "Second", "content": "Also help"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.user_token}",
        )
        return resp.json()["data"]["ticket"]["id"]

    def test_bulk_close_sets_status_to_closed(self):
        # Regression test: bulk action names ("close"/"resolve") are verbs,
        # but SupportTicket.status stores the adjective form ("closed").
        # A prior version of this endpoint passed "close" straight through
        # as the status value, which is not a valid TICKET_STATUS_CHOICES
        # member — every bulk close/resolve silently failed 100% of the
        # time. This test would fail against that regression.
        response = self._bulk(self.admin_token, "close", [self.ticket_id])
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["success_count"], 1)
        self.assertEqual(data["failed_count"], 0)

        detail = self.client.get(
            f"/api/v1/operations/support/tickets/{self.ticket_id}",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        ).json()["data"]
        self.assertEqual(detail["ticket"]["status"], "closed")

    def test_bulk_resolve_sets_status_to_resolved(self):
        response = self._bulk(self.admin_token, "resolve", [self.ticket_id])
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["success_count"], 1)

        detail = self.client.get(
            f"/api/v1/operations/support/tickets/{self.ticket_id}",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        ).json()["data"]
        self.assertEqual(detail["ticket"]["status"], "resolved")

    def test_bulk_close_multiple_tickets(self):
        second_id = self._second_ticket_id()
        response = self._bulk(self.admin_token, "close", [self.ticket_id, second_id])
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["success_count"], 2)
        self.assertEqual(data["failed_count"], 0)

    def test_bulk_unknown_ticket_id_reported_as_failed(self):
        import uuid

        response = self._bulk(self.admin_token, "close", [str(uuid.uuid4())])
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["success_count"], 0)
        self.assertEqual(data["failed_count"], 1)
        self.assertEqual(data["failed"][0]["reason"], "Not found.")

    def test_bulk_partial_failure(self):
        import uuid

        response = self._bulk(
            self.admin_token, "close", [self.ticket_id, str(uuid.uuid4())]
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["success_count"], 1)
        self.assertEqual(data["failed_count"], 1)

    def test_bulk_requires_admin(self):
        response = self._bulk(self.user_token, "close", [self.ticket_id])
        self.assertEqual(response.status_code, 403)

    def test_bulk_invalid_action_rejected(self):
        response = self._bulk(self.admin_token, "delete", [self.ticket_id])
        self.assertEqual(response.status_code, 422)

    def test_bulk_empty_ids_rejected(self):
        response = self._bulk(self.admin_token, "close", [])
        self.assertEqual(response.status_code, 422)
