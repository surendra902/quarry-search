import json
import tempfile
import unittest
from pathlib import Path
from quarry.extractors import extract_referral_codes
from quarry.models import ReferralRecord
from quarry.storage import QuarryStorage


class EvidenceBoundaryTests(unittest.TestCase):
    def test_markdown_url_label_cannot_swallow_real_destination(self):
        text='Try [claude.ai/referral/0sqPw8E_lw](https://claude.ai/referral/0sqPw8E_lw) now.'
        self.assertEqual(extract_referral_codes(text),[('https://claude.ai/referral/0sqPw8E_lw','0sqPw8E_lw')])
    def test_malformed_literal_path_is_not_cut_at_an_open_parenthesis(self):
        self.assertEqual(extract_referral_codes('https://claude.ai/referral/Code123(garbage)'),[])
    def test_legacy_scan_is_not_restored_as_verified_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=QuarryStorage(str(Path(tmp)/'store.db'))
            item=ReferralRecord('ScanCode123','https://claude.ai/referral/ScanCode123',
                'Web (URLScan Intelligence)','https://urlscan.io/api/v1/result/fixture/',
                author='Public URLScan Submission',published_at='2026-10-05T00:00:00Z',
                timestamp_basis='urlscan_submission_time').to_dict()
            snap=Path(tmp)/'snapshot.json'
            snap.write_text(json.dumps({'records':[item],'source_state':{
                'measurement_started_at':'2026-10-05T01:00:00Z','public_web_cursor':4}}))
            store.seed_from_snapshot(snap)
            result=store.get_by_code('ScanCode123')
            self.assertEqual(result['evidence_kind'],'candidate_only')
            self.assertIsNone(result['published_at'])
            self.assertIsNone(result['author'])
            self.assertEqual(store.get_state('public_web_cursor'),4)
            self.assertEqual(store.get_state('measurement_started_at'),'2026-10-05T01:00:00Z')


if __name__=='__main__':
    unittest.main()
