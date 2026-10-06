import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from quarry.storage import QuarryStorage
from quarry.harvester import ContinuousHarvester


class QuietHarvestTests(unittest.TestCase):
    def test_quiet_cycle_does_not_dispatch_or_poll_bot_and_exports_empty_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=QuarryStorage(str(Path(tmp)/'store.db'))
            target=Path(tmp)/'snapshot.json'
            with patch.dict('os.environ',{'TELEGRAM_BOT_TOKEN':'fixture-not-real','TELEGRAM_CHAT_ID':'fixture'}), \
                 patch('requests.post',side_effect=AssertionError('No outbound notification allowed')):
                worker=ContinuousHarvester(storage=store,export_snapshot=str(target),notifications_enabled=False)
                self.assertIsNone(worker.telegram_bot)
                with patch.object(worker.engine,'discover',return_value={'new_records':[], 'candidate_records':[]}):
                    self.assertEqual(worker.harvest_cycle(),0)
            self.assertTrue(target.exists())
            data=json.loads(target.read_text())
            self.assertIn('source_state',data)
            self.assertIn('daily_yield',data)


if __name__=='__main__':
    unittest.main()
