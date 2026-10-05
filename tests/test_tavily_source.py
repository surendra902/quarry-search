import unittest
from unittest.mock import patch, MagicMock
from quarry.sources.tavily_source import TavilySource


class TavilySourceTests(unittest.TestCase):
    def test_unconfigured_returns_unavailable(self):
        src = TavilySource(api_key=None)
        with patch.dict("os.environ", {}, clear=True):
            records = src.discover_new()
            self.assertEqual(records, [])
            self.assertEqual(src.last_report["status"], "unavailable")

    @patch("requests.post")
    def test_parses_tavily_results(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "title": "Claude Pro Free Trial",
                    "url": "https://example.com/blog/claude-deals",
                    "content": "Get Claude using this invite: https://claude.ai/referral/TvLy1234AB"
                }
            ]
        }
        mock_post.return_value = mock_resp

        src = TavilySource(api_key="tvly-mock-key")
        records = src.discover_new()
        # Deduplicated by referral code
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].referral_code, "TvLy1234AB")
        self.assertEqual(records[0].url, "https://claude.ai/referral/TvLy1234AB")


if __name__ == "__main__":
    unittest.main()
