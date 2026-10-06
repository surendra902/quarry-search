"""Tests for candidate-to-page search discovery pipeline."""
import unittest
from unittest.mock import Mock, patch
from quarry.models import ReferralRecord


class SearchDiscoveryTests(unittest.TestCase):
    def setUp(self):
        from quarry.search_discovery import SearchDiscoveryVerifier
        self.verifier = SearchDiscoveryVerifier(max_page_fetches=5, timeout=3)

    def test_recovers_code_present_only_in_page_anchor_destination(self):
        # Snippet only says "Claude Code review", omitting the referral link
        search_item = {
            'url': 'https://example.org/blog/review',
            'title': 'Claude Code Experience',
            'snippet': 'My review of Claude Code. You can get a free trial pass below.',
            'published_at': '2026-10-01T12:00:00Z',
            'author': 'TechReviewer'
        }
        page_html = '''
        <html>
            <body>
                <h1>Claude Review</h1>
                <p>Great tool.</p>
                <a href="https://claude.ai/referral/HrefCode123">Claim 7-day guest pass</a>
            </body>
        </html>
        '''
        mock_fetch = Mock(return_value={'status': 200, 'body': page_html})
        records = self.verifier.verify_candidates([search_item], fetcher=mock_fetch)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].referral_code, 'HrefCode123')
        self.assertEqual(records[0].evidence_kind, 'direct_match')
        self.assertEqual(records[0].source_url, 'https://example.org/blog/review')
        self.assertIn('Claim 7-day guest pass', records[0].evidence_snippet)

    def test_snippet_direct_match_does_not_require_network_fetch(self):
        search_item = {
            'url': 'https://example.org/quick-post',
            'title': 'Free pass',
            'snippet': 'Here is my link https://claude.ai/referral/DirectCode456 for free week.',
            'published_at': '2026-10-02T10:00:00Z'
        }
        mock_fetch = Mock()
        records = self.verifier.verify_candidates([search_item], fetcher=mock_fetch)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].referral_code, 'DirectCode456')
        mock_fetch.assert_not_called()

    def test_excluded_sources_and_landing_pages_are_rejected(self):
        items = [
            {'url': 'https://twitter.com/someone/status/123', 'snippet': 'https://claude.ai/referral/BadCode1'},
            {'url': 'https://x.com/someone/status/456', 'snippet': 'https://claude.ai/referral/BadCode2'},
            {'url': 'https://claude.ai/referral/SelfEcho', 'snippet': 'Sign up at claude.ai'}
        ]
        records = self.verifier.verify_candidates(items)
        self.assertEqual(len(records), 0)

    def test_unreachable_or_failed_page_does_not_create_false_referral(self):
        search_item = {
            'url': 'https://example.org/broken-page',
            'title': 'Broken link',
            'snippet': 'Discussion about AI tools without any referral code.'
        }
        mock_fetch = Mock(return_value={'status': 404, 'body': 'Not Found'})
        records = self.verifier.verify_candidates([search_item], fetcher=mock_fetch)
        self.assertEqual(len(records), 0)


if __name__ == '__main__':
    unittest.main()
