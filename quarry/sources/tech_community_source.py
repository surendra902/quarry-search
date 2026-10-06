"""Bounded, unauthenticated DEV article discovery and Qiita native search.

Contracts: https://developers.forem.com/api/v1 and https://qiita.com/api/v2/docs.
DEV's /articles list is not full-text search and does not contain article bodies.
"""
from datetime import datetime
import html
import logging
import re
from typing import List, Optional

import requests

from quarry.sources.base import BaseSource
from quarry.models import ReferralRecord, utc_now
from quarry.extractors import extract_referral_codes

logger = logging.getLogger("quarry.sources.tech_community")
_HEADERS = {"User-Agent": "QuarryHarvester/1.0", "Accept": "application/json"}
_FULL_URL = re.compile(r'''https?://[^\s<>"'`]+''', re.IGNORECASE)


class TechCommunitySource(BaseSource):
    name = "tech_community"
    max_requests = 4
    budget_seconds = 20

    def __init__(self):
        self._start()

    def _items(self, url, params):
        timeout = self._reserve_request()
        if timeout is None:
            return None
        try:
            response = requests.get(url, params=params, headers=_HEADERS,
                                    timeout=(min(3, timeout), timeout), allow_redirects=False)
            if self._http_failure(response, url):
                return None
            items = response.json()
            if not isinstance(items, list):
                self._problem("error", f"{url}: expected a JSON article list.")
                return None
            self._success()
            return items
        except (requests.RequestException, ValueError, TypeError) as exc:
            self._problem("error", f"{url}: {type(exc).__name__}; request or response failed.")
            return None

    @staticmethod
    def _date(value):
        if not isinstance(value, str):
            return None
        try:
            return value if datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo else None
        except ValueError:
            return None

    def _records(self, item, platform, body_fields, author_field, date_field, updated_field, target_code):
        if not isinstance(item, dict):
            self._problem("error", f"{platform}: malformed article.")
            return []
        bodies = [item[field] for field in body_fields if isinstance(item.get(field), str)]
        source_url = item.get("url")
        if not bodies or not isinstance(source_url, str) or not source_url:
            self._problem("error", f"{platform}: missing native body or article URL; article not scanned.")
            return []
        # Keep HTML hrefs and Markdown destinations, not merely rendered text.
        content = html.unescape("\n".join(bodies))
        author = item.get("user") or {}
        author = author.get(author_field) if isinstance(author, dict) else None
        author = author if isinstance(author, str) and author else None
        published = self._date(item.get(date_field))
        records = []
        seen = set()
        for match in _FULL_URL.finditer(content):
            raw_url = match.group().rstrip(".,;:!?)]}")
            for clean_url, code in extract_referral_codes(raw_url):
                if code in seen or (target_code is not None and code != target_code):
                    continue
                seen.add(code)
                records.append(ReferralRecord(
                    referral_code=code, url=clean_url, platform=platform,
                    source_url=source_url, author=author, published_at=published,
                    discovered_at=utc_now(), status="unknown", evidence_kind="direct_match",
                    evidence_snippet=content[max(0, match.start() - 100):match.end() + 100],
                    timestamp_basis=("devto_" if date_field == "published_at" else "qiita_") + date_field if published else None,
                    source_updated_at=self._date(item.get(updated_field)),
                ))
        return records

    def _query_devto(self, query: str = "claude", limit: int = 15,
                     target_code: Optional[str] = None) -> List[ReferralRecord]:
        # `query` is retained for compatibility, NOT sent as unsupported ?q=.
        self.last_report["messages"].append(
            "DEV coverage: one claude tag page (popularity ordered), latest-page fallback only if empty; "
            "bounded detail fetches by ID, not a full-text or exhaustive token search.")
        size = min(30, limit)
        items = self._items("https://dev.to/api/articles", {"tag": "claude", "page": 1, "per_page": size})
        if items == []:
            items = self._items("https://dev.to/api/articles/latest", {"page": 1, "per_page": size})
        if items is None:
            return []
        records = []
        seen_ids = set()
        scanned = 0
        for item in items[:size]:
            if not isinstance(item, dict) or type(item.get("id")) is not int or item["id"] <= 0:
                self._problem("error", "DEV: missing or malformed numerical article ID.")
                continue
            article_id = item["id"]
            if article_id in seen_ids:
                continue
            seen_ids.add(article_id)
            # Leave one request for Qiita so DEV details cannot starve it.
            if self.last_report["request_count"] >= self.max_requests - 1:
                self._problem("partial", "DEV detail request budget reached; remaining articles not scanned.")
                break
            detail = self._get_json(f"https://dev.to/api/articles/{article_id}", headers=_HEADERS)
            if detail is not None:
                scanned += 1
                records.extend(self._records(detail, "DEV.to (Tech Blog / Community)",
                                             ("body_markdown", "body_html"), "username",
                                             "published_at", "edited_at", target_code))
        self.last_report["messages"].append(f"DEV: {len(items)} candidates returned; {scanned} detail responses read.")
        return records

    def _query_qiita(self, query: str, limit: int = 15,
                     target_code: Optional[str] = None) -> List[ReferralRecord]:
        self.last_report["messages"].append("Qiita coverage: first native search page only; no comments or exhaustive history.")
        size = min(20, limit)
        items = self._items("https://qiita.com/api/v2/items", {"query": query, "page": 1, "per_page": size})
        if items is None:
            return []
        records = []
        for item in items[:size]:
            records.extend(self._records(item, "Qiita (Web Forum / Blog)", ("body", "rendered_body"),
                                         "id", "created_at", "updated_at", target_code))
        self.last_report["messages"].append(f"Qiita: {len(items)} native search results returned.")
        return records

    def _collect(self, limit, target_code=None):
        self.last_report["messages"].append(
            "Dates are native article publication/creation times, not referral insertion times or proof of origin.")
        records = self._query_devto(limit=limit, target_code=target_code)
        query = f'"https://claude.ai/referral/{target_code}"' if target_code else '"claude.ai/referral"'
        records.extend(self._query_qiita(query, limit=limit, target_code=target_code))
        result = self._finish(records, limit)
        logger.info("Tech community bounded coverage: %s", self.last_report)
        return result

    def discover_new(self, limit: int = 30) -> List[ReferralRecord]:
        self._start()
        limit = self._limit(limit)
        return self._collect(limit) if limit else self._finish([], 0)

    def find_original_source(self, referral_code: str) -> Optional[ReferralRecord]:
        matches = self.find_sources(referral_code, limit=1)
        return matches[0] if matches else None

    def find_sources(self, referral_code: str, limit: int = 20) -> List[ReferralRecord]:
        self._start()
        limit = self._limit(limit)
        code = self._code(referral_code)
        return self._collect(limit, code) if code and limit else self._finish([], 0)
