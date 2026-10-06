"""Bounded discovery and earliest-evidenced lookup, never global-origin claims."""
import os
from concurrent.futures import ThreadPoolExecutor
from quarry.storage import QuarryStorage, evidence_order
from quarry.models import utc_now
from quarry.extractors import extract_code_from_url, extract_referral_codes, is_excluded_source
from quarry.sources.github_source import GitHubSource
from quarry.sources.hackernews_source import HackerNewsSource


class QuarryEngine:
    def __init__(self, storage=None, sources=None):
        self.storage = storage if storage is not None else QuarryStorage()
        if sources is None:
            sources = [GitHubSource(token=os.environ.get('GITHUB_TOKEN')), HackerNewsSource()]
            try:
                from quarry.sources.web_directory_source import WebDirectorySource
                sources.append(WebDirectorySource())
            except ImportError:
                pass
            try:
                from quarry.sources.urlscan_source import URLScanSource
                sources.append(URLScanSource())
            except ImportError:
                pass
            try:
                from quarry.sources.tech_community_source import TechCommunitySource
                sources.append(TechCommunitySource())
            except ImportError:
                pass
            if os.environ.get('QUARRY_ENABLE_PAID_SOURCES') == '1' and os.environ.get('EXA_API_KEY'):
                try:
                    from quarry.sources.exa_source import ExaSource
                    sources.append(ExaSource(storage=self.storage))
                except ImportError:
                    pass
            if os.environ.get('QUARRY_ENABLE_PAID_SOURCES') == '1' and os.environ.get('TAVILY_API_KEY'):
                try:
                    from quarry.sources.tavily_source import TavilySource
                    sources.append(TavilySource())
                except ImportError:
                    pass
            if os.environ.get('QUARRY_ENABLE_PAID_SOURCES') == '1' and os.environ.get('APIFY_API_TOKEN'):
                try:
                    from quarry.sources.apify_source import ApifySource
                    sources.append(ApifySource())
                except ImportError:
                    pass
            if os.environ.get('QUARRY_ENABLE_PAID_SOURCES') == '1' and os.environ.get('SERPAPI_API_KEY'):
                try:
                    from quarry.sources.serp_source import SerpSource
                    sources.append(SerpSource(storage=self.storage))
                except ImportError:
                    pass
            if os.environ.get('QUARRY_WEB_SEARCH') == '1':
                from quarry.sources.web_dork_source import WebDorkSource
                sources.append(WebDorkSource())
            if os.environ.get('QUARRY_REDDIT_ENABLED') == '1':
                from quarry.sources.reddit_source import RedditSource
                sources.append(RedditSource(enabled=True))
            from quarry.sources.public_web_source import PublicWebSource
            sources.append(PublicWebSource(cursor=self.storage.get_state('public_web_cursor', 0)))
        self.sources = sources

    def _run_source(self, source, code=None, limit=20):
        try:
            if code is None:
                rows = source.discover_new(limit=limit)
            elif hasattr(source, 'find_sources'):
                rows = source.find_sources(code, limit=limit)
            else:
                row = source.find_original_source(code)
                rows = [row] if row else []
            report = dict(getattr(source, 'last_report', {}) or {})
            report.setdefault('status', 'ok')
            report.setdefault('messages', [])
            accepted = []
            for row in rows:
                try:
                    if is_excluded_source(row.source_url):
                        report['messages'].append('Excluded an X/Twitter result by collection policy.')
                        continue
                    exact = extract_code_from_url(row.url)
                    if exact != row.referral_code or (code is not None and exact != code):
                        raise ValueError('Source returned a different identifier.')
                    if row.evidence_kind == 'direct_match' and exact not in {c for _, c in extract_referral_codes(row.evidence_snippet or '')}:
                        raise ValueError('Direct evidence does not contain the full referral URL.')
                    accepted.append(row)
                except (AttributeError, TypeError, ValueError):
                    report['status'] = 'partial'
                    report['messages'].append('Discarded a record without consistent exact-link evidence.')
            report['records'] = len(accepted)
            return source.name, accepted, report
        except Exception as exc:
            return source.name, [], {'status': 'error', 'messages': [str(exc)[:300]], 'records': 0}

    def _gather(self, code=None, limit=20):
        if not self.sources:
            return []
        with ThreadPoolExecutor(max_workers=min(4, len(self.sources))) as pool:
            return list(pool.map(lambda source: self._run_source(source, code, limit), self.sources))

    def discover(self, limit_per_source=20):
        if not self.storage.get_state('measurement_started_at'):
            self.storage.set_state('measurement_started_at', utc_now())
        reports, rows, seen = {}, [], set()
        for name, found, report in self._gather(limit=limit_per_source):
            reports[name] = report
            if name == 'public_web' and isinstance(report.get('next_cursor'), int):
                self.storage.set_state('public_web_cursor', report['next_cursor'])
            for row in found:
                key = (row.referral_code, row.source_url)
                if key not in seen:
                    seen.add(key)
                    rows.append(row)
        new, saved_codes = [], set()
        for row in rows:
            inserted = self.storage.save_link(row)
            if inserted:
                saved_codes.add(row.referral_code)
                new.append(row.to_dict())
        summary = {
            'timestamp': utc_now(), 'total_candidates_found': len(rows),
            'new_unique_links_saved': len(saved_codes), 'total_links_in_db': self.storage.count(),
            'source_breakdown': {name: r['records'] for name, r in reports.items()},
            'source_reports': reports, 'new_records': new,
            'candidate_records': [row.to_dict() for row in rows],
            'persistent': self.storage.persistent, 'stored': self.storage.writable,
            'partial': any(r['status'] != 'ok' for r in reports.values()),
            'message': 'Observed links may be historical; validity remains unknown.' if self.storage.writable else 'Read-only deployment snapshot. Live results are returned but are not saved.'
        }
        summary['daily_yield'] = self.storage.yield_summary()
        self.storage.set_state('last_sweep', summary)
        return summary

    def lookup_detailed(self, value, refresh=False):
        code = extract_code_from_url(value)
        cached = self.storage.get_occurrences(code)
        verified_cached = [r for r in cached if r.get('evidence_kind') in ('direct_match', 'archive_match')]
        reports, gathered = {}, []
        if not verified_cached or refresh:
            for name, found, report in self._gather(code=code):
                reports[name] = report
                for row in found:
                    self.storage.save_link(row)
                    gathered.append(row.to_dict())
        merged = {(r['referral_code'], r['source_url']): r for r in cached}
        for row in gathered:
            key = (row['referral_code'], row['source_url'])
            if key not in merged or evidence_order(row) <= evidence_order(merged[key]):
                merged[key] = row
        occurrences = sorted(merged.values(), key=evidence_order)
        verified = [r for r in occurrences if r.get('evidence_kind') in ('direct_match', 'archive_match')]
        record = dict(verified[0]) if verified else None
        if record:
            record['cached'] = not gathered
        partial = any(r['status'] != 'ok' for r in reports.values())
        return {
            'found': bool(record), 'record': record, 'occurrences': occurrences,
            'source_reports': reports, 'partial': partial, 'code': code,
            'message': 'Earliest evidenced occurrence among the matches checked; not proof of the original public post.' if record else 'No verified occurrence found in the sources checked. Unchecked, blocked, deleted or unindexed sources remain unknown.',
            'persistent': self.storage.persistent, 'stored': self.storage.writable,
        }

    def lookup(self, value):
        return self.lookup_detailed(value)['record']
