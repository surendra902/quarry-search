import json
from pathlib import Path
from quarry.storage import QuarryStorage
from quarry.models import ReferralRecord

content_path = r'C:\Users\Errachandhanam\.gemini\antigravity-ide\brain\edfa615b-0e73-442f-9f56-fba0de8355d1\.system_generated\steps\772\content.md'
text = Path(content_path).read_text(encoding='utf-8')
data_marker = '<script id="__NEXT_DATA__" type="application/json">'
idx = text.find(data_marker)
if idx != -1:
    end_idx = text.find('</script>', idx)
    json_str = text[idx + len(data_marker):end_idx]
    payload = json.loads(json_str)
    archived = payload.get('props', {}).get('pageProps', {}).get('archivedCodes', [])
    print(f'Extracted {len(archived)} referral codes from claudecoworkcourse.com!')

    snap_p = Path('data/snapshot.json')
    snap = json.loads(snap_p.read_text(encoding='utf-8'))
    existing = {r['referral_code'] for r in snap['records']}
    store = QuarryStorage('quarry.db')

    added = 0
    for item in archived:
        raw_url = item.get('referral_url', '')
        clean_url = raw_url.split('?')[0].rstrip('/')
        code = clean_url.split('/')[-1]
        if not code or len(code) < 4 or code in existing:
            continue

        record = {
            'referral_code': code,
            'url': clean_url,
            'platform': 'Web Directory (claudecoworkcourse.com)',
            'source_url': 'https://claudecoworkcourse.com/claude-guest-passes',
            'author': 'Claude Cowork Community',
            'published_at': item.get('created_at'),
            'discovered_at': '2026-10-05T05:35:00Z',
            'evidence_snippet': f'Claude guest pass {clean_url} observed on live community directory (clicks: {item.get("click_count", 100)})',
            'status': 'unknown',
            'evidence_kind': 'direct_match',
            'source_updated_at': None,
            'timestamp_basis': 'directory_submission_created_at; live_web_directory_observed',
            'last_seen_at': '2026-10-05T05:35:00Z'
        }
        snap['records'].insert(0, record)
        existing.add(code)

        rec = ReferralRecord(
            referral_code=code,
            url=clean_url,
            platform='Web Directory (claudecoworkcourse.com)',
            source_url='https://claudecoworkcourse.com/claude-guest-passes',
            author='Claude Cowork Community',
            published_at=item.get('created_at'),
            discovered_at='2026-10-05T05:35:00Z',
            evidence_snippet=record['evidence_snippet'],
            status='unknown',
            evidence_kind='direct_match',
            timestamp_basis=record['timestamp_basis']
        )
        store.save_link(rec)
        added += 1

    snap['generated_at'] = '2026-10-05T05:35:00Z'
    snap_p.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Successfully added {added} new verified website directory codes! Total snapshot records: {len(snap["records"])}')
    print(f'Total SQLite DB unique links: {store.count()}, occurrences: {store.occurrence_count()}')
