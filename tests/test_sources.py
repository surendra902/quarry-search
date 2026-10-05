"""Source public-interface contracts. HTTP fixtures are synthetic, never live."""
import unittest
from unittest.mock import Mock, patch

from quarry.sources.github_source import GitHubSource

CODE = "MiXeD_123abc"
LINK = "https://claude.ai/referral/MiXeD_123abc"


def response(payload=None, status=200, headers=None, text=""):
    res = Mock(status_code=status, headers=headers or {}, text=text)
    res.json.return_value = payload
    return res


def issue(number, body, **kwargs):
    return dict(html_url=f"https://github.com/acme/repo/issues/{number}",
                title="Unrelated title", body=body, user={"login": "fixture-user"},
                created_at="2025-01-01T00:00:00Z", updated_at="2025-02-01T00:00:00Z", **kwargs)


class GitHubProofTests(unittest.TestCase):
    def test_evidence_uses_full_link_not_an_earlier_bare_mention(self):
        with patch("quarry.sources.github_source.requests.get", side_effect=[
            response({"items": [issue(1, CODE + " padding" * 100 + " " + LINK)]}), response({"items": []})
        ]):
            record = GitHubSource().find_original_source(CODE)
        self.assertIn(LINK, record.evidence_snippet)

    def test_source_tokens_use_shared_parser_bounds_without_case_changes(self):
        for token in ("Ab", "Ab" * 30):
            link = "https://claude.ai/referral/" + token
            with self.subTest(token=token), patch("quarry.sources.github_source.requests.get", side_effect=[
                response({"items": [issue(1, link)]}), response({"items": []})
            ]):
                record = GitHubSource().find_original_source(token)
                self.assertIsNotNone(record)
                self.assertEqual(record.referral_code, token)

    def test_spoof_hosts_prefix_tokens_and_case_mismatch_are_not_sources(self):
        for body in ("https://evilclaude.ai/referral/" + CODE,
                     "https://claude.ai.attacker.test/referral/" + CODE,
                     LINK + "extra", LINK.lower(), LINK + "/suffix"):
            with self.subTest(body=body), patch("quarry.sources.github_source.requests.get", side_effect=[
                response({"items": [issue(1, body)]}), response({"items": []})
            ]):
                self.assertIsNone(GitHubSource().find_original_source(CODE))

    def test_commit_evidence_uses_committer_date_not_author_date(self):
        item = {"html_url": "https://github.com/acme/repo/commit/123", "commit": {
            "message": "actual message " + LINK, "author": {"name": "claimant", "date": "2000-01-01T00:00:00Z"},
            "committer": {"date": "2025-01-01T00:00:00Z"}}}
        with patch("quarry.sources.github_source.requests.get", side_effect=[response({"items": []}), response({"items": [item]})]):
            record = GitHubSource().find_original_source(CODE)
        self.assertEqual(record.published_at, "2025-01-01T00:00:00Z")
        self.assertIn("commit_committer_date", record.timestamp_basis)
        self.assertEqual(record.evidence_kind, "direct_match")
        self.assertIn(LINK, record.evidence_snippet)

    def test_lookup_rejects_bare_token_and_different_full_link(self):
        for body in (CODE, "https://claude.ai/referral/OtherCode99"):
            with self.subTest(body=body), patch("quarry.sources.github_source.requests.get", side_effect=[
                response({"items": [issue(1, body)]}), response({"items": []})
            ]):
                self.assertIsNone(GitHubSource().find_original_source(CODE))

    def test_lookup_inspects_second_hit_and_keeps_link_in_evidence(self):
        with patch("quarry.sources.github_source.requests.get", side_effect=[
            response({"items": [issue(1, CODE), issue(2, "prefix " * 100 + LINK)]}),
            response({"items": []})
        ]):
            record = GitHubSource().find_original_source(CODE)
        self.assertEqual(record.source_url, "https://github.com/acme/repo/issues/2")
        self.assertEqual(record.referral_code, CODE)
        self.assertIn(LINK, record.evidence_snippet)


from quarry.sources.hackernews_source import HackerNewsSource
from quarry.sources.reddit_source import RedditSource
from quarry.sources.web_dork_source import WebDorkSource
from quarry.sources import web_dork_source
import requests


class ReportingAndOccurrenceTests(unittest.TestCase):
    def test_github_occurrences_are_not_deduped_by_token(self):
        with patch("quarry.sources.github_source.requests.get", side_effect=[
            response({"items": [issue(1, LINK), issue(1, LINK), issue(2, LINK)]}),
            response({"items": []})
        ]):
            records = GitHubSource().find_sources(CODE)
        self.assertEqual([r.source_url for r in records], [
            "https://github.com/acme/repo/issues/1", "https://github.com/acme/repo/issues/2"])
        self.assertTrue(all(r.evidence_kind == "direct_match" for r in records))
        self.assertEqual(records[0].source_updated_at, "2025-02-01T00:00:00Z")
        self.assertIn("not_link_time", records[0].timestamp_basis)

    def test_errors_reported_and_report_reset_between_calls(self):
        source = GitHubSource()
        for status, expected in ((403, "blocked"), (429, "rate_limited"), (500, "error")):
            with self.subTest(status=status), patch("quarry.sources.github_source.requests.get", return_value=response({}, status)):
                self.assertEqual(source.find_sources(CODE), [])
                self.assertEqual(source.last_report["status"], expected)
                self.assertEqual(source.last_report["request_count"], 2)
                self.assertTrue(source.last_report["messages"])
        with patch("quarry.sources.github_source.requests.get", return_value=response({"items": []})):
            self.assertEqual(source.find_sources(CODE), [])
            self.assertEqual(source.last_report["status"], "ok")
            self.assertFalse(any("HTTP 500" in m for m in source.last_report["messages"]))

    def test_github_timeout_and_unscanned_pages_are_not_healthy_empty(self):
        source = GitHubSource()
        with patch("quarry.sources.github_source.requests.get", side_effect=requests.Timeout()):
            self.assertEqual(source.discover_new(), [])
        self.assertEqual(source.last_report["status"], "error")
        with patch("quarry.sources.github_source.requests.get", return_value=response({"items": [], "total_count": 50})):
            self.assertEqual(source.discover_new(), [])
        self.assertEqual(source.last_report["status"], "partial")
        self.assertTrue(any("pages not scanned" in m for m in source.last_report["messages"]))


class HackerNewsProofTests(unittest.TestCase):
    def test_bare_token_is_not_a_source(self):
        with patch("quarry.sources.hackernews_source.requests.get", return_value=response({
            "hits": [{"objectID": "10", "comment_text": CODE}], "nbPages": 1})):
            self.assertIsNone(HackerNewsSource().find_original_source(CODE))

    def test_story_text_html_and_multiple_occurrences_use_firebase_evidence(self):
        escaped = '&lt;a href="https:&#x2F;&#x2F;claude.ai&#x2F;referral&#x2F;MiXeD_123abc"&gt;claim&lt;/a&gt;'
        def http(url, **kwargs):
            if "algolia" in url:
                return response({"hits": [{"objectID": "10", "story_text": escaped},
                                          {"objectID": "10", "story_text": escaped},
                                          {"objectID": "11", "comment_text": LINK}], "nbPages": 1})
            number = 10 if "/10.json" in url else 11
            return response({"id": number, "text": escaped, "by": "official-user", "time": 0})
        with patch("quarry.sources.hackernews_source.requests.get", side_effect=http) as get:
            records = HackerNewsSource().find_sources(CODE)
        self.assertEqual([r.source_url for r in records], [
            "https://news.ycombinator.com/item?id=10", "https://news.ycombinator.com/item?id=11"])
        self.assertTrue(all(r.evidence_kind == "direct_match" for r in records))
        self.assertTrue(all(LINK in r.evidence_snippet for r in records))
        self.assertEqual(records[0].author, "official-user")
        self.assertEqual(records[0].published_at, "1970-01-01T00:00:00Z")
        self.assertEqual(get.call_count, 3)

    def test_stale_index_hit_cannot_become_direct_match(self):
        with patch("quarry.sources.hackernews_source.requests.get", side_effect=[
            response({"hits": [{"objectID": "10", "story_text": LINK}], "nbPages": 1}),
            response({"id": 10, "text": CODE})
        ]):
            self.assertIsNone(HackerNewsSource().find_original_source(CODE))


class RedditProofTests(unittest.TestCase):
    def test_disabled_reddit_never_uses_archive_or_network(self):
        source = RedditSource()
        with patch("quarry.sources.reddit_source.requests.get") as get:
            self.assertEqual(source.discover_new(), [])
            self.assertIsNone(source.find_original_source(CODE))
        get.assert_not_called()
        self.assertEqual(source.last_report["status"], "unavailable")

    def test_explicit_public_api_access_surfaces_403(self):
        source = RedditSource(enabled=True)
        with patch("quarry.sources.reddit_source.requests.get", return_value=response({}, 403)) as get:
            self.assertEqual(source.find_sources(CODE), [])
        self.assertEqual(source.last_report["status"], "blocked")
        self.assertTrue(all(c.args[0].startswith("https://www.reddit.com/") for c in get.call_args_list))

    def test_lookup_rejects_first_token_hit_and_preserves_second_source(self):
        posts = [{"data": {"title": "title", "selftext": text, "permalink": f"/r/ClaudeAI/comments/{i}/post/",
                            "subreddit": "ClaudeAI", "author": "real-api-user", "created_utc": 0}}
                 for i, text in ((1, CODE), (2, LINK), (3, LINK))]
        with patch("quarry.sources.reddit_source.requests.get", return_value=response({"data": {"children": posts, "after": None}})):
            records = RedditSource(enabled=True).find_sources(CODE)
        self.assertEqual([r.source_url for r in records], [
            "https://www.reddit.com/r/ClaudeAI/comments/2/post/", "https://www.reddit.com/r/ClaudeAI/comments/3/post/"])
        self.assertTrue(all(r.evidence_kind == "direct_match" for r in records))
        self.assertIn(LINK, records[0].evidence_snippet)


class SearchSnippetTests(unittest.TestCase):
    def setUp(self):
        guard = patch("quarry.sources.web_dork_source.requests.post", side_effect=AssertionError("Unexpected legacy network path"))
        guard.start()
        self.addCleanup(guard.stop)

    def test_real_optional_fetcher_performs_one_transport_attempt(self):
        try:
            from scrapling.fetchers import Fetcher as RealFetcher
        except ImportError:
            self.skipTest("Optional scrapling[fetchers] not installed")
        page = Mock(status=200, body=('<div class="result__body"><a class="result__a" href="https://example.org/post">Post</a><a class="result__snippet">' + LINK + '</a></div>').encode())
        with patch.object(web_dork_source, "Fetcher", RealFetcher), \
                patch("scrapling.engines.static.CurlSession") as transport, \
                patch("scrapling.engines.static.ResponseFactory.from_http_request", return_value=page):
            records = WebDorkSource().find_sources(CODE)
            self.assertEqual(len(records), 1)
            transport.return_value.request.assert_called_once()

    def test_full_link_snippets_are_candidates_without_invented_author(self):
        page = '<div class="result__body"><h2 class="result__title"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fpost">Post</a></h2><a class="result__snippet">' + LINK + '</a></div>'
        fetcher = Mock()
        fetcher.get.return_value = Mock(status=200, body=page.encode(), headers={})
        with patch.object(web_dork_source, "Fetcher", fetcher, create=True):
            records = WebDorkSource().find_sources(CODE)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source_url, "https://example.org/post")
        self.assertEqual(records[0].evidence_kind, "candidate_only")
        self.assertIsNone(records[0].author)
        self.assertIn(LINK, records[0].evidence_snippet)
        fetcher.get.assert_called_once()

    def test_search_captcha_is_blocked_not_empty_success(self):
        fetcher = Mock()
        fetcher.get.return_value = Mock(status=200, body=b'<form id="challenge-form">Select all squares containing a duck</form>', headers={})
        source = WebDorkSource()
        with patch.object(web_dork_source, "Fetcher", fetcher, create=True):
            self.assertEqual(source.find_sources(CODE), [])
        self.assertEqual(source.last_report["status"], "blocked")

    def test_missing_optional_fetcher_is_reported(self):
        source = WebDorkSource()
        with patch.object(web_dork_source, "Fetcher", None, create=True):
            self.assertEqual(source.find_sources(CODE), [])
        self.assertEqual(source.last_report["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
