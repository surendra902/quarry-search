"""Worker recovery and state persistence tests across process restarts."""
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from quarry.models import ReferralRecord
from quarry.storage import QuarryStorage
from quarry.sources.exa_source import ExaSource
from quarry.harvester import ContinuousHarvester


class WorkerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "recovery.db")
        self.storage = QuarryStorage(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_query_pool_cursor_advances_across_restarts(self):
        # First process instance
        src1 = ExaSource(api_key="fixture-key", storage=self.storage)
        with patch.object(src1, "_client") as mock_client:
            mock_exa = Mock()
            mock_exa.search_and_contents.return_value = Mock(results=[])
            mock_client.return_value = mock_exa
            src1.discover_new(10)
        self.assertEqual(self.storage.get_state("exa_cycle_idx"), 1)

        # Second process instance (simulating restart)
        src2 = ExaSource(api_key="fixture-key", storage=self.storage)
        with patch.object(src2, "_client") as mock_client:
            mock_exa = Mock()
            mock_exa.search_and_contents.return_value = Mock(results=[])
            mock_client.return_value = mock_exa
            src2.discover_new(10)
        self.assertEqual(self.storage.get_state("exa_cycle_idx"), 2)

    def test_harvester_cycle_does_not_replay_deliveries(self):
        alerts_mock = Mock()
        alerts_mock.is_configured.return_value = True
        alerts_mock.dispatch.return_value = {'telegram': True}

        record = ReferralRecord(
            referral_code="RecoveryCode1",
            url="https://claude.ai/referral/RecoveryCode1",
            platform="Test",
            source_url="https://example.org/test",
            published_at="2026-10-06T10:00:00Z",
            discovered_at="2026-10-06T10:00:00Z",
            evidence_snippet="Found RecoveryCode1",
            status="unknown",
            evidence_kind="direct_match",
            timestamp_basis="direct_observed"
        )

        mock_engine = Mock()
        mock_engine.sources = []
        mock_engine.discover.return_value = {
            'new_records': [record.__dict__],
            'candidate_records': []
        }

        harvester = ContinuousHarvester(
            storage=self.storage,
            alerts=alerts_mock,
            interval_seconds=30
        )
        harvester.engine = mock_engine

        # Cycle 1
        new_count1 = harvester.harvest_cycle()
        self.assertEqual(new_count1, 1)
        self.assertEqual(alerts_mock.dispatch.call_count, 1)

        # Cycle 2 with same candidates (already in DB)
        mock_engine.discover.return_value = {
            'new_records': [],
            'candidate_records': [record.__dict__]
        }
        new_count2 = harvester.harvest_cycle()
        self.assertEqual(new_count2, 0)
        self.assertEqual(alerts_mock.dispatch.call_count, 1)  # Not called again


if __name__ == '__main__':
    unittest.main()
