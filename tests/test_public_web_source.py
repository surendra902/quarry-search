import unittest
from quarry.sources.public_web_source import PublicWebSource

URL = 'https://claude.ai/referral/FeedCode123'


class Fetch:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []
    def __call__(self, url, timeout):
        self.calls.append(url)
        return self.pages.get(url, {'status': 404, 'body': '', 'headers': {}})


def response(body, status=200, headers=None):
    return {'status': status, 'body': body, 'headers': headers or {}}


class PublicWebTests(unittest.TestCase):
    def source(self, seeds, pages):
        fetch = Fetch(pages)
        return PublicWebSource(seeds=seeds, fetch=fetch, resolver=lambda host:['93.184.216.34'], delay=0), fetch
    def test_href_evidence_is_retained_without_inventing_article_date(self):
        src, _ = self.source([{'url':'https://example.org/claude'}], {
            'https://example.org/robots.txt': response('User-agent: *\nAllow: /'),
            'https://example.org/claude': response('<meta property="article:published_time" content="2026-10-05T00:00:00Z"><main><a href="'+URL+'">Claim</a></main>')})
        rows = src.discover_new()
        self.assertEqual(len(rows), 1)
        self.assertIn(URL, rows[0].evidence_snippet)
        self.assertIsNone(rows[0].published_at)
    def test_robots_denial_prevents_page_fetch(self):
        src, fetch = self.source([{'url':'https://example.org/private/claude'}], {
            'https://example.org/robots.txt': response('User-agent: *\nDisallow: /private/')})
        self.assertEqual(src.discover_new(), [])
        self.assertNotIn('https://example.org/private/claude', fetch.calls)
        self.assertNotEqual(src.last_report['status'], 'ok')
    def test_private_addresses_and_excluded_x_are_not_fetched(self):
        for url in ('http://127.0.0.1/claude','http://169.254.169.254/','https://x.com/search?q=claude'):
            src, fetch = self.source([{'url':url}], {})
            self.assertEqual(src.discover_new(), [])
            self.assertEqual(fetch.calls, [])
    def test_feed_discovers_new_permalinks_and_keeps_source_dates(self):
        feed='<rss><channel><item><title>Claude pass</title><link>https://example.org/new-post</link><pubDate>Mon, 05 Oct 2026 01:00:00 GMT</pubDate><description>'+URL+'</description></item></channel></rss>'
        src, fetch = self.source([{'url':'https://example.org/feed','kind':'feed'}], {
            'https://example.org/robots.txt':response('User-agent: *\nAllow: /'),
            'https://example.org/feed':response(feed),
            'https://example.org/new-post':response('<article><p>'+URL+'</p></article>')})
        rows=src.discover_new()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0].source_url,'https://example.org/new-post')
        self.assertEqual(rows[0].published_at,'2026-10-05T01:00:00Z')
        self.assertIn('rss_item_published_at',rows[0].timestamp_basis)
        self.assertIn('https://example.org/new-post',fetch.calls)
    def test_cross_host_redirect_is_not_followed(self):
        src, fetch=self.source([{'url':'https://example.org/claude'}],{
            'https://example.org/robots.txt':response('User-agent: *\nAllow: /'),
            'https://example.org/claude':response('',302,{'Location':'http://127.0.0.1/private'})})
        self.assertEqual(src.discover_new(),[])
        self.assertNotIn('http://127.0.0.1/private',fetch.calls)
    def test_sitemap_lastmod_is_not_publication_time(self):
        xml='<urlset><url><loc>https://example.org/claude-post</loc><lastmod>2026-10-05</lastmod></url></urlset>'
        src,_=self.source([{'url':'https://example.org/sitemap.xml','kind':'sitemap'}],{
            'https://example.org/robots.txt':response('User-agent: *\nAllow: /'),
            'https://example.org/sitemap.xml':response(xml),
            'https://example.org/claude-post':response('<article>'+URL+'</article>')})
        rows=src.discover_new()
        self.assertEqual(len(rows),1)
        self.assertIsNone(rows[0].published_at)


if __name__=='__main__':
    unittest.main()
