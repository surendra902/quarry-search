"""SerpApi Google search supplementary index adapter in strict free-quota mode.

Enforces a 250 requests/month hard cap and 50 requests/hour limit.
Does not trust snippets for referral evidence; routes candidates through
SearchDiscoveryVerifier for direct HTML verification.
"""
import os
import re
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from urllib.parse import urlsplit
import requests

from quarry.sources.base import BaseSource
from quarry.models import ReferralRecord
from quarry.extractors import extract_referral_codes
from quarry.search_discovery import SearchDiscoveryVerifier

MAX_MONTHLY_SEARCHES = 250
MAX_HOURLY_SEARCHES = 50
DEFAULT_TIMEOUT = 5


class SerpSource(BaseSource):
    name = "serpapi"
    max_requests = 4
    budget_seconds = 20

    def __init__(self, api_key: Optional[str] = None, storage: Optional[object] = None):
        self._start()
        self.api_key = api_key or os.environ.get("SERPAPI_API_KEY")
        self.storage = storage
        self._cycle_idx = 0

    def _client_available(self) -> bool:
        key = self.api_key or os.environ.get("SERPAPI_API_KEY")
        if not key:
            self._problem("unavailable", "SERPAPI_API_KEY is not configured; SerpApi search unavailable.")
            return False
        return True

    def _get_current_month_key(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def _get_current_hour_key(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")

    def _check_and_increment_quota(self) -> bool:
        if not self.storage or not hasattr(self.storage, "get_state"):
            return True

        current_month = self._get_current_month_key()
        stored_month = self.storage.get_state("serpapi_month_key", current_month)
        monthly_usage = self.storage.get_state("serpapi_monthly_usage", 0)

        if stored_month != current_month:
            stored_month = current_month
            monthly_usage = 0
            self.storage.set_state("serpapi_month_key", current_month)
            self.storage.set_state("serpapi_monthly_usage", 0)

        if monthly_usage >= MAX_MONTHLY_SEARCHES:
            self._problem("unavailable", f"SerpApi monthly free quota hard cap ({MAX_MONTHLY_SEARCHES}) reached; search paused.")
            return False

        current_hour = self._get_current_hour_key()
        stored_hour = self.storage.get_state("serpapi_hour_key", current_hour)
        hourly_usage = self.storage.get_state("serpapi_hourly_usage", 0)

        if stored_hour != current_hour:
            stored_hour = current_hour
            hourly_usage = 0
            self.storage.set_state("serpapi_hour_key", current_hour)
            self.storage.set_state("serpapi_hourly_usage", 0)

        if hourly_usage >= MAX_HOURLY_SEARCHES:
            self._problem("rate_limited", f"SerpApi hourly free quota limit ({MAX_HOURLY_SEARCHES}) reached; search paused.")
            return False

        self.storage.set_state("serpapi_monthly_usage", monthly_usage + 1)
        self.storage.set_state("serpapi_hourly_usage", hourly_usage + 1)
        return True

    def _parse_results(self, json_data: Dict[str, Any], target_code: Optional[str] = None) -> List[ReferralRecord]:
        verifier = SearchDiscoveryVerifier(max_page_fetches=8, timeout=4)
        organic_results = json_data.get("organic_results", [])
        if not isinstance(organic_results, list):
            return []

        items = []
        for res in organic_results:
            if not isinstance(res, dict):
                continue
            url = res.get("link", "")
            if not url:
                continue
            title = res.get("title", "")
            snippet = res.get("snippet", "")
            date_str = res.get("date")

            host = urlsplit(url).netloc
            platform = f"Web (Google / {host})" if host else "Web (Google Search)"

            items.append({
                "url": url,
                "title": title,
                "snippet": snippet,
                "published_at": date_str,
                "platform": platform
            })

        records = verifier.verify_candidates(items)
        if target_code is not None:
            records = [r for r in records if r.referral_code == target_code]
        return records

    def discover_new(self, limit: int = 50) -> List[ReferralRecord]:
        self._start()
        limit = self._limit(limit)
        if not limit:
            return self._finish([], 0)

        if not self._client_available():
            return self._finish([], limit)

        query_pools = [
            # Pool 0: Primary referral link discovery
            [
                '"claude.ai/referral" guest pass',
                '"claude.ai/referral" free pro'
            ],
            # Pool 1: Developer communities & tech guides
            [
                'site:dev.to OR site:medium.com "claude.ai/referral"',
                'site:substack.com OR site:hashnode.dev "claude.ai/referral"'
            ],
            # Pool 2: Discussion forums & sharing threads
            [
                '"claude.ai/referral" forum OR discussion',
                '"claude.ai/referral" invitation code'
            ]
        ]

        if self.storage and hasattr(self.storage, "get_state"):
            self._cycle_idx = self.storage.get_state("serpapi_cycle_idx", 0)

        active_pool = query_pools[self._cycle_idx % len(query_pools)]
        self._cycle_idx = (self._cycle_idx + 1) % len(query_pools)
        if self.storage and hasattr(self.storage, "set_state"):
            self.storage.set_state("serpapi_cycle_idx", self._cycle_idx)

        key = self.api_key or os.environ.get("SERPAPI_API_KEY")
        all_records = []

        for q in active_pool:
            if not self._check_and_increment_quota():
                break

            timeout = self._reserve_request()
            if timeout is None:
                break

            try:
                resp = requests.get(
                    "https://serpapi.com/search.json",
                    params={
                        "engine": "google",
                        "q": q,
                        "api_key": key,
                        "num": min(10, limit)
                    },
                    timeout=(3, timeout)
                )
                if self._http_failure(resp, f"SerpApi '{q}'"):
                    continue

                data = resp.json()
                if "error" in data:
                    self._problem("error", f"SerpApi API error: {data['error']}")
                    continue

                self._success()
                all_records.extend(self._parse_results(data))
            except Exception as exc:
                self._problem("error", f"SerpApi search error for '{q}': {type(exc).__name__}: {exc}")

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

        if not self._client_available():
            return self._finish([], limit)

        if not self._check_and_increment_quota():
            return self._finish([], limit)

        timeout = self._reserve_request()
        if timeout is None:
            return self._finish([], limit)

        key = self.api_key or os.environ.get("SERPAPI_API_KEY")
        records = []
        try:
            resp = requests.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google",
                    "q": f'"claude.ai/referral/{code}"',
                    "api_key": key,
                    "num": min(10, limit)
                },
                timeout=(3, timeout)
            )
            if not self._http_failure(resp, f"SerpApi '{code}'"):
                data = resp.json()
                if "error" in data:
                    self._problem("error", f"SerpApi API error: {data['error']}")
                else:
                    self._success()
                    records = self._parse_results(data, target_code=code)
        except Exception as exc:
            self._problem("error", f"SerpApi lookup failed for '{code}': {type(exc).__name__}: {exc}")

        return self._finish(records, limit)
