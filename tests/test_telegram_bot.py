"""Unit tests for Telegram Bot service (command dispatch, format safety, and web handler)."""
import io
import json
import unittest
from unittest.mock import Mock, patch

from quarry.telegram_bot import TelegramBotService, _record_val
from quarry.models import ReferralRecord


class MockStorage:
    def __init__(self, links=None):
        self._links = links if links is not None else []
        self.mode = "local_persistent"
        self.writable = True

    def list_links(self, limit=5):
        return self._links[:limit]

    def count(self):
        return len(self._links)

    def occurrence_count(self):
        return len(self._links)

    def get_state(self, key, default=None):
        return default

    def set_state(self, key, value):
        pass


class TelegramBotTests(unittest.TestCase):
    def setUp(self):
        self.sample_links = [
            {
                "referral_code": "CodeAlpha123",
                "url": "https://claude.ai/referral/CodeAlpha123",
                "platform": "DEV.to (Tech Community)",
                "source_url": "https://dev.to/user/post1",
                "discovered_at": "2026-10-06T10:00:00Z"
            },
            {
                "referral_code": "CodeBeta456",
                "url": "https://claude.ai/referral/CodeBeta456",
                "platform": "Qiita (Web Forum)",
                "source_url": "https://qiita.com/user/post2",
                "discovered_at": "2026-10-06T09:30:00Z"
            }
        ]
        self.storage = MockStorage(self.sample_links)
        self.bot = TelegramBotService(token="123456:FAKE_TOKEN_FOR_TESTS", storage=self.storage)

    def test_record_val_helper_handles_dict_and_object(self):
        d = {"referral_code": "D123", "platform": "Web"}
        obj = ReferralRecord(referral_code="O123", url="https://claude.ai/referral/O123", platform="Web",
                             source_url="https://example.com", discovered_at="2026-10-06")
        self.assertEqual(_record_val(d, "referral_code"), "D123")
        self.assertEqual(_record_val(obj, "referral_code"), "O123")
        self.assertEqual(_record_val(d, "missing", "default"), "default")
        self.assertEqual(_record_val(obj, "missing", "default"), "default")

    def test_handle_update_latest_command(self):
        with patch.object(self.bot, "send_message", return_value=True) as mock_send:
            for text in ("/latest", "/latest@suri8bot", "latest", "⚡ Latest Links", "⚡ latest"):
                with self.subTest(text=text):
                    handled = self.bot.handle_update({
                        "update_id": 100,
                        "message": {"chat": {"id": 12345}, "text": text}
                    })
                    self.assertTrue(handled)
                    mock_send.assert_called()
                    args, kwargs = mock_send.call_args
                    chat_id, sent_text = args[0], args[1]
                    self.assertEqual(chat_id, "12345")
                    self.assertIn("CodeAlpha123", sent_text)
                    self.assertIn("CodeBeta456", sent_text)
                    self.assertIn("https://claude.ai/referral/CodeAlpha123", sent_text)

    def test_handle_update_status_command(self):
        with patch.object(self.bot, "send_message", return_value=True) as mock_send:
            handled = self.bot.handle_update({
                "update_id": 101,
                "message": {"chat": {"id": 12345}, "text": "/status"}
            })
            self.assertTrue(handled)
            args, _ = mock_send.call_args
            self.assertIn("Quarry Harvester Status", args[1])
            self.assertIn("Unique Codes:", args[1])

    def test_handle_update_start_command(self):
        with patch.object(self.bot, "send_message", return_value=True) as mock_send:
            handled = self.bot.handle_update({
                "update_id": 102,
                "message": {"chat": {"id": 12345}, "text": "/start"}
            })
            self.assertTrue(handled)
            args, _ = mock_send.call_args
            self.assertIn("Welcome to Quarry", args[1])

    def test_handle_update_empty_database(self):
        empty_bot = TelegramBotService(token="fake", storage=MockStorage([]))
        with patch.object(empty_bot, "send_message", return_value=True) as mock_send:
            handled = empty_bot.handle_update({
                "update_id": 103,
                "message": {"chat": {"id": 12345}, "text": "/latest"}
            })
            self.assertTrue(handled)
            args, _ = mock_send.call_args
            self.assertIn("No referral links recorded", args[1])

    def test_telegram_webhook_route_in_web_handler(self):
        from quarry.web import QuarryHandler
        payload = json.dumps({"update_id": 104, "message": {"chat": {"id": 12345}, "text": "/latest"}}).encode('utf-8')
        mock_rfile = io.BytesIO(payload)
        mock_wfile = io.BytesIO()

        handler = QuarryHandler.__new__(QuarryHandler)
        handler.rfile = mock_rfile
        handler.wfile = mock_wfile
        handler.path = "/api/telegram"
        handler.command = "POST"
        handler.requestline = "POST /api/telegram HTTP/1.1"
        handler.request_version = "HTTP/1.1"
        handler.headers = {"Content-Length": str(len(payload))}
        handler.server = Mock()

        with patch.object(TelegramBotService, "send_message", return_value=True):
            handler._dispatch()

        response_bytes = mock_wfile.getvalue()
        self.assertIn(b"200 OK", response_bytes)
        self.assertIn(b'"ok": true', response_bytes.lower())


if __name__ == "__main__":
    unittest.main()
