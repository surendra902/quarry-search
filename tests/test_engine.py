import os
import tempfile
import unittest
from quarry.engine import QuarryEngine
from quarry.models import ReferralRecord
from quarry.storage import QuarryStorage


class Source:
    def __init__(self, name, published=None, fail=False):
        self.name, self.published, self.fail = name, published, fail
    def discover_new(self, limit=50):
        if self.fail:
            raise RuntimeError('upstream unavailable')
        if not self.published:
            return []
        return [ReferralRecord('ExactToken', 'https://claude.ai/referral/ExactToken', self.name,
                 'https://example.org/' + self.name, published_at=self.published,
                 evidence_snippet='https://claude.ai/referral/ExactToken', evidence_kind='direct_match')]
    def find_original_source(self, code):
        rows = self.discover_new()
        return rows[0] if rows else None


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = QuarryStorage(os.path.join(self.temp.name, 'store.db'))
    def tearDown(self):
        self.temp.cleanup()
    def test_lookup_checks_more_than_first_provider_and_retains_occurrences(self):
        engine = QuarryEngine(self.store, [Source('later', '2026-10-01T00:00:00Z'), Source('earlier', '2025-01-01T00:00:00Z')])
        result = engine.lookup('ExactToken')
        self.assertEqual(result['platform'], 'earlier')
        self.assertEqual(len(self.store.get_occurrences('ExactToken')), 2)
    def test_failure_is_not_healthy_empty_source(self):
        engine = QuarryEngine(self.store, [Source('offline', fail=True)])
        result = engine.discover()
        self.assertTrue(result['partial'])
        self.assertEqual(result['source_reports']['offline']['status'], 'error')
    def test_no_match_does_not_claim_no_public_post_exists(self):
        engine = QuarryEngine(self.store, [Source('empty')])
        result = engine.lookup_detailed('ExactToken')
        self.assertFalse(result['found'])
        self.assertIn('checked', result['message'])
        self.assertNotIn('No open post exists', result['message'])
    def test_invalid_input_rejected_before_source_call(self):
        engine = QuarryEngine(self.store, [Source('offline', fail=True)])
        with self.assertRaises(ValueError):
            engine.lookup('https://evilclaude.ai/referral/ExactToken')


if __name__ == '__main__':
    unittest.main()
