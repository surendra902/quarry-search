"""Bounded source adapters with explicit coverage and evidence semantics."""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
import html
import re
import time
from typing import List, Optional

import requests
from quarry.models import ReferralRecord
from quarry.extractors import extract_referral_codes, extract_code_from_url


class BaseSource(ABC):
    name = "base"
    max_requests = 8
    budget_seconds = 35

    def _start(self):
        self.last_report = {"status": "ok", "messages": [],
                            "coverage_limited": True, "request_count": 0}
        self._deadline = time.monotonic() + self.budget_seconds
        self._successful_requests = 0
        self._failed_statuses = []

    def _problem(self, status, message):
        self.last_report["messages"].append(message)
        self.last_report["coverage_limited"] = True
        self._failed_statuses.append(status)
        if self._successful_requests:
            self.last_report["status"] = "partial"
        else:
            priority = ("rate_limited", "blocked", "unavailable", "error", "partial")
            self.last_report["status"] = next(s for s in priority if s in self._failed_statuses)

    def _success(self):
        self._successful_requests += 1
        if self._failed_statuses:
            self.last_report["status"] = "partial"

    def _reserve_request(self):
        remaining = self._deadline - time.monotonic()
        if self.last_report["request_count"] >= self.max_requests or remaining <= 0:
            self._problem("partial", "Request/time budget reached; some results were not scanned.")
            return None
        self.last_report["request_count"] += 1
        return min(8, max(0.1, remaining / 2))

    def _http_failure(self, response, label):
        status = getattr(response, "status_code", getattr(response, "status", None))
        if status == 200:
            return False
        headers = getattr(response, "headers", {}) or {}
        kind = "rate_limited" if status == 429 or (
            status == 403 and (headers.get("X-RateLimit-Remaining") == "0" or headers.get("Retry-After"))
        ) else "blocked" if status in (401, 403) else "error"
        self._problem(kind, f"{label}: HTTP {status}; no healthy-empty inference is possible.")
        return True

    def _get_json(self, url, **kwargs):
        timeout = self._reserve_request()
        if timeout is None:
            return None
        try:
            result = requests.get(url, timeout=(min(3, timeout), timeout), allow_redirects=False, **kwargs)
            if self._http_failure(result, url):
                return None
            data = result.json()
            if not isinstance(data, dict):
                self._problem("error", f"{url}: missing or malformed JSON object.")
                return None
            self._success()
            return data
        except (requests.RequestException, ValueError, TypeError) as exc:
            self._problem("error", f"{url}: {type(exc).__name__}; request or response failed.")
            return None

    @staticmethod
    def _limit(limit):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("limit must be a non-negative integer")
        return min(limit, 100)

    def _code(self, code):
        # Source lookup accepts a token, not an arbitrary search expression.
        if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", code):
            self._problem("error", "Invalid referral token; no requests were made.")
            return None
        try:
            return extract_code_from_url(code)
        except ValueError:
            self._problem("error", "Invalid referral token; no requests were made.")
            return None

    @staticmethod
    def _evidence(text, code):
        # An early bare mention must not displace the actual link from evidence.
        decoded = html.unescape(text)
        for match in re.finditer(re.escape(code), decoded):
            excerpt = decoded[max(0, match.start() - 100):match.end() + 100]
            if any(token == code for _, token in extract_referral_codes(excerpt)):
                return excerpt
        return decoded  # Preserve the complete source if no short excerpt proves it.

    @staticmethod
    def _iso_timestamp(value):
        if value is None or isinstance(value, bool):
            return None
        try:
            return datetime.fromtimestamp(float(value), timezone.utc).isoformat().replace("+00:00", "Z")
        except (TypeError, ValueError, OverflowError, OSError):
            return None

    def _finish(self, records, limit):
        unique = {}
        for record in records:
            unique.setdefault((record.referral_code, record.source_url, record.platform), record)
        if len(unique) > limit:
            self._problem("partial", "Result limit reached; additional observed occurrences were omitted.")
        self.last_report["messages"].append(
            "Bounded public/indexed coverage only; a match is not proof of the original author or current redemption status."
        )
        return list(unique.values())[:limit]

    @abstractmethod
    def discover_new(self, limit: int = 50) -> List[ReferralRecord]:
        """Return observed referral occurrences, not guaranteed-new codes."""

    @abstractmethod
    def find_original_source(self, referral_code: str) -> Optional[ReferralRecord]:
        """Compatibility name: return a matching occurrence, NOT a proven origin."""

    def find_sources(self, referral_code: str, limit: int = 20) -> List[ReferralRecord]:
        # Compatibility for third-party adapters implementing the original interface.
        if self._limit(limit) == 0:
            return []
        record = self.find_original_source(referral_code)
        return [record] if record else []
