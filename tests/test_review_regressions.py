import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from quarry.engine import QuarryEngine
from quarry.models import ReferralRecord
from quarry.storage import QuarryStorage
from quarry.sources.web_directory_source import WebDirectorySource
from quarry.sources.web_dork_source import WebDorkSource


class ReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = QuarryStorage(str(Path(self.temp.name) / 'store.db'))
        self.now = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
    def tearDown(self):
        self.temp.cleanup()
    def record(self, source, published=None, basis='article_published_at'):
        return ReferralRecord('Review1234', 'https://claude.ai/referral/Review1234', 'Fixture', source,
            published_at=published, discovered_at='2026-10-05T10:00:00Z',
            evidence_snippet='https://claude.ai/referral/Review1234', timestamp_basis=basis,
            evidence_kind='direct_match')
    def test_archived_old_code_and_today_repost_is_not_fresh(self):
        self.store.save_link(self.record('https://example.org/archive', '2025-01-01T00:00:00Z', 'directory_archived_submission_time_not_new_post'))
        self.store.save_link(self.record('https://example.org/repost', '2026-10-05T01:00:00Z'))
        today = self.store.yield_summary(now=self.now)['today']
        self.assertEqual(today['recent_dated_candidates'], 0)
        self.assertEqual(today['historical_dated'], 1)
    def test_undated_refresh_preserves_established_publication_evidence(self):
        self.store.save_link(self.record('https://example.org/post', '2026-10-05T01:00:00Z', 'rss_item_published_at; link_in_native_feed_and_retrieved_page'))
        self.store.save_link(self.record('https://example.org/post', None, 'web_page_observed_now; publication_time_unknown'))
        row = self.store.get_by_code('Review1234')
        self.assertEqual(row['published_at'], '2026-10-05T01:00:00Z')
        self.assertIn('rss_item_published_at', row['timestamp_basis'])
        self.assertEqual(self.store.yield_summary(now=self.now)['today']['recent_dated_candidates'], 1)
    def test_unrelated_next_state_does_not_hide_visible_links(self):
        body = '<script id="__NEXT_DATA__">'+json.dumps({'props':{'pageProps':{'title':'Directory'}}})+'</script><main><a href="https://claude.ai/referral/Review1234">Referral</a></main>'
        def fetch(url, timeout):
            return {'status':200, 'headers':{}, 'body':'User-agent: *\nAllow: /' if url.endswith('/robots.txt') else body}
        src = WebDirectorySource(seeds=[{'url':'https://example.org/list'}], fetch=fetch, resolver=lambda h:['93.184.216.34'], delay=0)
        self.assertEqual([r.referral_code for r in src.discover_new()], ['Review1234'])
    def test_engine_excludes_x_even_from_optional_source_candidates(self):
        x = self.record('https://x.com/user/status/123')
        good = self.record('https://example.org/post')
        class Source:
            name = 'fixture'
            def discover_new(self, limit=20):
                return [x, good]
        result = QuarryEngine(self.store, sources=[Source()]).discover()
        self.assertEqual([r['source_url'] for r in result['candidate_records']], ['https://example.org/post'])
    def test_search_targets_exclude_x_variants_but_not_lookalikes(self):
        for url in ('https://x.com/a', 'https://mobile.twitter.com/a', 'https://www.X.com./a'):
            with self.subTest(url=url):
                self.assertIsNone(WebDorkSource._target(url))
        self.assertEqual(WebDorkSource._target('https://notx.com/a'), 'https://notx.com/a')


if __name__ == '__main__':
    unittest.main()
