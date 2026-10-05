import requests
import re
import urllib.parse
from typing import List, Optional
from bs4 import BeautifulSoup
from quarry.sources.base import BaseSource
from quarry.models import ReferralRecord
from quarry.extractors import extract_referral_codes

class WebDorkSource(BaseSource):
    name = "web_dorks"

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    def discover_new(self, limit: int = 50) -> List[ReferralRecord]:
        records: List[ReferralRecord] = []
        dorks = [
            '"claude.ai/referral"',
            'site:x.com "claude.ai/referral"',
            'site:twitter.com "claude.ai/referral"',
            'site:threads.net "claude.ai/referral"',
            'site:dev.to "claude.ai/referral"',
        ]
        seen_codes = set()
        for dork in dorks:
            try:
                resp = requests.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": dork},
                    headers=self.headers,
                    timeout=10
                )
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    results = soup.find_all("div", class_="result__body")
                    for res in results:
                        link_tag = res.find("a", class_="result__url")
                        snippet_tag = res.find("a", class_="result__snippet")
                        title_tag = res.find("a", class_="result__title")
                        
                        target_url = link_tag.get("href") if link_tag else ""
                        snippet_text = snippet_tag.text if snippet_tag else ""
                        title_text = title_tag.text if title_tag else ""
                        full_text = f"{target_url}\n{snippet_text}\n{title_text}"
                        
                        found = extract_referral_codes(full_text)
                        for clean_url, code in found:
                            if code not in seen_codes:
                                seen_codes.add(code)
                                records.append(ReferralRecord(
                                    referral_code=code,
                                    url=clean_url,
                                    platform="Web Search Dork",
                                    source_url=target_url or clean_url,
                                    author="Web Author",
                                    published_at=None,
                                    evidence_snippet=snippet_text[:180],
                                    status="unknown"
                                ))
            except Exception as e:
                print(f"[WebDorkSource] Error: {e}")
        return records[:limit]

    def find_original_source(self, referral_code: str) -> Optional[ReferralRecord]:
        dork = f'"{referral_code}"'
        try:
            resp = requests.post(
                "https://html.duckduckgo.com/html/",
                data={"q": dork},
                headers=self.headers,
                timeout=10
            )
            if resp.status_code == 200 and referral_code in resp.text:
                soup = BeautifulSoup(resp.text, "html.parser")
                results = soup.find_all("div", class_="result__body")
                for res in results:
                    snippet = res.find("a", class_="result__snippet")
                    title = res.find("a", class_="result__title")
                    link = res.find("a", class_="result__url")
                    if snippet and referral_code in (snippet.text + (title.text if title else "")):
                        return ReferralRecord(
                            referral_code=referral_code,
                            url=f"https://claude.ai/referral/{referral_code}",
                            platform="Web Search",
                            source_url=link.get("href") if link else "https://duckduckgo.com",
                            author=None,
                            published_at=None,
                            evidence_snippet=snippet.text[:180],
                            status="unknown"
                        )
        except Exception:
            pass
        return None
