"""Tests for evidence freshness, native dates vs scan dates, and daily yield metrics."""
import unittest
from datetime import datetime, timezone

from quarry.metrics import publication_time, yield_summary


class FreshnessEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 6, 12, 0, 0, tzinfo=timezone.utc)

    def test_scan_and_index_dates_are_not_publication_dates(self):
        scan_row = {
            'referral_code': 'Code1',
            'published_at': '2026-10-06T11:00:00Z',
            'timestamp_basis': 'urlscan_submission_time'
        }
        self.assertIsNone(publication_time(scan_row))

        index_row = {
            'referral_code': 'Code2',
            'published_at': '2026-10-06T11:00:00Z',
            'timestamp_basis': 'exa_search_content_indexed'
        }
        self.assertIsNone(publication_time(index_row))

    def test_native_post_date_qualifies_as_publication_time(self):
        article_row = {
            'referral_code': 'Code3',
            'published_at': '2026-10-06T09:00:00Z',
            'timestamp_basis': 'devto_published_at'
        }
        pub_dt = publication_time(article_row)
        self.assertIsNotNone(pub_dt)
        self.assertEqual(pub_dt.year, 2026)
        self.assertEqual(pub_dt.day, 6)

    def test_yield_separates_fresh_native_from_historical_and_scan(self):
        records = [
            # 1. Fresh native article on same day
            {
                'referral_code': 'FreshToday',
                'discovered_at': '2026-10-06T10:00:00Z',
                'published_at': '2026-10-06T09:00:00Z',
                'evidence_kind': 'direct_match',
                'timestamp_basis': 'blog_published_time'
            },
            # 2. Historical code from previous month
            {
                'referral_code': 'OldCode',
                'discovered_at': '2026-10-06T10:00:00Z',
                'published_at': '2026-08-15T12:00:00Z',
                'evidence_kind': 'direct_match',
                'timestamp_basis': 'forum_post_created_at'
            },
            # 3. Code with scan date only
            {
                'referral_code': 'ScanCode',
                'discovered_at': '2026-10-06T10:00:00Z',
                'published_at': '2026-10-06T10:00:00Z',
                'evidence_kind': 'direct_match',
                'timestamp_basis': 'urlscan_submission_time'
            }
        ]

        summary = yield_summary(records, now=self.now, days=1)
        today = summary['today']
        self.assertEqual(today['first_observed_unique'], 3)
        self.assertEqual(today['recent_dated_candidates'], 1)  # Only FreshToday
        self.assertEqual(today['historical_dated'], 1)          # OldCode
        self.assertEqual(today['unknown_publication'], 1)       # ScanCode


if __name__ == '__main__':
    unittest.main()
