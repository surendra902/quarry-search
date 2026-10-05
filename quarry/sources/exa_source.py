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

    def __init__(self, api_key: Optional[str] = None):
        self._start()
        self.api_key = api_key or os.environ.get("EXA_API_KEY")
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
        records = []
        results = getattr(search_results, "results", []) or []
        for res in results:
            url = getattr(res, "url", "")
            title = getattr(res, "title", "")
            author = getattr(res, "author", None)
            published_date = getattr(res, "published_date", None)
            text = getattr(res, "text", "") or ""
            highlights = getattr(res, "highlights", []) or []
            combined_text = "\n".join([title, text] + highlights)

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

            for clean_url, code in extract_referral_codes(combined_text + " " + url):
                if target_code is not None and code != target_code:
                    continue
                records.append(ReferralRecord(
                    referral_code=code,
                    url=clean_url,
                    platform=platform,
                    source_url=url,
                    author=author,
                    published_at=self._iso_timestamp(published_date) if isinstance(published_date, (int, float)) else (str(published_date) if published_date else None),
                    evidence_snippet=self._evidence(combined_text, code) if combined_text else f"Referral link {clean_url} discovered via Exa at {url}",
                    status="unknown",
                    evidence_kind="direct_match",
                    timestamp_basis="exa_search_content_indexed; direct_web_content_observed"
                ))
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
            # Pool 0: Direct referral links & guest passes across web
            [
                "claude.ai/referral guest pass",
                "Here is my Claude referral link https://claude.ai/referral/",
                "claude referral code guest pass free pro"
            ],
            # Pool 1: Technical blogs, newsletters, and publications
            [
                "claude.ai/referral site:medium.com OR site:dev.to OR site:qiita.com OR site:zenn.dev",
                "site:substack.com OR site:hashnode.dev claude referral link",
                "Claude Code passes https://claude.ai/referral/"
            ],
            # Pool 2: Developer communities, web directories, and forums
            [
                '"claude.ai/referral" site:reddit.com OR site:github.com',
                "claude referral pass link site:toolspine.com OR site:thekodelab.com OR site:opentherank.com",
                "Claude 招待コード OR クロード 招待リンク site:qiita.com OR site:zenn.dev"
            ]
        ]

        active_pool = query_pools[self._cycle_idx % len(query_pools)]
        self._cycle_idx += 1

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
