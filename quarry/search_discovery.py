"""Candidate-to-page search verification pipeline.

Bridges search results whose snippets omit referral codes to verified records
by fetching candidate page HTML and extracting anchor destinations.
"""
import logging
from typing import List, Dict, Any, Optional, Callable
from urllib.parse import urlsplit
import requests
from bs4 import BeautifulSoup

from quarry.extractors import extract_referral_codes, is_excluded_source
from quarry.models import ReferralRecord, utc_now

logger = logging.getLogger("quarry.search_discovery")
DEFAULT_UA = "QuarrySearch/1.0 (+https://github.com/surendra902/quarry-search)"


def _default_http_fetch(url: str, timeout: int = 5) -> Optional[Dict[str, Any]]:
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": DEFAULT_UA},
            timeout=(3, timeout),
            allow_redirects=True
        )
        if resp.status_code == 200:
            return {"status": 200, "body": resp.text, "headers": dict(resp.headers)}
    except Exception as exc:
        logger.debug(f"Candidate page fetch failed for {url}: {exc}")
    return None


class SearchDiscoveryVerifier:
    def __init__(self, max_page_fetches: int = 8, timeout: int = 5):
        self.max_page_fetches = max_page_fetches
        self.timeout = timeout

    def _is_permitted_candidate(self, url: str) -> bool:
        if not url or not url.startswith(("http://", "https://")):
            return False
        if is_excluded_source(url):
            return False
        try:
            parts = urlsplit(url)
            host = (parts.hostname or "").lower()
            if not host:
                return False
            # Landing pages themselves or search engines echoing queries are not original sources
            if host in ("claude.ai", "www.claude.ai") or "referral" in parts.path and host == "claude.ai":
                return False
            return True
        except Exception:
            return False

    def verify_candidates(
        self,
        items: List[Dict[str, Any]],
        fetcher: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None
    ) -> List[ReferralRecord]:
        fetch = fetcher or (lambda u: _default_http_fetch(u, timeout=self.timeout))
        verified_records: List[ReferralRecord] = []
        seen_codes = set()
        page_fetches_used = 0

        for item in items:
            url = item.get("url", "").strip()
            if not self._is_permitted_candidate(url):
                continue

            title = item.get("title", "")
            snippet = item.get("snippet") or item.get("text") or ""
            author = item.get("author")
            pub_date = item.get("published_at") or item.get("published_date")
            platform = item.get("platform") or f"Web ({urlsplit(url).netloc})"

            combined = f"{title}\n{snippet}"
            codes_in_snippet = extract_referral_codes(combined)

            if codes_in_snippet:
                for canonical, code in codes_in_snippet:
                    if code in seen_codes:
                        continue
                    seen_codes.add(code)
                    verified_records.append(ReferralRecord(
                        referral_code=code,
                        url=canonical,
                        platform=platform,
                        source_url=url,
                        author=author,
                        published_at=pub_date,
                        discovered_at=utc_now(),
                        evidence_snippet=snippet or title,
                        status="unknown",
                        evidence_kind="direct_match",
                        timestamp_basis="search_snippet_content"
                    ))
                continue

            # Snippet did not contain code — inspect actual candidate page HTML
            if page_fetches_used >= self.max_page_fetches:
                continue

            res = fetch(url)
            page_fetches_used += 1
            if not res or res.get("status") != 200:
                continue

            html_body = res.get("body", "")
            if not html_body or "claude.ai/referral" not in html_body:
                continue

            soup = BeautifulSoup(html_body, "html.parser")
            
            # 1. Search in <a> anchor href destinations
            for anchor in soup.find_all("a", href=True):
                href = anchor.get("href", "")
                anchor_matches = extract_referral_codes(href)
                for canonical, code in anchor_matches:
                    if code in seen_codes:
                        continue
                    seen_codes.add(code)
                    anchor_text = anchor.get_text(strip=True) or "Link"
                    parent_text = anchor.parent.get_text(strip=True) if anchor.parent else anchor_text
                    verified_records.append(ReferralRecord(
                        referral_code=code,
                        url=canonical,
                        platform=platform,
                        source_url=url,
                        author=author,
                        published_at=pub_date,
                        discovered_at=utc_now(),
                        evidence_snippet=parent_text[:300] or f"Anchor destination: {canonical}",
                        status="unknown",
                        evidence_kind="direct_match",
                        timestamp_basis="candidate_page_anchor_destination"
                    ))

            # 2. Search in visible body text
            body_matches = extract_referral_codes(html_body)
            for canonical, code in body_matches:
                if code in seen_codes:
                    continue
                seen_codes.add(code)
                verified_records.append(ReferralRecord(
                    referral_code=code,
                    url=canonical,
                    platform=platform,
                    source_url=url,
                    author=author,
                    published_at=pub_date,
                    discovered_at=utc_now(),
                    evidence_snippet=f"Direct occurrence on verified page body: {canonical}",
                    status="unknown",
                    evidence_kind="direct_match",
                    timestamp_basis="candidate_page_body_content"
                ))

        return verified_records
