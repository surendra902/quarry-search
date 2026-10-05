import unittest
import os
import tempfile
from quarry.models import ReferralRecord
from quarry.storage import QuarryStorage
from quarry.extractors import extract_referral_codes, extract_code_from_url, is_valid_referral_format
from quarry.engine import QuarryEngine
from quarry.sources.base import BaseSource

class MockTestSource(BaseSource):
    name = "mock_source"
    
    def discover_new(self, limit: int = 50):
        return [
            ReferralRecord(
                referral_code="MockCode123",
                url="https://claude.ai/referral/MockCode123",
                platform="MockPlatform",
                source_url="https://example.com/post/1",
                author="alice",
                published_at="2026-10-01T12:00:00Z",
                evidence_snippet="Check out my Claude referral MockCode123"
            )
        ]

    def find_original_source(self, referral_code: str):
        if referral_code == "MockCode123":
            return ReferralRecord(
                referral_code="MockCode123",
                url="https://claude.ai/referral/MockCode123",
                platform="MockPlatform",
                source_url="https://example.com/post/1",
                author="alice",
                published_at="2026-10-01T12:00:00Z",
                evidence_snippet="Check out my Claude referral MockCode123"
            )
        return None

class TestQuarrySearch(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.storage = QuarryStorage(db_path=self.temp_db.name)

    def tearDown(self):
        if os.path.exists(self.temp_db.name):
            try:
                os.remove(self.temp_db.name)
            except:
                pass

    def test_extract_referral_codes(self):
        sample_text = """
        Here is a link: https://claude.ai/referral/PFQOnxQmRQ and an HTML one:
        &lt;a href="https:&#x2F;&#x2F;claude.ai&#x2F;referral&#x2F;YWAsr_1fbA"&gt;link&lt;/a&gt;
        and another: claude.ai/referral/pIpeQjEpEw.
        Ignore fake placeholder: https://claude.ai/referral/YOUR_CODE
        """
        extracted = extract_referral_codes(sample_text)
        codes = [c for _, c in extracted]
        self.assertIn("PFQOnxQmRQ", codes)
        self.assertIn("YWAsr_1fbA", codes)
        self.assertIn("pIpeQjEpEw", codes)
        self.assertNotIn("YOUR_CODE", codes)

    def test_is_valid_referral_format(self):
        self.assertTrue(is_valid_referral_format("PFQOnxQmRQ"))
        self.assertTrue(is_valid_referral_format("https://claude.ai/referral/YWAsr_1fbA"))
        self.assertFalse(is_valid_referral_format("short"))
        self.assertFalse(is_valid_referral_format("invalid!@#$%^"))

    def test_storage_save_and_deduplication(self):
        rec = ReferralRecord(
            referral_code="TestCodeABC",
            url="https://claude.ai/referral/TestCodeABC",
            platform="UnitTester",
            source_url="https://example.com/test",
            author="tester",
            published_at="2026-10-05T00:00:00Z",
            evidence_snippet="Test evidence"
        )
        # First save succeeds
        saved = self.storage.save_link(rec)
        self.assertTrue(saved)
        self.assertEqual(self.storage.count(), 1)

        # Duplicate save returns False (deduplicated)
        saved_again = self.storage.save_link(rec)
        self.assertFalse(saved_again)
        self.assertEqual(self.storage.count(), 1)

        # Retrieval
        fetched = self.storage.get_by_code("TestCodeABC")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["author"], "tester")
        self.assertEqual(fetched["platform"], "UnitTester")

    def test_engine_discovery_and_lookup(self):
        mock_source = MockTestSource()
        engine = QuarryEngine(storage=self.storage, sources=[mock_source])
        
        # Test discovery
        summary = engine.discover(limit_per_source=10)
        self.assertEqual(summary["total_candidates_found"], 1)
        self.assertEqual(summary["new_unique_links_saved"], 1)
        self.assertEqual(self.storage.count(), 1)

        # Test lookup
        result = engine.lookup("MockCode123")
        self.assertIsNotNone(result)
        self.assertEqual(result["author"], "alice")
        self.assertEqual(result["source_url"], "https://example.com/post/1")

if __name__ == "__main__":
    unittest.main()
