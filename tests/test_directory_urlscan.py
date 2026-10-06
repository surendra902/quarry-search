import json
import unittest
from unittest.mock import Mock, patch
from quarry.sources.urlscan_source import URLScanSource
from quarry.sources.web_directory_source import WebDirectorySource


class ProvenanceTests(unittest.TestCase):
    def test_urlscan_observation_is_not_a_published_source_post(self):
        response=Mock(status_code=200)
        response.json.return_value={'results':[{'page':{'url':'https://claude.ai/referral/ScanCode123'},
            'task':{'time':'2026-10-05T00:00:00Z'},'result':'https://urlscan.io/api/v1/result/scan-id/'}]}
        with patch('requests.get',return_value=response):
            rows=URLScanSource().discover_new()
        self.assertTrue(rows)
        self.assertEqual(rows[0].evidence_kind,'candidate_only')
        self.assertIsNone(rows[0].published_at)
        self.assertIsNone(rows[0].author)
    def test_directory_archive_is_labeled_and_never_given_invented_author(self):
        from quarry.sources.public_web_source import PublicWebSource
        payload={'props':{'pageProps':{'codes':[], 'archivedCodes':[{'referral_url':'https://claude.ai/referral/Archive123',
                'created_at':'2026-10-05T00:00:00Z','directory_status':'archived'}]}}}
        body='<script id="__NEXT_DATA__" type="application/json">'+json.dumps(payload)+'</script>'
        url='https://claudecoworkcourse.com/claude-guest-passes'
        def fetch(target,timeout):
            return {'status':200,'body':'User-agent: *\nAllow: /' if target.endswith('/robots.txt') else body,'headers':{}}
        source=WebDirectorySource(fetch=fetch,resolver=lambda h:['93.184.216.34'],delay=0,seeds=[{'url':url}])
        rows=source.discover_new()
        self.assertEqual(len(rows),1)
        self.assertIn('archived',rows[0].timestamp_basis)
        self.assertIsNone(rows[0].author)
        self.assertIn('https://claude.ai/referral/Archive123',rows[0].evidence_snippet)


if __name__=='__main__':
    unittest.main()
