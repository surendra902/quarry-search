"""Directory inventory with native evidence; archived stock is not fresh supply."""
import json
from bs4 import BeautifulSoup
from quarry.sources.public_web_source import PublicWebSource
from quarry.extractors import extract_referral_codes
from quarry.models import ReferralRecord


class WebDirectorySource(PublicWebSource):
    name = 'web_directories'
    max_requests = 12
    budget_seconds = 35
    TARGET_URLS = [
        'https://claudecoworkcourse.com/claude-guest-passes',
        'https://claudecoupons.com/referral-codes',
        'https://referraldrop.com/en/drop/claude',
        'https://jdesigns.info/systemized',
        'https://nannyakore.com/en/blog/cursor-ios-app-review-en',
        'https://jtechforums.org/t/claude-code-free-week-giveaway/9011/5',
    ]

    def __init__(self, seeds=None, **kwargs):
        super().__init__(seeds=seeds if seeds is not None else [{'url': url} for url in self.TARGET_URLS], **kwargs)

    def _page_records(self, body, task, actual_url, target):
        soup = BeautifulSoup(body, 'html.parser')
        node = soup.select_one('script#__NEXT_DATA__')
        if node is None:
            return super()._page_records(body, task, actual_url, target)
        try:
            props = json.loads(node.get_text()).get('props', {}).get('pageProps', {})
        except (ValueError, TypeError, AttributeError):
            self._problem('partial', 'Directory state could not be parsed; checking visible page evidence only.')
            return super()._page_records(body, task, actual_url, target)
        rows = []
        seen = set()
        for key in ('codes', 'archivedCodes'):
            items = props.get(key, [])
            if not isinstance(items, list):
                self._problem('partial', f'Directory {key} is not a list.')
                continue
            self.last_report[key + '_reported'] = len(items)
            for item in items:
                if not isinstance(item, dict):
                    continue
                archived = key == 'archivedCodes' or item.get('directory_status') == 'archived'
                for canonical, code in extract_referral_codes(item.get('referral_url', '')):
                    if code in seen or target and code != target:
                        continue
                    seen.add(code)
                    rows.append(ReferralRecord(code, canonical, 'Web Directory (' + actual_url.split('/')[2] + ')',
                        actual_url, author=item.get('display_name') or None,
                        published_at=item.get('created_at'),
                        evidence_snippet=json.dumps(item, ensure_ascii=False), evidence_kind='direct_match',
                        timestamp_basis='directory_archived_submission_time_not_new_post' if archived else 'directory_submission_time_not_referral_issuance'))
        if props.get('archivedCodes'):
            self.last_report['messages'].append('Archived directory entries are historical inventory; click counts do not validate redeemability.')
        # Structured stock wins on duplicates (especially archived labels),
        # but unrelated Next.js state must not hide visible-page evidence.
        for row in super()._page_records(body, task, actual_url, target):
            if row.referral_code not in seen:
                seen.add(row.referral_code)
                rows.append(row)
        return rows
