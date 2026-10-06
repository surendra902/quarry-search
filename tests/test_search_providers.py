"""Tests for search provider adapters (SerpApi free-tier quota, Exa query rotation, and verification)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from quarry.storage import QuarryStorage
from quarry.sources.serp_source import SerpSource, MAX_MONTHLY_SEARCHES, MAX_HOURLY_SEARCHES


def mock_response(payload=None, status=200, headers=None):
    res = Mock(status_code=status, headers=headers or {})
    res.json.return_value = payload or {}
    return res


class SerpSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_serp.db")
        self.storage = QuarryStorage(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_api_key_reports_unavailable(self):
        with patch.dict(os.environ, {"SERPAPI_API_KEY": ""}, clear=True):
            source = SerpSource(api_key=None, storage=self.storage)
            results = source.discover_new(limit=10)
            self.assertEqual(results, [])
            self.assertEqual(source.last_report["status"], "unavailable")
            self.assertIn("SERPAPI_API_KEY is not configured", source.last_report["messages"][0])

    def test_monthly_quota_hard_cap_enforced(self):
        self.storage.set_state("serpapi_month_key", source_month := "2026-10")
        self.storage.set_state("serpapi_monthly_usage", MAX_MONTHLY_SEARCHES)

        source = SerpSource(api_key="test_key", storage=self.storage)
        with patch.object(source, "_get_current_month_key", return_value=source_month):
            results = source.discover_new(limit=10)
            self.assertEqual(results, [])
            self.assertEqual(source.last_report["status"], "unavailable")
            self.assertTrue(any(f"monthly free quota hard cap ({MAX_MONTHLY_SEARCHES})" in m for m in source.last_report["messages"]))

    def test_hourly_quota_hard_cap_enforced(self):
        self.storage.set_state("serpapi_hour_key", source_hour := "2026-10-06T11")
        self.storage.set_state("serpapi_hourly_usage", MAX_HOURLY_SEARCHES)

        source = SerpSource(api_key="test_key", storage=self.storage)
        with patch.object(source, "_get_current_hour_key", return_value=source_hour):
            results = source.discover_new(limit=10)
            self.assertEqual(results, [])
            self.assertEqual(source.last_report["status"], "rate_limited")
            self.assertTrue(any(f"hourly free quota limit ({MAX_HOURLY_SEARCHES})" in m for m in source.last_report["messages"]))

    def test_quota_resets_when_month_or_hour_changes(self):
        self.storage.set_state("serpapi_month_key", "2026-09")
        self.storage.set_state("serpapi_monthly_usage", 250)
        self.storage.set_state("serpapi_hour_key", "2026-10-06T10")
        self.storage.set_state("serpapi_hourly_usage", 50)

        source = SerpSource(api_key="test_key", storage=self.storage)
        with patch.object(source, "_get_current_month_key", return_value="2026-10"), \
             patch.object(source, "_get_current_hour_key", return_value="2026-10-06T11"), \
             patch("quarry.sources.serp_source.requests.get", return_value=mock_response({"organic_results": []})):
            source.discover_new(limit=10)
            self.assertEqual(self.storage.get_state("serpapi_month_key"), "2026-10")
            self.assertLessEqual(self.storage.get_state("serpapi_monthly_usage"), 2)
            self.assertEqual(self.storage.get_state("serpapi_hour_key"), "2026-10-06T11")
            self.assertLessEqual(self.storage.get_state("serpapi_hourly_usage"), 2)

    def test_query_rotation_advances_cursor_across_calls(self):
        source = SerpSource(api_key="test_key", storage=self.storage)
        with patch("quarry.sources.serp_source.requests.get", return_value=mock_response({"organic_results": []})):
            source.discover_new(limit=10)
            self.assertEqual(self.storage.get_state("serpapi_cycle_idx"), 1)
            source.discover_new(limit=10)
            self.assertEqual(self.storage.get_state("serpapi_cycle_idx"), 2)

    def test_page_verification_recovers_referral_when_snippet_omits_it(self):
        serp_payload = {
            "organic_results": [
                {
                    "link": "https://example.com/guide-to-claude",
                    "title": "A Complete Guide to Claude Pro & Claude Code",
                    "snippet": "Here is an overview of Claude features and guest passes for new users.",
                    "date": "2026-10-06"
                }
            ]
        }
        mock_html = (
            "<html><body>"
            "<h1>Guide</h1>"
            "<p>Get your guest pass here: "
            "<a href='https://claude.ai/referral/SerpAnchorCode123'>Claim Claude Pass</a></p>"
            "</body></html>"
        )

        source = SerpSource(api_key="test_key", storage=self.storage)
        with patch("quarry.sources.serp_source.requests.get", return_value=mock_response(serp_payload)), \
             patch("quarry.search_discovery._default_http_fetch", return_value={"status": 200, "body": mock_html, "headers": {}}):
            records = source.discover_new(limit=10)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].referral_code, "SerpAnchorCode123")
            self.assertEqual(records[0].url, "https://claude.ai/referral/SerpAnchorCode123")
            self.assertEqual(records[0].source_url, "https://example.com/guide-to-claude")
            self.assertEqual(records[0].platform, "Web (Google / example.com)")

    def test_find_sources_filters_for_target_code(self):
        serp_payload = {
            "organic_results": [
                {
                    "link": "https://example.com/shared-passes",
                    "title": "Free Claude Passes",
                    "snippet": "Use my link https://claude.ai/referral/TargetCode999 for free pro access!"
                }
            ]
        }
        source = SerpSource(api_key="test_key", storage=self.storage)
        with patch("quarry.sources.serp_source.requests.get", return_value=mock_response(serp_payload)):
            records = source.find_sources("TargetCode999", limit=5)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].referral_code, "TargetCode999")

            # Searching for a different code returns empty list
            records_diff = source.find_sources("OtherCode000", limit=5)
            self.assertEqual(records_diff, [])


if __name__ == "__main__":
    unittest.main()
