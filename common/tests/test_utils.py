from django.test import RequestFactory, SimpleTestCase

from common.utils import parse_date_range_param


class ParseDateRangeParamTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_parses_both_bounds(self):
        request = self.factory.get(
            "/", {"created_at": "from=2024-01-01T00:00:00Z&to=2024-01-31T00:00:00Z"}
        )
        from_dt, to_dt = parse_date_range_param(request, "created_at")
        self.assertEqual(from_dt.isoformat(), "2024-01-01T00:00:00+00:00")
        self.assertEqual(to_dt.isoformat(), "2024-01-31T00:00:00+00:00")

    def test_parses_from_only(self):
        request = self.factory.get("/", {"created_at": "from=2024-01-01T00:00:00Z"})
        from_dt, to_dt = parse_date_range_param(request, "created_at")
        self.assertIsNotNone(from_dt)
        self.assertIsNone(to_dt)

    def test_missing_param_returns_none_none(self):
        request = self.factory.get("/")
        from_dt, to_dt = parse_date_range_param(request, "created_at")
        self.assertIsNone(from_dt)
        self.assertIsNone(to_dt)

    def test_malformed_value_treated_as_absent(self):
        request = self.factory.get("/", {"created_at": "from=not-a-date"})
        from_dt, to_dt = parse_date_range_param(request, "created_at")
        self.assertIsNone(from_dt)
        self.assertIsNone(to_dt)
