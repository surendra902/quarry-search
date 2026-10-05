"""Tech community forum and developer blog source adapter (DEV.to, Qiita, etc.)."""
import logging
from typing import List, Optional
import requests

from quarry.sources.base import BaseSource
from quarry.models import ReferralRecord, utc_now
from quarry.extractors import extract_referral_codes

logger = logging.getLogger("quarry.sources.tech_community")


class TechCommunitySource(BaseSource):
    name = "tech_community"
    max_requests = 4
    budget_seconds = 20

    def __init__(self):
        self._start()

    def _query_devto(self, query: str, limit: int = 15, target_code: Optional[str] = None) -> List[ReferralRecord]:
        timeout = self._reserve_request()
        if timeout is None:
            return []

        records = []
        try:
            url = f"https://dev.to/api/articles?q={query}&per_page={min(30, limit)}"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 QuarryHarvester"}, timeout=timeout)
            if resp.status_code == 200:
                self._success()
                for item in resp.json():
                    content = f"{item.get('title', '')}\n{item.get('description', '')}\n{item.get('body_markdown', '')}"
                    article_url = item.get("url", "")
                    author = item.get("user", {}).get("username", "DEV.to Author")
                    pub = item.get("published_at")

                    for clean_url, code in extract_referral_codes(content):
                        if target_code is not None and code != target_code:
                            continue
                        records.append(ReferralRecord(
                            referral_code=code,
                            url=clean_url,
                            platform="DEV.to (Tech Blog / Community)",
                            source_url=article_url,
                            author=author,
                            published_at=pub,
                            discovered_at=utc_now(),
                            evidence_snippet=self._evidence(content, code),
                            status="unknown",
                            evidence_kind="direct_match",
                            timestamp_basis="devto_published_at"
                        ))
        except Exception as exc:
            self._problem("error", f"DEV.to search error: {exc}")
        return records

    def _query_qiita(self, query: str, limit: int = 15, target_code: Optional[str] = None) -> List[ReferralRecord]:
        timeout = self._reserve_request()
        if timeout is None:
            return []

        records = []
        try:
            url = f"https://qiita.com/api/v2/items?query={query}&per_page={min(20, limit)}"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 QuarryHarvester"}, timeout=timeout)
            if resp.status_code == 200:
                self._success()
                for item in resp.json():
                    content = f"{item.get('title', '')}\n{item.get('body', '')}"
                    item_url = item.get("url", "")
                    author = item.get("user", {}).get("id", "Qiita Author")
                    pub = item.get("created_at")

                    for clean_url, code in extract_referral_codes(content):
                        if target_code is not None and code != target_code:
                            continue
                        records.append(ReferralRecord(
                            referral_code=code,
                            url=clean_url,
                            platform="Qiita (Web Forum / Blog)",
                            source_url=item_url,
                            author=author,
                            published_at=pub,
                            discovered_at=utc_now(),
                            evidence_snippet=self._evidence(content, code),
                            status="unknown",
                            evidence_kind="direct_match",
                            timestamp_basis="qiita_created_at"
                        ))
        except Exception as exc:
            self._problem("error", f"Qiita search error: {exc}")
        return records

    def discover_new(self, limit: int = 30) -> List[ReferralRecord]:
        self._start()
        limit = self._limit(limit)
        if not limit:
            return self._finish([], 0)

        all_records = []
        seen = set()

        for rec in self._query_devto("claude+guest+pass", limit=15):
            if rec.referral_code not in seen:
                seen.add(rec.referral_code)
                all_records.append(rec)

        for rec in self._query_qiita("claude+referral", limit=15):
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

        all_records = []
        for rec in self._query_devto(code, limit=limit, target_code=code):
            all_records.append(rec)
        for rec in self._query_qiita(code, limit=limit, target_code=code):
            all_records.append(rec)

        return self._finish(all_records, limit)
