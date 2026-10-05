"""Source adapter for community web directories and coupon platforms."""
import re
from typing import List, Optional
import requests
from bs4 import BeautifulSoup

from quarry.sources.base import BaseSource
from quarry.models import ReferralRecord
from quarry.extractors import extract_referral_codes


class WebDirectorySource(BaseSource):
    name = "web_directories"
    max_requests = 4
    budget_seconds = 20

    TARGET_URLS = [
        "https://claudecoworkcourse.com/claude-guest-passes",
        "https://claudecoupons.com/referral-codes",
        "https://referraldrop.com/en/drop/claude"
    ]

    def __init__(self):
        self._start()

    def discover_new(self, limit: int = 50) -> List[ReferralRecord]:
        self._start()
        limit = self._limit(limit)
        if not limit:
            return self._finish([], 0)

        records = []
        for url in self.TARGET_URLS:
            timeout = self._reserve_request()
            if timeout is None:
                break
            try:
                resp = requests.get(
                    url,
                    timeout=(min(3, timeout), timeout),
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                )
                if resp.status_code != 200:
                    self._problem("partial", f"{url}: HTTP {resp.status_code}")
                    continue
                self._success()
                text = resp.text

                # Check for Next.js __NEXT_DATA__
                marker = '<script id="__NEXT_DATA__" type="application/json">'
                if marker in text:
                    try:
                        import json
                        idx = text.find(marker)
                        end_idx = text.find('</script>', idx)
                        json_str = text[idx + len(marker):end_idx]
                        payload = json.loads(json_str)
                        archived = payload.get('props', {}).get('pageProps', {}).get('archivedCodes', [])
                        for item in archived:
                            raw = item.get('referral_url', '')
                            for clean_url, code in extract_referral_codes(raw):
                                records.append(ReferralRecord(
                                    referral_code=code,
                                    url=clean_url,
                                    platform=f"Web Directory ({url.split('/')[2]})",
                                    source_url=url,
                                    author="Community Member",
                                    published_at=item.get('created_at'),
                                    evidence_snippet=f"Referral pass {clean_url} listed on live community directory (clicks: {item.get('click_count', 0)})",
                                    status="unknown",
                                    evidence_kind="direct_match",
                                    timestamp_basis="directory_submission_created_at; live_web_directory_observed"
                                ))
                    except Exception:
                        pass

                # Also parse standard HTML body
                soup = BeautifulSoup(text, "html.parser")
                body_text = soup.get_text(" ", strip=True)
                for clean_url, code in extract_referral_codes(body_text + " " + text):
                    records.append(ReferralRecord(
                        referral_code=code,
                        url=clean_url,
                        platform=f"Web Directory ({url.split('/')[2]})",
                        source_url=url,
                        author="Directory Curator",
                        published_at=None,
                        evidence_snippet=self._evidence(body_text, code),
                        status="unknown",
                        evidence_kind="direct_match",
                        timestamp_basis="web_directory_observed_now"
                    ))
            except Exception as exc:
                self._problem("error", f"{url}: {type(exc).__name__}: {exc}")

        return self._finish(records, limit)

    def find_original_source(self, referral_code: str) -> Optional[ReferralRecord]:
        matches = self.find_sources(referral_code, limit=1)
        return matches[0] if matches else None

    def find_sources(self, referral_code: str, limit: int = 20) -> List[ReferralRecord]:
        self._start()
        limit = self._limit(limit)
        code = self._code(referral_code)
        if not code or not limit:
            return self._finish([], 0)

        all_records = self.discover_new(limit=100)
        matching = [r for r in all_records if r.referral_code == code]
        return self._finish(matching, limit)
