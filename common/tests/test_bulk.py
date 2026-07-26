from django.test import SimpleTestCase

from common.bulk import serialize_bulk_result
from common.validators import validate_bulk_action


class SerializeBulkResultTests(SimpleTestCase):
    def test_shapes_counts_from_success_and_failed_lists(self):
        results = {
            "success": [{"id": "1", "name": "A"}, {"id": "2", "name": "B"}],
            "failed": [{"id": "3", "name": "C", "reason": "Not found."}],
            "total": 3,
        }
        data = serialize_bulk_result(results)
        self.assertEqual(data["success_count"], 2)
        self.assertEqual(data["failed_count"], 1)
        self.assertEqual(data["total"], 3)
        self.assertEqual(data["success"], results["success"])
        self.assertEqual(data["failed"], results["failed"])

    def test_all_success(self):
        results = {"success": [{"id": "1", "name": "A"}], "failed": [], "total": 1}
        data = serialize_bulk_result(results)
        self.assertEqual(data["success_count"], 1)
        self.assertEqual(data["failed_count"], 0)

    def test_all_failed(self):
        results = {"success": [], "failed": [{"id": "1", "name": "A", "reason": "x"}], "total": 1}
        data = serialize_bulk_result(results)
        self.assertEqual(data["success_count"], 0)
        self.assertEqual(data["failed_count"], 1)


class ValidateBulkActionTests(SimpleTestCase):
    def test_valid_action_and_ids_passes(self):
        cleaned, errors = validate_bulk_action(
            {"action": "activate", "ids": ["1", "2"]}, ["activate", "deactivate"]
        )
        self.assertEqual(errors, {})
        self.assertEqual(cleaned, {"action": "activate", "ids": ["1", "2"]})

    def test_action_not_in_whitelist_rejected(self):
        cleaned, errors = validate_bulk_action(
            {"action": "delete", "ids": ["1"]}, ["activate", "deactivate"]
        )
        self.assertEqual(cleaned, {})
        self.assertIn("action", errors)

    def test_missing_action_rejected(self):
        cleaned, errors = validate_bulk_action({"ids": ["1"]}, ["activate"])
        self.assertIn("action", errors)

    def test_empty_ids_rejected(self):
        cleaned, errors = validate_bulk_action(
            {"action": "activate", "ids": []}, ["activate"]
        )
        self.assertIn("ids", errors)

    def test_ids_not_a_list_rejected(self):
        cleaned, errors = validate_bulk_action(
            {"action": "activate", "ids": "not-a-list"}, ["activate"]
        )
        self.assertIn("ids", errors)

    def test_missing_ids_rejected(self):
        cleaned, errors = validate_bulk_action({"action": "activate"}, ["activate"])
        self.assertIn("ids", errors)

    def test_both_invalid_returns_both_errors(self):
        cleaned, errors = validate_bulk_action({}, ["activate"])
        self.assertIn("action", errors)
        self.assertIn("ids", errors)
        self.assertEqual(cleaned, {})
