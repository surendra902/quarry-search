"""URLScan observations are discovery candidates, not original source posts."""
import json
from urllib.parse import urlsplit
from quarry.sources.base import BaseSource
from quarry.models import ReferralRecord
from quarry.extractors import extract_referral_codes


class URLScanSource(BaseSource):
    name = 'urlscan'
    max_requests = 2
    budget_seconds = 15

    def __init__(self, api_key=None):
        self.api_key = api_key
        self._start()

    def _query(self, query, limit=25, target_code=None):
        headers = {'User-Agent': 'QuarrySearch/1.0'}
        if self.api_key:
            headers['API-Key'] = self.api_key
        data = self._get_json('https://urlscan.io/api/v1/search/', headers=headers,
                              params={'q': query, 'size': min(50, limit)})
        if data is None:
            return []
        rows = []
        results = data.get('results', [])
        if not isinstance(results, list):
            self._problem('error', 'URLScan returned a malformed result list.')
            return []
        for item in results:
            if not isinstance(item, dict):
                self._problem('partial', 'Malformed scan entry skipped.')
                continue
            page, task = item.get('page') or {}, item.get('task') or {}
            source = item.get('result', '')
            if not isinstance(source, str) or urlsplit(source).hostname != 'urlscan.io':
                self._problem('partial', 'Scan without a stable first-party result URL was skipped.')
                continue
            evidence = json.dumps({'page_url': page.get('url'), 'submitted_url': task.get('url'),
                                   'scan_time': task.get('time')}, ensure_ascii=False)
            for canonical, code in extract_referral_codes(evidence):
                if target_code and target_code != code:
                    continue
                rows.append(ReferralRecord(code, canonical, 'Web (URLScan Intelligence)', source,
                    author=None, published_at=None, source_updated_at=task.get('time'),
                    evidence_snippet=evidence, evidence_kind='candidate_only',
                    timestamp_basis='urlscan_observation_time_not_source_publication'))
        self.last_report['messages'].append('Scan timestamps are observations, not source-post publication times; original source remains unverified.')
        return rows

    def discover_new(self, limit=50):
        self._start()
        limit = self._limit(limit)
        if not limit:
            return self._finish([], 0)
        rows = self._query('page.domain:claude.ai AND page.url:referral', limit=limit)
        return self._finish(rows, limit)

    def find_sources(self, referral_code, limit=20):
        self._start()
        limit = self._limit(limit)
        code = self._code(referral_code)
        return self._finish(self._query(f'page.url:"claude.ai/referral/{code}"', limit, code), limit) if code and limit else self._finish([], 0)

    def find_original_source(self, referral_code):
        rows = self.find_sources(referral_code, 1)
        return rows[0] if rows else None
