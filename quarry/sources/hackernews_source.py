import requests
from typing import List, Optional
from quarry.sources.base import BaseSource
from quarry.models import ReferralRecord
from quarry.extractors import extract_referral_codes

class HackerNewsSource(BaseSource):
    name = "hackernews"

    def __init__(self):
        self.headers = {"User-Agent": "quarry-search-bot/1.0"}

    def discover_new(self, limit: int = 50) -> List[ReferralRecord]:
        records: List[ReferralRecord] = []
        queries = [
            "https://hn.algolia.com/api/v1/search_by_date?query=%22claude.ai/referral%22&tags=(story,comment)&hitsPerPage=30",
            "https://hn.algolia.com/api/v1/search?query=%22claude.ai/referral%22&tags=(story,comment)&hitsPerPage=30",
            "https://hn.algolia.com/api/v1/search?query=claude%20referral&tags=(story,comment)&hitsPerPage=30",
        ]
        seen_codes = set()
        for url in queries:
            try:
                resp = requests.get(url, headers=self.headers, timeout=10)
                if resp.status_code == 200:
                    hits = resp.json().get("hits", [])
                    for hit in hits:
                        text = f"{hit.get('title') or ''}\n{hit.get('comment_text') or ''}\n{hit.get('story_text') or ''}\n{hit.get('url') or ''}"
                        found = extract_referral_codes(text)
                        oid = hit.get("objectID")
                        item_url = f"https://news.ycombinator.com/item?id={oid}"
                        for clean_url, code in found:
                            if code not in seen_codes:
                                seen_codes.add(code)
                                records.append(ReferralRecord(
                                    referral_code=code,
                                    url=clean_url,
                                    platform="Hacker News",
                                    source_url=item_url,
                                    author=hit.get("author"),
                                    published_at=hit.get("created_at"),
                                    evidence_snippet=(hit.get("story_title") or hit.get("title") or (hit.get("comment_text") or "")[:150]).strip(),
                                    status="unknown"
                                ))
            except Exception as e:
                print(f"[HackerNewsSource] Error: {e}")
        return records[:limit]

    def find_original_source(self, referral_code: str) -> Optional[ReferralRecord]:
        url = f"https://hn.algolia.com/api/v1/search?query={referral_code}&tags=(story,comment)"
        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                for hit in hits:
                    text = f"{hit.get('title') or ''} {hit.get('comment_text') or ''} {hit.get('url') or ''}"
                    if referral_code in text:
                        oid = hit.get("objectID")
                        return ReferralRecord(
                            referral_code=referral_code,
                            url=f"https://claude.ai/referral/{referral_code}",
                            platform="Hacker News",
                            source_url=f"https://news.ycombinator.com/item?id={oid}",
                            author=hit.get("author"),
                            published_at=hit.get("created_at"),
                            evidence_snippet=(hit.get("title") or (hit.get("comment_text") or "")[:150]).strip(),
                            status="unknown"
                        )
        except Exception as e:
            print(f"[HackerNewsSource] Error: {e}")
        return None
