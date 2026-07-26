from django.test import TestCase

from apps.accounts.tests.factories import UserFactory
from common.audit import log_admin_action
from common.jwt import encode_access_token


class AuditLogListViewTests(TestCase):
    def setUp(self):
        self.admin = UserFactory(email="admin@example.com", is_staff=True)
        self.user = UserFactory(email="user@example.com")
        self.admin_token = encode_access_token(self.admin)
        self.user_token = encode_access_token(self.user)

        log_admin_action(
            actor=self.admin, app_name="providers", action="capability_route_update",
            description="Updated route fast", severity="info",
        )
        log_admin_action(
            actor=self.admin, app_name="platform", action="platform_mode_change",
            description="Platform mode changed to live", severity="warning",
        )
        log_admin_action(
            actor=self.admin, app_name="accounts", action="staff_promoted",
            description="Promoted a user", severity="info",
        )

    def _list(self, token, **params):
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return self.client.get(
            f"/api/v1/operations/audit-logs?{query}",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def test_requires_admin(self):
        self.assertEqual(self._list(self.user_token).status_code, 403)
        self.assertEqual(self._list(self.admin_token).status_code, 200)

    def test_lists_all_logs_ordered_newest_first(self):
        data = self._list(self.admin_token).json()["data"]
        self.assertEqual(data["total"], 3)
        actions = [log["action"] for log in data["logs"]]
        self.assertEqual(actions, ["staff_promoted", "platform_mode_change", "capability_route_update"])

    def test_filters_by_severity(self):
        data = self._list(self.admin_token, severity="warning").json()["data"]
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["logs"][0]["action"], "platform_mode_change")

    def test_filters_by_app_name(self):
        data = self._list(self.admin_token, app_name="providers").json()["data"]
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["logs"][0]["action"], "capability_route_update")

    def test_filters_by_action(self):
        data = self._list(self.admin_token, action="staff_promoted").json()["data"]
        self.assertEqual(data["total"], 1)

    def test_status_code_present_for_the_sort_option_to_render(self):
        data = self._list(self.admin_token).json()["data"]
        self.assertIn("status_code", data["logs"][0])

    def test_pagination(self):
        data = self._list(self.admin_token, page=1, limit=2).json()["data"]
        self.assertEqual(len(data["logs"]), 2)
        self.assertEqual(data["total"], 3)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["limit"], 2)

        page2 = self._list(self.admin_token, page=2, limit=2).json()["data"]
        self.assertEqual(len(page2["logs"]), 1)

    def test_invalid_pagination_params_rejected(self):
        self.assertEqual(self._list(self.admin_token, page="abc").status_code, 400)
