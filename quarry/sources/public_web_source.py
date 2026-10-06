"""Bounded public pages + RSS/Atom/sitemaps, with robots and same-host controls."""
import ipaddress
import json
import re
import socket
import time
from collections import deque
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urldefrag
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from quarry.sources.base import BaseSource
from quarry.extractors import extract_referral_codes, is_excluded_source
from quarry.models import ReferralRecord

AGENT = 'QuarrySearch/1.0'
MAX_BODY = 2_000_000
KEYWORDS = re.compile(r'claude|anthropic|guest.?pass|referral', re.I)


def _resolve(host):
    return list({row[4][0] for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})


def _transport(url, timeout):
    try:
        from scrapling.fetchers import Fetcher
    except ImportError:
        with requests.get(url, headers={'User-Agent': AGENT}, timeout=(3, timeout),
                          allow_redirects=False, stream=True) as response:
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_BODY:
                    raise ValueError('Response exceeds the page-size limit.')
                chunks.append(chunk)
            return {'status': response.status_code, 'headers': dict(response.headers),
                    'body': b''.join(chunks).decode(response.encoding or 'utf-8', errors='replace')}
    page = Fetcher.get(url, timeout=timeout, retries=1, follow_redirects=False,
                       headers={'User-Agent': AGENT})
    body = page.body
    if len(body) > MAX_BODY:
        raise ValueError('Response exceeds the page-size limit.')
    return {'status': page.status, 'headers': dict(page.headers),
            'body': body.decode('utf-8', errors='replace') if isinstance(body, bytes) else str(body)}


class PublicWebSource(BaseSource):
    name = 'public_web'
    max_requests = 14
    budget_seconds = 30

    def __init__(self, seeds=None, cursor=0, fetch=None, resolver=None, delay=0.5):
        if seeds is None:
            path = Path(__file__).resolve().parents[2] / 'data' / 'web_sources.json'
            seeds = json.loads(path.read_text(encoding='utf-8')).get('sources', []) if path.exists() else []
        self.seeds = [row for row in seeds if row.get('enabled', True)]
        self.cursor = int(cursor or 0)
        self.fetch = fetch or _transport
        self.resolver = resolver or _resolve
        self.delay = delay
        self._start()

    def _safe(self, url, allowed):
        try:
            parts = urlsplit(url)
            host = parts.hostname
            if (parts.scheme not in ('https', 'http') or not host or parts.username or parts.password
                    or parts.port not in (None, 80, 443) or host not in allowed
                    or any(ord(c) < 32 for c in url) or '\\' in url):
                return False
            if is_excluded_source(url):
                return False
            try:
                if not ipaddress.ip_address(host).is_global:
                    return False
            except ValueError:
                pass
            addresses = self.resolver(host)
            return bool(addresses) and all(ipaddress.ip_address(addr).is_global for addr in addresses)
        except (ValueError, OSError, TypeError):
            return False

    def _request(self, url, allowed, check_robots=False):
        for _ in range(3):
            if not self._safe(url, allowed):
                self._problem('blocked', 'Non-public, excluded or off-host URL was not fetched.')
                return None
            if check_robots and not self._allowed_by_robots(url, allowed):
                return None
            host = urlsplit(url).netloc
            wait = self._next_fetch.get(host, 0) - time.monotonic()
            if wait > 0:
                if time.monotonic() + wait >= self._deadline:
                    self._problem('partial', 'Crawl delay exceeds remaining request budget.')
                    return None
                time.sleep(wait)
            timeout = self._reserve_request()
            if timeout is None:
                return None
            self._next_fetch[host] = time.monotonic() + self._delays.get(host, self.delay)
            try:
                result = self.fetch(url, timeout)
            except Exception as exc:
                self._problem('error', f'{host}: {type(exc).__name__}; page unavailable.')
                return None
            if len(result.get('body', '')) > MAX_BODY:
                self._problem('partial', f'{host}: page exceeds size cap.')
                return None
            if result['status'] in (301, 302, 303, 307, 308):
                headers = {k.lower(): v for k, v in result.get('headers', {}).items()}
                url = urljoin(url, headers.get('location', ''))
                continue
            return {**result, 'url': url}
        self._problem('partial', 'Redirect limit reached.')
        return None

    def _allowed_by_robots(self, url, allowed):
        parts = urlsplit(url)
        origin = parts.scheme + '://' + parts.netloc
        if origin not in self._robots:
            result = self._request(origin + '/robots.txt', allowed)
            if result is None:
                self._robots[origin] = None
            elif result['status'] == 404:
                robot = RobotFileParser()
                robot.parse(['User-agent: *', 'Allow: /'])
                self._robots[origin] = robot
            elif result['status'] == 200 and '<html' not in result['body'].lower():
                robot = RobotFileParser()
                robot.parse(result['body'].splitlines())
                self._robots[origin] = robot
                self._delays[parts.netloc] = max(self.delay, robot.crawl_delay(AGENT) or 0)
                self._next_fetch[parts.netloc] = max(self._next_fetch.get(parts.netloc, 0), time.monotonic() + self._delays[parts.netloc])
            else:
                self._problem('blocked', f'{origin}: robots.txt unavailable (HTTP {result["status"]}); skipped.')
                self._robots[origin] = None
        robot = self._robots[origin]
        if robot is None or not robot.can_fetch(AGENT, url):
            self._problem('blocked', f'{origin}: robots policy denied or unavailable.')
            return False
        return True

    @staticmethod
    def _children(body, base):
        root = ET.fromstring(body)
        local = lambda tag: tag.rsplit('}', 1)[-1]
        kind = local(root.tag)
        if kind in ('urlset', 'sitemapindex'):
            for entry in list(root):
                loc = next((node.text for node in entry if local(node.tag) == 'loc'), None)
                if loc and (kind == 'sitemapindex' or KEYWORDS.search(loc)):
                    yield {'url': urljoin(base, loc), 'kind': 'sitemap' if kind == 'sitemapindex' else 'page'}
            return
        for entry in root.iter():
            if local(entry.tag) not in ('item', 'entry'):
                continue
            values, link = {}, None
            for node in entry:
                key = local(node.tag)
                values[key] = ''.join(node.itertext())
                if key == 'link' and node.attrib.get('rel', 'alternate') == 'alternate':
                    link = node.attrib.get('href') or node.text
            content = '\n'.join(values.values())
            if not link or not KEYWORDS.search(content):
                continue
            date = values.get('published') or values.get('pubDate')
            if date and values.get('pubDate'):
                try:
                    parsed = parsedate_to_datetime(date)
                    date = parsed.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z') if parsed.tzinfo else None
                except (ValueError, TypeError):
                    date = None
            yield {'url': urljoin(base, link), 'kind': 'page', 'feed_content': content,
                   'published_at': date, 'author': values.get('creator')}

    def _page_records(self, body, task, actual_url, target):
        soup = BeautifulSoup(body, 'html.parser')
        if any(marker in body.lower() for marker in ('cf-chl-', 'challenge-form', 'verify you are human', '<title>just a moment')):
            self._problem('blocked', f'{urlsplit(actual_url).hostname}: challenge page, not source content.')
            return []
        for node in soup.select('script, style, noscript, header, footer, nav'):
            node.decompose()
        fragment = urlsplit(task['url']).fragment
        scope = soup.find(id=fragment) if fragment else None
        scope = scope or soup.find('main') or soup.find('article') or soup
        candidates = {}
        for anchor in scope.find_all('a', href=True):
            for canonical, code in extract_referral_codes(str(anchor)):
                candidates.setdefault(code, (canonical, str(anchor)))
        text = scope.get_text(' ', strip=True)
        for canonical, code in extract_referral_codes(text):
            candidates.setdefault(code, (canonical, self._evidence(text, code)))
        rows = []
        for code, (canonical, snippet) in candidates.items():
            if target and code != target:
                continue
            feed_matches = {token for _, token in extract_referral_codes(task.get('feed_content', ''))}
            dated = code in feed_matches and bool(task.get('published_at'))
            rows.append(ReferralRecord(code, canonical, 'Web (' + urlsplit(actual_url).hostname + ')',
                actual_url, author=task.get('author') if dated else None,
                published_at=task.get('published_at') if dated else None,
                evidence_snippet=snippet, evidence_kind='direct_match',
                timestamp_basis='rss_item_published_at; link_in_native_feed_and_retrieved_page' if dated else 'web_page_observed_now; publication_time_unknown'))
        return rows

    def _crawl(self, limit, target=None):
        self._start()
        self._robots, self._delays, self._next_fetch = {}, {}, {}
        self.last_report.update(seed_count=len(self.seeds), pages_fetched=0, seeds_checked=0)
        if not self.seeds or not limit:
            return self._finish([], limit)
        start = self.cursor % len(self.seeds)
        selected = (self.seeds[start:] + self.seeds[:start])[:4]
        queue = deque()
        for seed in selected:
            host = urlsplit(seed['url']).hostname or ''
            allowed = {host, host.removeprefix('www.'), 'www.' + host.removeprefix('www.')}
            queue.append(({**seed, 'depth': 0, 'seed': True}, allowed))
        records, visited = [], set()
        while queue and self.last_report['request_count'] < self.max_requests and time.monotonic() < self._deadline:
            task, allowed = queue.popleft()
            url = task['url']
            if url in visited:
                continue
            visited.add(url)
            if task.get('seed'):
                self.last_report['seeds_checked'] += 1
            if not self._safe(url, allowed):
                self._problem('blocked', 'Non-public, excluded or off-host seed/link skipped.')
                continue
            if not self._allowed_by_robots(url, allowed):
                continue
            result = self._request(url, allowed, check_robots=True)
            if result is None:
                continue
            if result['status'] != 200:
                self._problem('rate_limited' if result['status'] == 429 else 'blocked' if result['status'] in (401, 403) else 'error', f'{urlsplit(url).hostname}: HTTP {result["status"]}.')
                continue
            self._success()
            self.last_report['pages_fetched'] += 1
            if task.get('kind', 'page') in ('feed', 'sitemap'):
                try:
                    children = list(self._children(result['body'], result['url']))
                    if len(children) > 3:
                        self._problem('partial', 'Feed/sitemap child limit reached; remaining entries not scanned.')
                    if task['depth'] < 2:
                        for child in children[:3]:
                            queue.append(({**child, 'depth': task['depth'] + 1}, allowed))
                except ET.ParseError:
                    self._problem('error', 'Feed/sitemap is not valid XML.')
            else:
                records.extend(self._page_records(result['body'], task, result['url'], target))
        if queue:
            self._problem('partial', 'Request/time budget reached before all queued pages were fetched.')
        self.last_report['next_cursor'] = (start + self.last_report['seeds_checked']) % len(self.seeds)
        self.cursor = self.last_report['next_cursor']
        return self._finish(records, limit)

    def discover_new(self, limit=50):
        return self._crawl(self._limit(limit))

    def find_sources(self, referral_code, limit=20):
        self._start()
        code = self._code(referral_code)
        return self._crawl(self._limit(limit), code) if code else self._finish([], 0)

    def find_original_source(self, referral_code):
        rows = self.find_sources(referral_code, limit=1)
        return rows[0] if rows else None
