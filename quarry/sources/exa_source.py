"""Exa.ai neural and deep web search source adapter."""
import os
import re
from typing import List, Optional
try:
    from exa_py import Exa
except ImportError:
    Exa = None

from quarry.sources.base import BaseSource
from quarry.models import ReferralRecord
from quarry.extractors import extract_referral_codes


class ExaSource(BaseSource):
    name = "exa"
    max_requests = 6
    budget_seconds = 30

    def __init__(self, api_key: Optional[str] = None, storage: Optional[object] = None):
        self._start()
        self.api_key = api_key or os.environ.get("EXA_API_KEY")
        self.storage = storage
        self._cycle_idx = 0

    def _client(self):
        if Exa is None:
            self._problem("unavailable", "exa_py package is not installed; Exa search unavailable.")
            return None
        key = self.api_key or os.environ.get("EXA_API_KEY")
        if not key:
            self._problem("unavailable", "EXA_API_KEY is not configured; Exa search unavailable.")
            return None
        try:
            return Exa(api_key=key)
        except Exception as exc:
            self._problem("error", f"Failed to initialize Exa client: {type(exc).__name__}")
            return None

    def _parse_results(self, search_results, target_code=None) -> List[ReferralRecord]:
        from quarry.search_discovery import SearchDiscoveryVerifier
        verifier = SearchDiscoveryVerifier(max_page_fetches=8, timeout=4)
        results = getattr(search_results, "results", []) or []
        items = []
        for res in results:
            url = getattr(res, "url", "")
            platform = "Web (Exa Neural)"
            if "medium.com" in url:
                platform = "Medium (Tech Article)"
            elif "dev.to" in url:
                platform = "DEV.to (Tech Community)"
            elif "qiita.com" in url:
                platform = "Qiita (Japanese Tech Forum)"
            elif "zenn.dev" in url:
                platform = "Zenn.dev (Tech Publication)"
            elif "github.com" in url:
                platform = "GitHub (Code / Issue)"
            elif "substack.com" in url:
                platform = "Substack (Newsletter)"
            elif "reddit.com" in url:
                platform = "Reddit"
            elif any(d in url for d in ("toolspine.com", "opentherank.com", "usingclaude.com", "thekodelab.com")):
                platform = "Tech Guide / Web Directory"

            items.append({
                "url": url,
                "title": getattr(res, "title", ""),
                "author": getattr(res, "author", None),
                "published_at": getattr(res, "published_date", None),
                "platform": platform,
                "snippet": "\n".join([getattr(res, "text", "") or ""] + (getattr(res, "highlights", []) or []))
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
        client = self._client()
        if not client:
            return self._finish([], limit)

        query_pools = [
            # Pool 0: Fresh direct referral links & top developer communities
            [
                "free week of claude pro guest pass claude.ai/referral",
                "site:nodeseek.com claude.ai/referral",
                "site:v2ex.com claude.ai/referral"
            ],
            # Pool 1: Technical blogs, publications, and forum links
            [
                "site:linux.do claude.ai/referral",
                "claude pro guest pass referral code 2026",
                "claude.ai/referral site:medium.com OR site:dev.to OR site:qiita.com OR site:zenn.dev"
            ],
            # Pool 2: Developer communities, web directories, and guides
            [
                "claude code cowork guest pass referral",
                "claude referral pass link site:toolspine.com OR site:laosji.net",
                "Claude 招待コード OR クロード 招待リンク site:qiita.com OR site:zenn.dev"
            ]
        ]

        if self.storage and hasattr(self.storage, "get_state"):
            self._cycle_idx = self.storage.get_state("exa_cycle_idx", 0)

        active_pool = query_pools[self._cycle_idx % len(query_pools)]
        self._cycle_idx = (self._cycle_idx + 1) % len(query_pools)
        if self.storage and hasattr(self.storage, "set_state"):
            self.storage.set_state("exa_cycle_idx", self._cycle_idx)

        all_records = []
        for q in active_pool:
            timeout = self._reserve_request()
            if timeout is None:
                break
            try:
                res = client.search_and_contents(
                    q,
                    type="neural",
                    num_results=min(15, limit),
                    text=True,
                    highlights=True
                )
                self._success()
                all_records.extend(self._parse_results(res))
            except Exception as exc:
                self._problem("error", f"Exa search error for '{q}': {type(exc).__name__}: {exc}")

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
        client = self._client()
        if not client:
            return self._finish([], limit)

        timeout = self._reserve_request()
        if timeout is None:
            return self._finish([], limit)

        records = []
        try:
            res = client.search_and_contents(
                f'"claude.ai/referral/{code}"',
                type="keyword",
                num_results=min(10, limit),
                text=True
            )
            self._success()
            records.extend(self._parse_results(res, target_code=code))
        except Exception as exc:
            self._problem("error", f"Exa keyword search error: {type(exc).__name__}: {exc}")

        if not records:
            timeout = self._reserve_request()
            if timeout is not None:
                try:
                    res = client.search_and_contents(
                        f"claude.ai/referral/{code}",
                        type="neural",
                        num_results=min(10, limit),
                        text=True
                    )
                    self._success()
                    records.extend(self._parse_results(res, target_code=code))
                except Exception as exc:
                    self._problem("error", f"Exa neural search error: {type(exc).__name__}: {exc}")

        return self._finish(records, limit)
