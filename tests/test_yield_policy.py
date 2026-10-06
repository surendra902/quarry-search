import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from quarry.models import ReferralRecord
from quarry.storage import QuarryStorage
from quarry.engine import QuarryEngine


class YieldPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = QuarryStorage(str(Path(self.temp.name) / 'yield.db'))
        self.now = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
    def tearDown(self):
        self.temp.cleanup()
    def add(self, code, published, basis='article_published_at', source='post', kind='direct_match'):
        self.store.save_link(ReferralRecord(code, 'https://claude.ai/referral/'+code, 'Fixture',
            'https://example.org/'+source+code, published_at=published,
            discovered_at='2026-10-05T10:00:00Z', evidence_snippet='https://claude.ai/referral/'+code,
            evidence_kind=kind, timestamp_basis=basis))
    def test_historical_and_unknown_dates_do_not_meet_daily_target(self):
        self.add('Historical1', '2025-01-01T00:00:00Z')
        self.add('UnknownDate', None)
        self.add('RecentPost1', '2026-10-05T01:00:00Z')
        self.add('ScanOnly123', '2026-10-05T01:00:00Z', 'urlscan_submission_time', kind='candidate_only')
        result = self.store.yield_summary(now=self.now)
        self.assertEqual(result['today']['first_observed_unique'], 4)
        self.assertEqual(result['today']['recent_dated_candidates'], 1)
        self.assertEqual(result['today']['historical_dated'], 1)
        self.assertEqual(result['today']['unknown_publication'], 1)
        self.assertEqual(result['today']['unverified_candidates'], 1)
        self.assertFalse(result['target_verified'])
    def test_repost_of_old_code_is_not_newly_published(self):
        self.add('SameCode123', '2025-01-01T00:00:00Z', source='old')
        self.add('SameCode123', '2026-10-05T01:00:00Z', source='new')
        result = self.store.yield_summary(now=self.now)
        self.assertEqual(result['today']['first_observed_unique'], 1)
        self.assertEqual(result['today']['recent_dated_candidates'], 0)
    def test_snapshot_export_does_not_invent_running_collector(self):
        path = Path(self.temp.name) / 'snapshot.json'
        payload = self.store.export_snapshot(path)
        self.assertFalse(payload['collector']['configured'])
        self.assertNotEqual(payload['collector']['status'], 'Active (24/7 Cloud)')
        self.assertIsNone(payload['collector']['last_heartbeat'])
    def test_paid_keys_do_not_implicitly_enable_paid_sources(self):
        with patch.dict(os.environ, {'EXA_API_KEY':'fixture', 'TAVILY_API_KEY':'fixture',
                                    'APIFY_API_TOKEN':'fixture', 'SERPAPI_API_KEY':'fixture',
                                    'QUARRY_ENABLE_PAID_SOURCES':'0'}):
            names = [source.name for source in QuarryEngine(self.store).sources]
        self.assertFalse({'exa','tavily','apify','serpapi'} & set(names), names)
    def test_scan_date_cannot_be_treated_as_post_publication(self):
        self.add('ScanOnly123', '2026-10-05T01:00:00Z', 'urlscan_submission_time')
        result = self.store.yield_summary(now=self.now)
        self.assertEqual(result['today']['recent_dated_candidates'], 0)
        self.assertFalse(result['target_verified'])


if __name__ == '__main__':
    unittest.main()
