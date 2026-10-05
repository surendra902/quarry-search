"""Explicit live smoke test. --sweep performs one free-source discovery request."""
import argparse
import json
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('--sweep', action='store_true')
    parser.add_argument('--out', default='.audit/live-browser')
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    base = args.url.rstrip('/')
    result = {'url': base, 'http': []}
    for path, expected in [('/api/status', 200), ('/api/lookup?q=bad%21', 400),
                            ('/api/lookup?q=https%3A%2F%2Fevilclaude.ai%2Freferral%2FYWAsr_1fbA', 400),
                            ('/api/discover', 405)]:
        response = requests.get(base + path, timeout=30)
        assert response.status_code == expected, (path, response.status_code, response.text[:300])
        result['http'].append({'path': path, 'status': response.status_code, 'json': response.json()})
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda err: errors.append(str(err)))
        page.goto(base, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_function("document.querySelector('#serviceStatus').textContent.includes('Service status loaded')", timeout=30000)
        page.wait_for_function("document.querySelector('#linksStatus').textContent.includes('stored records displayed')", timeout=30000)
        result['initial'] = {'count': page.locator('#statCount').inner_text(),
                             'occurrences': page.locator('#statOccurrences').inner_text(),
                             'storage': page.locator('#storageBadge').inner_text()}
        page.locator('#lookupInput').fill('YWAsr_1fbA')
        page.locator('#lookupBtn').click()
        page.wait_for_function("document.querySelector('#lookupStatus').textContent.includes('Direct source evidence returned')", timeout=90000)
        result['control'] = page.locator('#lookupStatus').inner_text()
        page.locator('#targetBtn').click()
        page.wait_for_function("document.querySelector('#lookupStatus').textContent.startsWith('Unresolved:')", timeout=90000)
        result['sample'] = page.locator('#lookupStatus').inner_text()
        page.locator('#lookupInput').fill('bad!')
        page.locator('#lookupInput').press('Enter')
        page.wait_for_function("document.querySelector('#lookupStatus').textContent.includes('HTTP 400')", timeout=30000)
        result['invalid_input'] = page.locator('#lookupStatus').inner_text()
        if args.sweep:
            page.locator('#sweepBtn').click()
            page.wait_for_function("!document.querySelector('#sweepBtn').disabled", timeout=120000)
            result['sweep'] = page.locator('#sweepStatus').inner_text()
            assert 'request failed' not in result['sweep'].lower(), result['sweep']
            assert 'candidates reported' in result['sweep'], result['sweep']
        page.screenshot(path=str(out / 'desktop.png'))
        page.set_viewport_size({'width': 375, 'height': 812})
        page.screenshot(path=str(out / 'mobile.png'))
        overflow = page.evaluate('document.documentElement.scrollWidth > innerWidth')
        assert not overflow, 'Mobile viewport overflow'
        assert not errors, errors
        result.update(javascript_errors=errors, mobile_overflow=overflow)
        browser.close()
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
