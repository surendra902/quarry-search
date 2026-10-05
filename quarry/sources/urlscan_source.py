"""URLScan.io public intelligence source for newly submitted referral links."""
import logging
from typing import List, Optional
import requests

from quarry.sources.base import BaseSource
from quarry.models import ReferralRecord, utc_now
from quarry.extractors import extract_referral_codes

logger = logging.getLogger("quarry.sources.urlscan")


class URLScanSource(BaseSource):
    name = "urlscan"
    max_requests = 3
    budget_seconds = 15

    def __init__(self, api_key: Optional[str] = None):
        self._start()
        self.api_key = api_key

    def _query(self, query: str, limit: int = 25, target_code: Optional[str] = None) -> List[ReferralRecord]:
        timeout = self._reserve_request()
        if timeout is None:
            return []

        records = []
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) QuarryHarvester/2026"}
            if self.api_key:
                headers["API-Key"] = self.api_key

            url = f"https://urlscan.io/api/v1/search/?q={query}&size={min(50, limit)}"
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code != 200:
                self._problem("error", f"urlscan.io returned HTTP {resp.status_code}")
                return []

            self._success()
            data = resp.json()
            for item in data.get("results", []):
                page = item.get("page", {})
                task = item.get("task", {})
                target_url = page.get("url") or task.get("url") or ""
                scan_url = item.get("result", "")
                time_str = task.get("time")

                for clean_url, code in extract_referral_codes(target_url):
                    if target_code is not None and code != target_code:
                        continue
                    records.append(ReferralRecord(
                        referral_code=code,
                        url=clean_url,
                        platform="Web (URLScan Intelligence)",
                        source_url=scan_url or target_url,
                        author="Public URLScan Submission",
                        published_at=time_str,
                        discovered_at=utc_now(),
                        evidence_snippet=f"Live referral link submitted to URLScan: {clean_url} (scan: {scan_url})",
                        status="unknown",
                        evidence_kind="direct_match",
                        timestamp_basis="urlscan_submission_time"
                    ))
        except Exception as exc:
            self._problem("error", f"URLScan search error: {exc}")
        return records

    def discover_new(self, limit: int = 50) -> List[ReferralRecord]:
        self._start()
        limit = self._limit(limit)
        if not limit:
            return self._finish([], 0)

        queries = [
            "page.domain:claude.ai+AND+page.url:referral",
            "page.url:\"claude.ai/referral\""
        ]

        all_records = []
        seen = set()
        for q in queries:
            if len(all_records) >= limit:
                break
            for rec in self._query(q, limit=limit):
                if rec.referral_code not in seen:
                    seen.add(rec.referral_code)
                    all_records.append(rec)

        return self._finish(all_records, limit)

    def find_original_source(self, referral_code: str) -> Optional[ReferralRecord]:
        matches = self.find_sources(referral_code, limit=1)
        return matches[0] if matches else None

    def find_sources(self, referral_code: str, limit: int = 20) -> List[ReferralRecord]:
        self._start()
        limit = self._limit(limit)
        code = self._code(referral_code)
        if not code or not limit:
            return self._finish([], 0)

        query = f"page.url:\"claude.ai/referral/{code}\""
        records = self._query(query, limit=limit, target_code=code)
        return self._finish(records, limit)
