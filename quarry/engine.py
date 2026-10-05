import time
from typing import List, Optional, Dict
from quarry.models import ReferralRecord
from quarry.storage import QuarryStorage
from quarry.extractors import extract_code_from_url, is_valid_referral_format
from quarry.sources.base import BaseSource
from quarry.sources.github_source import GitHubSource
from quarry.sources.hackernews_source import HackerNewsSource
from quarry.sources.reddit_source import RedditSource
from quarry.sources.web_dork_source import WebDorkSource

class QuarryEngine:
    def __init__(self, storage: Optional[QuarryStorage] = None, sources: Optional[List[BaseSource]] = None):
        self.storage = storage or QuarryStorage()
        self.sources: List[BaseSource] = sources if sources is not None else [
            GitHubSource(),
            HackerNewsSource(),
            RedditSource(),
            WebDorkSource(),
        ]

    def discover(self, limit_per_source: int = 50) -> Dict[str, any]:
        """
        Runs discovery sweeps across all registered sources.
        Deduplicates against local SQLite database.
        Returns newly discovered records and summary statistics.
        """
        new_records: List[ReferralRecord] = []
        source_counts: Dict[str, int] = {}
        total_found = 0

        for source in self.sources:
            try:
                print(f"[QuarryEngine] Polling source: {source.name}...")
                found = source.discover_new(limit=limit_per_source)
                source_counts[source.name] = len(found)
                total_found += len(found)
                
                for record in found:
                    is_new = self.storage.save_link(record)
                    if is_new:
                        new_records.append(record)
            except Exception as e:
                print(f"[QuarryEngine] Error in source {source.name}: {e}")
                source_counts[source.name] = 0

        return {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_candidates_found": total_found,
            "new_unique_links_saved": len(new_records),
            "total_links_in_db": self.storage.count(),
            "source_breakdown": source_counts,
            "new_records": [r.to_dict() for r in new_records]
        }

    def lookup(self, code_or_url: str) -> Optional[Dict]:
        """
        Given any referral code or URL, finds its original source post, platform, author, and evidence.
        Checks local database first, then queries live sources if not cached.
        """
        code = extract_code_from_url(code_or_url)
        if not is_valid_referral_format(code):
            raise ValueError(f"Invalid Claude referral code format: '{code_or_url}'")

        # 1. Check local DB
        local_match = self.storage.get_by_code(code)
        if local_match:
            local_match["cached"] = True
            return local_match

        # 2. Query live sources
        print(f"[QuarryEngine] Searching live sources for referral code: {code}...")
        for source in self.sources:
            try:
                record = source.find_original_source(code)
                if record:
                    self.storage.save_link(record)
                    d = record.to_dict()
                    d["cached"] = False
                    return d
            except Exception as e:
                print(f"[QuarryEngine] Error searching {source.name} for {code}: {e}")

        return None
