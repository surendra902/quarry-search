"""GitHub API occurrences: exact links in issue/PR text or commit messages."""
from typing import List, Optional
from urllib.parse import urlsplit
import requests
from quarry.sources.base import BaseSource
from quarry.models import ReferralRecord
from quarry.extractors import extract_referral_codes


class GitHubSource(BaseSource):
    name = "github"
    max_requests = 2

    def __init__(self, token: Optional[str] = None):
        self.headers = {"User-Agent": "quarry-search-bot/1.0",
                        "Accept": "application/vnd.github+json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self._start()

    def _search(self, code, limit):
        records = []
        for category in ("issues", "commits"):
            data = self._get_json(
                f"https://api.github.com/search/{category}", headers=self.headers,
                params={"q": f'"claude.ai/referral/{code}"' if code else '"claude.ai/referral"',
                        "sort": "created" if category == "issues" else "committer-date",
                        "order": "desc", "per_page": 30, "page": 1})
            if data is None:
                continue
            items = data.get("items")
            if not isinstance(items, list):
                self._problem("error", f"GitHub {category}: missing items list.")
                continue
            total = data.get("total_count")
            if data.get("incomplete_results") or len(items) >= 30 or (
                    isinstance(total, int) and total > len(items)):
                self._problem("partial", f"GitHub {category}: additional/incomplete search pages not scanned.")
            for item in items:
                if not isinstance(item, dict):
                    self._problem("error", f"GitHub {category}: malformed item.")
                    continue
                source_url = item.get("html_url") or ""
                try:
                    valid_source = urlsplit(source_url).scheme == "https" and urlsplit(source_url).hostname == "github.com"
                except ValueError:
                    valid_source = False
                if not valid_source:
                    self._problem("error", f"GitHub {category}: missing/invalid first-party source URL.")
                    continue
                commit = item.get("commit") or {}
                if category == "issues":
                    text = f"{item.get('title') or ''}\n{item.get('body') or ''}"
                    author = (item.get("user") or {}).get("login")
                    published = item.get("created_at")
                    updated = item.get("updated_at")
                    basis = "issue_created_at; content_observed_now; updated_at_is_last_edit_not_link_time"
                else:
                    text = commit.get("message") or ""
                    author = (item.get("author") or {}).get("login") or (commit.get("author") or {}).get("name")
                    published = (commit.get("committer") or {}).get("date")
                    updated = None
                    basis = "commit_committer_date; self_reported_git_metadata_not_publication_or_origin_proof"
                for clean_url, found_code in extract_referral_codes(text):
                    if code is not None and found_code != code:
                        continue
                    record = ReferralRecord(
                        referral_code=found_code, url=clean_url,
                        platform="GitHub (Issue/PR)" if category == "issues" else "GitHub (Commit)",
                        source_url=source_url, author=author, published_at=published,
                        evidence_snippet=self._evidence(text, found_code), status="unknown",
                        evidence_kind="direct_match", source_updated_at=updated, timestamp_basis=basis)
                    records.append(record)
        return self._finish(records, limit)

    def discover_new(self, limit: int = 50) -> List[ReferralRecord]:
        self._start()
        limit = self._limit(limit)
        return self._search(None, limit) if limit else self._finish([], 0)

    def find_sources(self, referral_code: str, limit: int = 20) -> List[ReferralRecord]:
        self._start()
        limit = self._limit(limit)
        code = self._code(referral_code)
        return self._search(code, limit) if code and limit else self._finish([], limit)

    def find_original_source(self, referral_code: str) -> Optional[ReferralRecord]:
        records = self.find_sources(referral_code, limit=1)
        return records[0] if records else None
