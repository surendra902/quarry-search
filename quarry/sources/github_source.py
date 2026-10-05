import requests
import re
from typing import List, Optional
from datetime import datetime
from quarry.sources.base import BaseSource
from quarry.models import ReferralRecord
from quarry.extractors import extract_referral_codes

class GitHubSource(BaseSource):
    name = "github"

    def __init__(self, token: Optional[str] = None):
        self.headers = {
            "User-Agent": "quarry-search-bot/1.0",
            "Accept": "application/vnd.github.v3+json",
        }
        if token:
            self.headers["Authorization"] = f"token {token}"

    def discover_new(self, limit: int = 50) -> List[ReferralRecord]:
        records: List[ReferralRecord] = []
        
        # 1. Search issues & pull requests
        try:
            url = "https://api.github.com/search/issues?q=%22claude.ai/referral%22&sort=created&order=desc&per_page=30"
            resp = requests.get(url, headers=self.headers, timeout=12)
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    body = item.get("body") or ""
                    title = item.get("title") or ""
                    text = f"{title}\n{body}"
                    found = extract_referral_codes(text)
                    for clean_url, code in found:
                        records.append(ReferralRecord(
                            referral_code=code,
                            url=clean_url,
                            platform="GitHub (Issue/PR)",
                            source_url=item.get("html_url"),
                            author=item.get("user", {}).get("login"),
                            published_at=item.get("created_at"),
                            evidence_snippet=title[:180],
                            status="unknown"
                        ))
        except Exception as e:
            print(f"[GitHubSource] Error querying issues: {e}")

        # 2. Search commits
        try:
            commit_headers = dict(self.headers)
            commit_headers["Accept"] = "application/vnd.github.cloak-preview"
            c_url = "https://api.github.com/search/commits?q=%22claude.ai/referral%22&sort=author-date&order=desc&per_page=20"
            c_resp = requests.get(c_url, headers=commit_headers, timeout=12)
            if c_resp.status_code == 200:
                items = c_resp.json().get("items", [])
                for item in items:
                    msg = item.get("commit", {}).get("message", "")
                    found = extract_referral_codes(msg)
                    for clean_url, code in found:
                        records.append(ReferralRecord(
                            referral_code=code,
                            url=clean_url,
                            platform="GitHub (Commit)",
                            source_url=item.get("html_url"),
                            author=item.get("commit", {}).get("author", {}).get("name"),
                            published_at=item.get("commit", {}).get("author", {}).get("date"),
                            evidence_snippet=msg[:180].replace("\n", " "),
                            status="unknown"
                        ))
        except Exception as e:
            print(f"[GitHubSource] Error querying commits: {e}")

        return records[:limit]

    def find_original_source(self, referral_code: str) -> Optional[ReferralRecord]:
        queries = [
            ("GitHub (Issue/PR)", f"https://api.github.com/search/issues?q={referral_code}"),
            ("GitHub (Commit)", f"https://api.github.com/search/commits?q={referral_code}"),
        ]
        for platform_label, endpoint in queries:
            try:
                headers = dict(self.headers)
                if "commits" in endpoint:
                    headers["Accept"] = "application/vnd.github.cloak-preview"
                resp = requests.get(endpoint, headers=headers, timeout=12)
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    if items:
                        item = items[0]
                        author = item.get("user", {}).get("login") if "user" in item else item.get("commit", {}).get("author", {}).get("name")
                        pub_date = item.get("created_at") or item.get("commit", {}).get("author", {}).get("date")
                        snippet = item.get("title") or item.get("commit", {}).get("message", "")
                        return ReferralRecord(
                            referral_code=referral_code,
                            url=f"https://claude.ai/referral/{referral_code}",
                            platform=platform_label,
                            source_url=item.get("html_url"),
                            author=author,
                            published_at=pub_date,
                            evidence_snippet=snippet[:180],
                            status="unknown"
                        )
            except Exception as e:
                print(f"[GitHubSource] Error checking {endpoint}: {e}")
        return None
