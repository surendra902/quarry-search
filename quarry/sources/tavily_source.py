"""Tavily search API source adapter for wide web discovery."""
import os
from typing import List, Optional
import requests

from quarry.sources.base import BaseSource
from quarry.models import ReferralRecord
from quarry.extractors import extract_referral_codes


class TavilySource(BaseSource):
    name = "tavily"
    max_requests = 4
    budget_seconds = 20

    def __init__(self, api_key: Optional[str] = None):
        self._start()
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY")

    def _search_api(self, query: str, limit: int = 10, target_code: Optional[str] = None) -> List[ReferralRecord]:
        key = self.api_key or os.environ.get("TAVILY_API_KEY")
        if not key:
            self._problem("unavailable", "TAVILY_API_KEY is not configured; Tavily search unavailable.")
            return []

        timeout = self._reserve_request()
        if timeout is None:
            return []

        records = []
        try:
            payload = {
                "api_key": key,
                "query": query,
                "search_depth": "advanced",
                "max_results": min(15, limit)
            }
            resp = requests.post("https://api.tavily.com/search", json=payload, timeout=timeout)
            if resp.status_code == 401 or resp.status_code == 403:
                self._problem("auth", f"Tavily API authentication failed (HTTP {resp.status_code}).")
                return []
            if resp.status_code != 200:
                self._problem("error", f"Tavily returned HTTP {resp.status_code}.")
                return []

            self._success()
            data = resp.json()
            for item in data.get("results", []):
                url = item.get("url", "")
                title = item.get("title", "")
                content = item.get("content", "")
                combined = f"{title}\n{content}\n{url}"

                platform = "Web (Tavily AI)"
                if "medium.com" in url:
                    platform = "Medium"
                elif "dev.to" in url:
                    platform = "DEV.to"
                elif "reddit.com" in url:
                    platform = "Reddit"
                elif "github.com" in url:
                    platform = "GitHub"

                for clean_url, code in extract_referral_codes(combined):
                    if target_code is not None and code != target_code:
                        continue
                    records.append(ReferralRecord(
                        referral_code=code,
                        url=clean_url,
                        platform=platform,
                        source_url=url,
                        author=None,
                        published_at=None,
                        evidence_snippet=self._evidence(combined, code) if combined else f"Referral found via Tavily at {url}",
                        status="unknown",
                        evidence_kind="direct_match",
                        timestamp_basis="tavily_search_api; target_content_observed_now"
                    ))
        except Exception as exc:
            self._problem("error", f"Tavily search error for '{query}': {type(exc).__name__}: {exc}")

        return records

    def discover_new(self, limit: int = 50) -> List[ReferralRecord]:
        self._start()
        limit = self._limit(limit)
        if not limit:
            return self._finish([], 0)

        key = self.api_key or os.environ.get("TAVILY_API_KEY")
        if not key:
            self._problem("unavailable", "TAVILY_API_KEY is not configured; Tavily search unavailable.")
            return self._finish([], limit)

        queries = [
            "claude.ai/referral guest pass",
            "Here is my Claude referral link claude.ai/referral"
        ]
        all_records = []
        for q in queries:
            all_records.extend(self._search_api(q, limit=limit))

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

        key = self.api_key or os.environ.get("TAVILY_API_KEY")
        if not key:
            self._problem("unavailable", "TAVILY_API_KEY is not configured; Tavily search unavailable.")
            return self._finish([], limit)

        records = self._search_api(f'"claude.ai/referral/{code}"', limit=limit, target_code=code)
        return self._finish(records, limit)
