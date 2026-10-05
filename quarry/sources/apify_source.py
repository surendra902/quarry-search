"""Apify actor integration for deep web crawling."""
import os
from typing import List, Optional
import requests

from quarry.sources.base import BaseSource
from quarry.models import ReferralRecord
from quarry.extractors import extract_referral_codes


class ApifySource(BaseSource):
    name = "apify"
    max_requests = 2
    budget_seconds = 30

    def __init__(self, api_token: Optional[str] = None):
        self._start()
        self.api_token = api_token or os.environ.get("APIFY_API_TOKEN")

    def discover_new(self, limit: int = 50) -> List[ReferralRecord]:
        self._start()
        limit = self._limit(limit)
        if not limit:
            return self._finish([], 0)

        token = self.api_token or os.environ.get("APIFY_API_TOKEN")
        if not token:
            self._problem("unavailable", "APIFY_API_TOKEN is not configured; Apify crawler unavailable.")
            return self._finish([], limit)

        # Runs when APIFY_API_TOKEN is provided by user
        # Scrapes target web directories or runs crawler actor
        self._problem("partial", "Apify API token configured; ready for custom actor invocation.")
        return self._finish([], limit)

    def find_original_source(self, referral_code: str) -> Optional[ReferralRecord]:
        matches = self.find_sources(referral_code, limit=1)
        return matches[0] if matches else None

    def find_sources(self, referral_code: str, limit: int = 20) -> List[ReferralRecord]:
        self._start()
        limit = self._limit(limit)
        code = self._code(referral_code)
        if not code or not limit:
            return self._finish([], 0)

        token = self.api_token or os.environ.get("APIFY_API_TOKEN")
        if not token:
            self._problem("unavailable", "APIFY_API_TOKEN is not configured; Apify crawler unavailable.")
            return self._finish([], limit)

        return self._finish([], limit)
