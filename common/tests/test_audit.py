from django.test import RequestFactory, TestCase

from apps.accounts.tests.factories import UserFactory
from common.audit import log_admin_action
from shared.models import SystemLog


class LogAdminActionTests(TestCase):
    def setUp(self):
        self.actor = UserFactory(email="admin@example.com")

    def test_writes_expected_fields_without_request(self):
        log = log_admin_action(
            actor=self.actor,
            app_name="providers",
            action="capability_route_update",
            description="Updated route fast",
        )
        self.assertEqual(SystemLog.objects.count(), 1)
        self.assertEqual(log.app_name, "providers")
        self.assertEqual(log.action, "capability_route_update")
        self.assertEqual(log.description, "Updated route fast")
        self.assertEqual(log.severity, "info")
        self.assertEqual(log.user_id, str(self.actor.id))
        self.assertEqual(log.user_email, self.actor.email)
        self.assertIsNone(log.path)
        self.assertIsNone(log.method)
        self.assertIsNone(log.ip_address)

    def test_writes_request_metadata_when_given(self):
        request = RequestFactory().post("/api/v1/operations/settings", REMOTE_ADDR="127.0.0.1")
        log = log_admin_action(
            actor=self.actor,
            app_name="platform",
            action="platform_mode_change",
            description="Platform mode changed to live",
            request=request,
        )
        self.assertEqual(log.path, "/api/v1/operations/settings")
        self.assertEqual(log.method, "POST")
        self.assertEqual(log.ip_address, "127.0.0.1")

    def test_actor_none_is_handled_gracefully(self):
        log = log_admin_action(
            actor=None,
            app_name="accounts",
            action="system_event",
            description="No actor for this one",
        )
        self.assertIsNone(log.user_id)
        self.assertIsNone(log.user_email)

    def test_extra_data_defaults_to_empty_dict(self):
        log = log_admin_action(
            actor=self.actor, app_name="accounts", action="test", description="x",
        )
        self.assertEqual(log.extra_data, {})

    def test_custom_severity_and_extra_data(self):
        log = log_admin_action(
            actor=self.actor, app_name="accounts", action="test", description="x",
            severity="warning", extra_data={"foo": "bar"},
        )
        self.assertEqual(log.severity, "warning")
        self.assertEqual(log.extra_data, {"foo": "bar"})
