"""Optional search snippets: candidate evidence only, never primary attribution."""
from typing import List, Optional
from urllib.parse import parse_qs, urlsplit, urlencode
import requests
from bs4 import BeautifulSoup
try:
    from scrapling.fetchers import Fetcher
except ImportError:
    Fetcher = None
from quarry.sources.base import BaseSource
from quarry.models import ReferralRecord
from quarry.extractors import extract_referral_codes, is_excluded_source


class WebDorkSource(BaseSource):
    name = "web_dorks"
    max_requests = 1

    def __init__(self):
        self._start()

    @staticmethod
    def _target(href):
        if not isinstance(href, str):
            return None
        if href.startswith("//"):
            href = "https:" + href
        try:
            parts = urlsplit(href)
            if parts.hostname in ("duckduckgo.com", "html.duckduckgo.com") or href.startswith("/l/"):
                href = parse_qs(parts.query).get("uddg", [""])[0]
                parts = urlsplit(href)
            if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
                return None
            return None if is_excluded_source(href) else href
        except ValueError:
            return None

    def _search(self, code, limit):
        if Fetcher is None:
            self._problem("unavailable", "Optional dependency scrapling[fetchers] is unavailable; web search was not attempted.")
            return self._finish([], limit)
        timeout = self._reserve_request()
        if timeout is None:
            return self._finish([], limit)
        query = f'"claude.ai/referral/{code}"' if code else '"claude.ai/referral"'
        records = []
        try:
            page = Fetcher.get("https://html.duckduckgo.com/html/?" + urlencode({"q": query}),
                               timeout=timeout, retries=1, follow_redirects=False)
            # Scrapling uses .status rather than requests' .status_code.
            status = page.status
            if status != 200:
                kind = "rate_limited" if status == 429 else "blocked" if status in (202, 401, 403) else "error"
                self._problem(kind, f"DuckDuckGo HTTP {status}; search unavailable.")
                return self._finish([], limit)
            body = page.body
            if isinstance(body, bytes):
                body = body.decode("utf-8", errors="replace")
            if not isinstance(body, str):
                self._problem("error", "DuckDuckGo returned a non-text response.")
                return self._finish([], limit)
            lowered = body.lower()
            if any(marker in lowered for marker in ("challenge-form", "anomaly.js", "captcha", "unusual traffic", "bots use duckduckgo")):
                self._problem("blocked", "DuckDuckGo returned a bot challenge; no bypass attempted.")
                return self._finish([], limit)
            soup = BeautifulSoup(body, "html.parser")
            results = soup.select(".result__body")
            if not results and not (soup.select_one(".no-results") or "no results found" in soup.get_text(" ").lower()):
                self._problem("error", "DuckDuckGo returned no recognizable results/empty-results marker.")
                return self._finish([], limit)
            self._success()
            if soup.select_one('input[name="s"]') or soup.select_one(".nav-link"):
                self._problem("partial", "DuckDuckGo additional search pages were not scanned.")
            for result in results:
                anchor = result.select_one("a.result__a") or result.select_one("a.result__url")
                target = self._target(anchor.get("href")) if anchor else None
                if not target:
                    self._problem("partial", "Search result without a usable target URL was discarded.")
                    continue
                text = result.get_text(" ", strip=True) + "\n" + target
                for clean_url, token in extract_referral_codes(text):
                    if code is not None and token != code:
                        continue
                    records.append(ReferralRecord(
                        referral_code=token, url=clean_url, platform="Web Search", source_url=target,
                        author=None, published_at=None, evidence_snippet=self._evidence(text, token),
                        status="unknown", evidence_kind="candidate_only",
                        timestamp_basis="search_snippet_observed_now; target_content_not_verified"))
        except Exception as exc:
            # Optional transport libraries use their own exception hierarchy.
            self._problem("error", f"DuckDuckGo {type(exc).__name__}; search request/parsing failed.")
        return self._finish(records, limit)

    def discover_new(self, limit: int = 50) -> List[ReferralRecord]:
        self._start()
        limit = self._limit(limit)
        return self._search(None, limit) if limit else self._finish([], 0)

    def find_sources(self, referral_code: str, limit: int = 20) -> List[ReferralRecord]:
        self._start()
        limit = self._limit(limit)
        code = self._code(referral_code)
        return self._search(code, limit) if code and limit else self._finish([], limit)

    def find_original_source(self, referral_code: str) -> Optional[ReferralRecord]:
        records = self.find_sources(referral_code, limit=1)
        return records[0] if records else None
