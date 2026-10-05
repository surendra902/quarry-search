"""Standalone browser contract tests; all API data is a controlled TEST FIXTURE.

Run: python tests/browser_dashboard.py
Requires: pip install playwright && python -m playwright install chromium
No production API, database, credential, or public source is contacted or changed.
"""
import asyncio
import json
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect

PUBLIC = Path(__file__).resolve().parents[1] / "public"
STATUS = {
    "storage": {"mode": "deployment_snapshot", "persistent": False, "writable": False},
    "total_links": 0, "total_occurrences": 0, "sources": ["Fixture Source"],
    "collector": {"configured": False, "last_heartbeat": None, "status": "not_configured"},
    "validation": "not_configured", "notifications": "not_configured", "version": "test-fixture",
}


class DashboardBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch()
        self.page = await self.browser.new_page(viewport={"width": 1280, "height": 900})
        self.responses = {"/api/status": STATUS, "/api/links": []}
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        await self.page.route("**/*", self.route)

    async def asyncTearDown(self):
        await self.browser.close()
        await self.playwright.stop()
        self.assertEqual(self.errors, [], "Unexpected browser JavaScript errors")

    async def route(self, route):
        url = urlsplit(route.request.url)
        if url.hostname != "dashboard.test":
            await route.abort()
            return
        if url.path in ("/", "/app.js"):
            path = PUBLIC / ("index.html" if url.path == "/" else "app.js")
            await route.fulfill(body=path.read_text(encoding="utf-8"), content_type="text/html" if url.path == "/" else "text/javascript")
            return
        data = self.responses.get(url.path, {"error": "Missing TEST FIXTURE"})
        if callable(data):
            await data(route)
            return
        status, data = data if isinstance(data, tuple) else (200, data)
        await route.fulfill(status=status, content_type="application/json", body=json.dumps(data))

    async def open(self):
        await self.page.goto("http://dashboard.test/")

    async def test_truthful_initial_state_and_snapshot(self):
        await self.open()
        await expect(self.page.locator("#statCount")).to_have_text("0")
        await expect(self.page.locator("#storageNote")).to_contain_text("not durable")
        await expect(self.page.locator("#collectorNote")).to_contain_text("not configured")
        await expect(self.page.locator("#tableBody")).to_contain_text("No stored records")
        body = await self.page.locator("body").inner_text()
        for unsupported in ("Total Verified Links", "$0.00", "Audited & Verified", "AutoModerator"):
            self.assertNotIn(unsupported, body)


    async def submit(self, value="Fixture123"):
        await self.page.get_by_label("Referral URL or code", exact=True).fill(value)
        await self.page.locator("#lookupInput").press("Enter")

    async def test_external_strings_are_text_and_only_http_links_clickable(self):
        attack = '<img src=x onerror="window.__xss=1"><svg onload="window.__xss=2">'
        record = {
            "referral_code": attack, "platform": attack, "author": attack,
            "source_url": "javascript:window.__xss=3", "url": "data:text/html,unsafe",
            "evidence_snippet": attack, "evidence_kind": "direct_match", "status": "unknown",
            "published_at": attack, "timestamp_basis": attack, "source_updated_at": attack,
            "discovered_at": "2026-01-02T00:00:00Z",
        }
        occurrence = {**record, "source_url": "https://example.test/observed", "observed_at": "2026-01-01T00:00:00Z"}
        self.responses["/api/links"] = [record]
        self.responses["/api/lookup"] = {
            "found": True, "record": record, "occurrences": [occurrence],
            "source_reports": {attack: {"status": "ok", "message": attack}}, "partial": False,
        }
        await self.open()
        await expect(self.page.locator("#tableBody")).to_contain_text(attack)
        await self.submit()
        await expect(self.page.locator("#lookupStatus")).to_contain_text("Direct source evidence returned")
        await self.page.locator("#lookupResult summary").filter(has_text="Observed occurrences").click()
        await self.page.locator("#lookupResult summary").filter(has_text="Source reports").click()
        await expect(self.page.locator("#lookupResult")).to_contain_text(attack)
        await expect(self.page.locator("#lookupResult")).to_contain_text("2026-01-01T00:00:00Z")
        self.assertEqual(await self.page.locator("img, svg").count(), 0)
        self.assertIsNone(await self.page.evaluate("window.__xss"))
        links = await self.page.locator("#lookupResult a").evaluate_all("nodes => nodes.map(n => ({href:n.href, rel:n.rel, target:n.target}))")
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["href"], "https://example.test/observed")
        self.assertEqual(links[0]["target"], "_blank")
        self.assertIn("noopener", links[0]["rel"])
        self.assertIn("noreferrer", links[0]["rel"])
        await expect(self.page.locator("#lookupResult")).to_contain_text("Unknown — not validated")

    async def test_unavailable_sources_keep_target_unresolved(self):
        self.responses["/api/lookup"] = {
            "found": False, "record": None, "occurrences": [], "partial": True,
            "message": "Fixture source unavailable", "source_reports": {
                "Fixture Source": {"status": "unavailable", "error": "HTTP 429"}
            },
        }
        await self.open()
        await self.page.locator("#targetBtn").click()
        await expect(self.page.locator("#lookupStatus")).to_contain_text("Unresolved")
        await expect(self.page.locator("#lookupStatus")).to_contain_text("PFQOnxQmRQ")
        await expect(self.page.locator("#lookupResult")).to_contain_text("Partial search")
        await self.page.locator("#lookupResult summary").filter(has_text="Source reports").click()
        await expect(self.page.locator("#lookupResult")).to_contain_text("not evidence of no match")
        await expect(self.page.locator("#lookupResult")).to_contain_text("HTTP 429")
        await expect(self.page.locator("#lookupBtn")).to_be_enabled()
        await expect(self.page.locator("#targetBtn")).to_be_enabled()

    async def test_archived_match_is_distinct_from_live_source_validation(self):
        record = {"referral_code": "ArchiveFixture", "evidence_kind": "archive_match", "source_url": "https://example.test/archive", "status": "unknown"}
        self.responses["/api/lookup"] = {"found": True, "record": record, "occurrences": [record], "source_reports": {}, "partial": False}
        await self.open()
        await self.submit("ArchiveFixture")
        await expect(self.page.locator("#lookupStatus")).to_contain_text("Archived source evidence returned")
        await expect(self.page.locator("#lookupResult")).to_contain_text("not a live-page check")
        await expect(self.page.locator("#lookupResult")).to_contain_text("Unknown — not validated")

    async def test_lookup_http_errors_and_empty_input_restore_controls(self):
        await self.open()
        await self.page.locator("#lookupBtn").click()
        await expect(self.page.locator("#lookupStatus")).to_contain_text("Enter a referral URL or code")
        for code in (400, 429, 503):
            self.responses["/api/lookup"] = (code, {"error": '<img src=x onerror="window.__xss=1"> fixture failure'})
            await self.submit()
            await expect(self.page.locator("#lookupStatus")).to_contain_text(f"HTTP {code}")
            await expect(self.page.locator("#lookupStatus")).to_contain_text("target remains unresolved")
            await expect(self.page.locator("#lookupBtn")).to_be_enabled()
            await expect(self.page.locator("#lookupResult")).to_be_hidden()
        self.assertEqual(await self.page.locator("img").count(), 0)

    async def test_invalid_json_network_and_malformed_success_are_errors(self):
        async def invalid(route):
            await route.fulfill(status=200, content_type="text/html", body="not JSON")

        async def offline(route):
            await route.abort("failed")

        await self.open()
        for response, expected in ((invalid, "unreadable JSON"), (offline, "Lookup failed"), ({}, "Unexpected lookup response")):
            self.responses["/api/lookup"] = response
            await self.submit()
            await expect(self.page.locator("#lookupStatus")).to_contain_text(expected)
            await expect(self.page.locator("#lookupBtn")).to_be_enabled()

    async def test_failed_initial_load_does_not_show_zero_or_empty_success(self):
        self.responses["/api/status"] = (503, {"error": "Fixture status unavailable"})
        self.responses["/api/links"] = (500, {"error": "Fixture storage error"})
        await self.open()
        await expect(self.page.locator("#serviceStatus")).to_contain_text("HTTP 503")
        await expect(self.page.locator("#linksStatus")).to_contain_text("HTTP 500")
        await expect(self.page.locator("#tableBody")).to_contain_text("not an empty database result")
        await expect(self.page.locator("#statCount")).to_have_text("—")
        self.responses["/api/status"] = STATUS
        self.responses["/api/links"] = []
        await self.page.locator("#refreshBtn").click()
        await expect(self.page.locator("#statCount")).to_have_text("0")
        await expect(self.page.locator("#tableBody")).to_contain_text("No stored records")

    async def test_snapshot_sweep_results_are_not_claimed_saved(self):
        record = {"referral_code": "FixtureSweep", "source_url": "https://example.test/source", "evidence_kind": "candidate_only"}
        self.responses["/api/discover"] = {
            "total_candidates_found": 1, "new_unique_links_saved": 0, "total_links_in_db": 0,
            "new_records": [], "candidate_records": [record], "source_reports": {"Fixture Source": {"status": "partial"}},
            "stored": False, "persistent": False, "partial": True,
        }
        await self.open()
        await self.page.locator("#sweepBtn").click()
        await expect(self.page.locator("#sweepStatus")).to_contain_text("Results were not saved")
        await expect(self.page.locator("#sweepStatus")).to_contain_text("Partial sweep")
        await expect(self.page.locator("#sweepResults")).to_contain_text("FixtureSweep")
        await expect(self.page.locator("#sweepResults")).to_contain_text("Candidate only — unresolved")
        await expect(self.page.locator("#tableBody")).not_to_contain_text("FixtureSweep")
        await expect(self.page.locator("#statCount")).to_have_text("0")
        await expect(self.page.locator("#sweepBtn")).to_be_enabled()

    async def test_sweep_failure_and_persistent_retry(self):
        self.responses["/api/discover"] = (503, {"error": "Fixture upstream failure"})
        await self.open()
        await self.page.locator("#sweepBtn").click()
        await expect(self.page.locator("#sweepStatus")).to_contain_text("HTTP 503")
        await expect(self.page.locator("#sweepBtn")).to_be_enabled()
        self.responses["/api/discover"] = {
            "total_candidates_found": 0, "new_unique_links_saved": 0, "total_links_in_db": 0,
            "new_records": [], "source_reports": {}, "stored": True, "persistent": True, "partial": False,
        }
        await self.page.locator("#sweepBtn").click()
        await expect(self.page.locator("#sweepStatus")).to_contain_text("0 new unique records saved to persistent storage")
        await expect(self.page.locator("#sweepResults")).to_contain_text("No candidate records returned")
        await expect(self.page.locator("#sweepBtn")).to_be_enabled()

    async def test_editing_during_lookup_prevents_stale_result_race(self):
        started, release = asyncio.Event(), asyncio.Event()

        async def delayed(route):
            started.set()
            await release.wait()
            await route.fulfill(json={"found": True, "record": {"referral_code": "OLD_TARGET", "evidence_kind": "direct_match"}, "occurrences": [], "source_reports": {}})

        self.responses["/api/lookup"] = delayed
        await self.open()
        await self.submit("OLD_TARGET")
        await asyncio.wait_for(started.wait(), timeout=5)
        await expect(self.page.locator("#lookupBtn")).to_be_disabled()
        await expect(self.page.locator("#lookupStatus")).to_contain_text("Searching")
        self.responses["/api/lookup"] = {"found": True, "record": {"referral_code": "NEW_TARGET", "evidence_kind": "direct_match"}, "occurrences": [], "source_reports": {}}
        await self.submit("NEW_TARGET")
        await expect(self.page.locator("#lookupResult")).to_contain_text("NEW_TARGET")
        release.set()
        await self.page.wait_for_timeout(150)
        await expect(self.page.locator("#lookupResult")).not_to_contain_text("OLD_TARGET")
        await expect(self.page.locator("#lookupBtn")).to_be_enabled()

    async def test_mobile_long_external_text_has_no_viewport_overflow(self):
        long_value = "FixtureLong" * 100
        record = {"referral_code": "MobileTest", "source_url": "https://example.test/" + long_value, "author": long_value, "evidence_snippet": long_value, "evidence_kind": "legacy_unverified"}
        self.responses["/api/links"] = [record]
        self.responses["/api/lookup"] = {"found": False, "record": None, "occurrences": [record], "source_reports": {long_value: {"status": long_value}}, "partial": False}
        await self.page.set_viewport_size({"width": 375, "height": 812})
        await self.open()
        await self.submit("MobileTest")
        await expect(self.page.locator("#lookupStatus")).to_contain_text("Unresolved")
        for summary in await self.page.locator("summary").all():
            await summary.click()
        await expect(self.page.locator("#lookupResult")).to_contain_text("Legacy / unverified")
        dimensions = await self.page.evaluate("({viewport:innerWidth, document:document.documentElement.scrollWidth})")
        self.assertEqual(dimensions["viewport"], 375)
        self.assertLessEqual(dimensions["document"], dimensions["viewport"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
