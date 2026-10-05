import requests
import re
import urllib.parse
from typing import List, Optional
from bs4 import BeautifulSoup
from quarry.sources.base import BaseSource
from quarry.models import ReferralRecord
from quarry.extractors import extract_referral_codes

class RedditSource(BaseSource):
    name = "reddit"

    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    def discover_new(self, limit: int = 50) -> List[ReferralRecord]:
        records: List[ReferralRecord] = []
        subreddits = ["ClaudeAI", "ClaudeCode", "ReferralCodes", "referral", "ChatGPT"]
        
        for sub in subreddits:
            url = f"https://www.reddit.com/r/{sub}/new.json?limit=25"
            try:
                resp = requests.get(url, headers={"User-Agent": "quarry-research:v1.0 (by /u/quarrybot)"}, timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    children = data.get("data", {}).get("children", [])
                    for child in children:
                        pdata = child.get("data", {})
                        title = pdata.get("title", "")
                        selftext = pdata.get("selftext", "")
                        permalink = pdata.get("permalink", "")
                        full_post_url = f"https://reddit.com{permalink}"
                        
                        text = f"{title}\n{selftext}"
                        found = extract_referral_codes(text)
                        for clean_url, code in found:
                            records.append(ReferralRecord(
                                referral_code=code,
                                url=clean_url,
                                platform=f"Reddit (r/{sub})",
                                source_url=full_post_url,
                                author=pdata.get("author"),
                                published_at=str(pdata.get("created_utc")),
                                evidence_snippet=title[:180],
                                status="unknown"
                            ))
            except Exception as e:
                # Silently catch rate-limits/403 on unauthenticated json
                pass
                
        return records[:limit]

    def find_original_source(self, referral_code: str) -> Optional[ReferralRecord]:
        # Check Reddit search endpoint via Pullpush archive
        try:
            pp_url = f"https://api.pullpush.io/reddit/search/submission/?q={referral_code}"
            r = requests.get(pp_url, headers=self.headers, timeout=8)
            if r.status_code == 200:
                items = r.json().get("data", [])
                if items:
                    it = items[0]
                    return ReferralRecord(
                        referral_code=referral_code,
                        url=f"https://claude.ai/referral/{referral_code}",
                        platform=f"Reddit (r/{it.get('subreddit')})",
                        source_url=f"https://reddit.com{it.get('permalink')}",
                        author=it.get("author"),
                        published_at=str(it.get("created_utc")),
                        evidence_snippet=it.get("title", "")[:180],
                        status="unknown"
                    )
        except Exception:
            pass
        return None
