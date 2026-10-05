import json
import os
import tempfile
import unittest
from unittest.mock import patch
from quarry.models import ReferralRecord
from quarry.storage import QuarryStorage


def record(source, published='2026-10-01T12:00:00Z'):
    return ReferralRecord('ValidCode', 'https://claude.ai/referral/ValidCode', 'Test', source,
                          published_at=published, evidence_snippet='https://claude.ai/referral/ValidCode',
                          evidence_kind='direct_match')


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, 'store.db')
        self.store = QuarryStorage(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_preserves_all_sources_and_selects_earliest_evidence(self):
        self.assertTrue(self.store.save_link(record('https://example.org/new')))
        self.assertFalse(self.store.save_link(record('https://example.org/old', '2025-01-01T00:00:00Z')))
        self.assertEqual(self.store.count(), 1)
        self.assertEqual(len(self.store.get_occurrences('ValidCode')), 2)
        self.assertEqual(self.store.get_by_code('ValidCode')['source_url'], 'https://example.org/old')

    def test_reopen_preserves_records_and_no_windows_handle_leak(self):
        self.store.save_link(record('https://example.org/one'))
        reopened = QuarryStorage(self.path)
        self.assertEqual(reopened.count(), 1)
        os.replace(self.path, self.path + '.moved')

    def test_deployment_snapshot_never_pretends_to_persist(self):
        snapshot = os.path.join(self.temp.name, 'snapshot.json')
        with open(snapshot, 'w', encoding='utf-8') as out:
            json.dump({'records': [record('https://example.org/one').to_dict()]}, out)
        with patch.dict(os.environ, {'VERCEL': '1', 'QUARRY_SNAPSHOT_PATH': snapshot}):
            store = QuarryStorage()
            self.assertFalse(store.writable)
            self.assertFalse(store.persistent)
            self.assertFalse(store.save_link(record('https://example.org/two')))
            self.assertEqual(len(store.get_occurrences('ValidCode')), 1)

    def test_timestamps_compare_in_utc(self):
        self.store.save_link(record('https://example.org/first', '2026-10-01T11:00:00+02:00'))
        self.store.save_link(record('https://example.org/second', '2026-10-01T10:00:00Z'))
        self.assertEqual(self.store.get_by_code('ValidCode')['source_url'], 'https://example.org/first')


if __name__ == '__main__':
    unittest.main()
