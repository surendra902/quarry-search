"""Algolia discovers candidates; official HN items carry the proof."""
from typing import List, Optional
import requests
from quarry.sources.base import BaseSource
from quarry.models import ReferralRecord
from quarry.extractors import extract_referral_codes


class HackerNewsSource(BaseSource):
    name = "hackernews"
    max_requests = 12

    def __init__(self):
        self.headers = {"User-Agent": "quarry-search-bot/1.0"}
        self._start()

    def _search(self, code, limit):
        endpoint = "search" if code else "search_by_date"
        data = self._get_json(f"https://hn.algolia.com/api/v1/{endpoint}", headers=self.headers,
                              params={"query": f'"claude.ai/referral/{code}"' if code else '"claude.ai/referral"',
                                      "tags": "(story,comment)", "hitsPerPage": 30, "page": 0})
        records = []
        if data is None:
            return self._finish(records, limit)
        hits = data.get("hits")
        if not isinstance(hits, list):
            self._problem("error", "HN index returned a malformed hits list.")
            return self._finish(records, limit)
        pages = data.get("nbPages")
        if len(hits) >= 30 or isinstance(pages, int) and pages > 1:
            self._problem("partial", "HN additional index pages were not scanned.")
        seen_items = set()
        for hit in hits:
            if not isinstance(hit, dict):
                self._problem("error", "HN malformed index hit.")
                continue
            candidate_text = "\n".join(str(hit.get(k) or "") for k in ("title", "comment_text", "story_text", "url"))
            found = extract_referral_codes(candidate_text)
            if not any(code is None or found_code == code for _, found_code in found):
                continue
            oid = str(hit.get("objectID") or "")
            if not oid.isascii() or not oid.isdigit():
                self._problem("error", "HN candidate has no valid item id.")
                continue
            if oid in seen_items:
                continue
            seen_items.add(oid)
            item = self._get_json(f"https://hacker-news.firebaseio.com/v0/item/{oid}.json", headers=self.headers)
            if item is None:
                continue
            if str(item.get("id")) != oid:
                self._problem("error", "HN official item id mismatched its candidate; discarded.")
                continue
            if item.get("deleted") or item.get("dead"):
                self._problem("partial", "HN indexed candidate is deleted/dead; discarded.")
                continue
            text = "\n".join(str(item.get(k) or "") for k in ("title", "text", "url"))
            verified = [(url, token) for url, token in extract_referral_codes(text) if code is None or token == code]
            if not verified:
                self._problem("partial", "HN indexed link absent from current official item; discarded.")
            for clean_url, token in verified:
                records.append(ReferralRecord(
                    referral_code=token, url=clean_url, platform="Hacker News",
                    source_url=f"https://news.ycombinator.com/item?id={oid}", author=item.get("by"),
                    published_at=self._iso_timestamp(item.get("time")),
                    evidence_snippet=self._evidence(text, token), status="unknown", evidence_kind="direct_match",
                    timestamp_basis="hn_item_created_time; content_observed_now; edit_time_unavailable"))
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
