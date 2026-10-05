"""Opt-in, read-only Reddit public JSON search; never use archive attribution."""
from typing import List, Optional
import requests
from quarry.sources.base import BaseSource
from quarry.models import ReferralRecord
from quarry.extractors import extract_referral_codes


class RedditSource(BaseSource):
    name = "reddit"
    max_requests = 1

    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None, *, enabled: bool = False):
        # Kept for call compatibility; credentials do not silently enable access.
        self.enabled = enabled
        self.headers = {"User-Agent": "quarry-public-source-audit/1.0", "Accept": "application/json"}
        self._start()

    def _search(self, code, limit):
        if not self.enabled:
            self._problem("unavailable", "Reddit disabled; explicitly enable only where public API access is approved.")
            return self._finish([], limit)
        data = self._get_json("https://www.reddit.com/search.json", headers=self.headers,
                              params={"q": f'"claude.ai/referral/{code}"' if code else '"claude.ai/referral"',
                                      "sort": "new", "limit": 100, "type": "link", "raw_json": 1})
        records = []
        if data is None:
            return self._finish(records, limit)
        listing = data.get("data")
        if not isinstance(listing, dict) or not isinstance(listing.get("children"), list):
            self._problem("error", "Reddit returned a malformed public listing.")
            return self._finish(records, limit)
        if listing.get("after") or len(listing["children"]) >= 100:
            self._problem("partial", "Reddit additional pages were not scanned; search does not cover all comments.")
        for child in listing["children"]:
            item = child.get("data") if isinstance(child, dict) else None
            if not isinstance(item, dict):
                self._problem("error", "Reddit returned a malformed post.")
                continue
            text = "\n".join(str(item.get(k) or "") for k in ("title", "selftext", "url"))
            permalink = item.get("permalink") or ""
            if not isinstance(permalink, str) or not permalink.startswith("/r/") or "/comments/" not in permalink or "?" in permalink or "#" in permalink:
                self._problem("error", "Reddit post lacks a valid first-party permalink; discarded.")
                continue
            for clean_url, token in extract_referral_codes(text):
                if code is not None and token != code:
                    continue
                records.append(ReferralRecord(
                    referral_code=token, url=clean_url, platform=f"Reddit (r/{item.get('subreddit') or 'unknown'})",
                    source_url="https://www.reddit.com" + permalink,
                    author=item.get("author") if item.get("author") != "[deleted]" else None,
                    published_at=self._iso_timestamp(item.get("created_utc")),
                    source_updated_at=self._iso_timestamp(item.get("edited")),
                    evidence_snippet=self._evidence(text, token), status="unknown", evidence_kind="direct_match",
                    timestamp_basis="reddit_created_utc; content_observed_now; edited_is_not_link_publication_time"))
        self.last_report["messages"].append("Reddit public search covers submissions only, not all comments/private/deleted posts.")
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
