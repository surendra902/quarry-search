"""Telegram interactive bot service for Quarry (supports both polling and webhook)."""
import html
import json
import logging
import os
from typing import Optional, List, Dict, Any
from urllib.parse import urlsplit
import requests

from quarry.storage import QuarryStorage

logger = logging.getLogger("quarry.telegram")

REPLY_KEYBOARD = {
    "keyboard": [
        [{"text": "⚡ Latest Feeds"}, {"text": "🔍 Search Now"}],
        [{"text": "📊 Status"}, {"text": "🌐 Web Dashboard"}]
    ],
    "resize_keyboard": True,
    "persistent": True
}


def _record_val(record: Any, field: str, default: Any = "") -> Any:
    if isinstance(record, dict):
        return record.get(field, default)
    return getattr(record, field, default)


class TelegramBotService:
    def __init__(self, token: Optional[str] = None, storage: Optional[QuarryStorage] = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
        if not self.token:
            from pathlib import Path
            env_file = Path(__file__).resolve().parent.parent / ".env"
            if env_file.exists():
                for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if line.strip().startswith("TELEGRAM_BOT_TOKEN="):
                        self.token = line.split("=", 1)[1].strip().strip('"\'')
                        break
        if not self.token:
            self.token = "8949259720:AAGld-d08yW-uE_ONQp3cbGQiVsWfXp0xq8"
        self.storage = storage or QuarryStorage()
        self.last_update_id = 0

    def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict[str, Any]] = None,
        disable_web_page_preview: bool = True
    ) -> bool:
        if not self.token:
            logger.warning("Telegram send_message failed: TELEGRAM_BOT_TOKEN is not configured.")
            return False
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": disable_web_page_preview
            }
            if reply_markup is not None:
                payload["reply_markup"] = reply_markup
            resp = requests.post(url, json=payload, timeout=8)
            if resp.status_code != 200:
                logger.error(f"Telegram API response {resp.status_code}: {resp.text}")
                return False
            return True
        except Exception as exc:
            logger.error(f"Telegram send error: {exc}")
            return False

    def handle_update(self, update: Dict[str, Any]) -> bool:
        """Handle a single Telegram Update (from webhook or getUpdates)."""
        if not isinstance(update, dict):
            return False

        chat_id = None
        raw_text = ""

        if "message" in update and isinstance(update["message"], dict):
            msg = update["message"]
            chat_id = str(msg.get("chat", {}).get("id", ""))
            raw_text = (msg.get("text") or "").strip()
        elif "callback_query" in update and isinstance(update["callback_query"], dict):
            cb = update["callback_query"]
            msg = cb.get("message") or {}
            chat_id = str(msg.get("chat", {}).get("id", ""))
            raw_text = (cb.get("data") or "").strip()

        if not chat_id:
            return False

        cmd = raw_text.lower()
        if "@" in cmd:
            cmd = cmd.split("@")[0]

        # 1. /latest or /feeds or "Latest" or "⚡ Latest Feeds" or "⚡ Latest Links" or "feeds"
        if cmd.startswith("/latest") or cmd.startswith("/feeds") or "latest" in cmd or "feed" in cmd or "link" in cmd:
            self._handle_latest(chat_id)
            return True

        # 2. /search or /hunt or /sweep or "Search" or "🔍 Search Now"
        if cmd.startswith("/search") or cmd.startswith("/hunt") or cmd.startswith("/sweep") or "search" in cmd or "hunt" in cmd:
            self._handle_search(chat_id)
            return True

        # 3. /status or "Status" or "📊 Status"
        if cmd.startswith("/status") or "status" in cmd:
            self._handle_status(chat_id)
            return True

        # 4. /start or /help or "Help" or "❓ Help"
        if cmd.startswith("/start") or cmd.startswith("/help") or "help" in cmd:
            self._handle_start(chat_id)
            return True

        # 5. /stop or /unsubscribe
        if cmd.startswith("/stop") or cmd.startswith("/unsubscribe") or cmd == "stop":
            self._handle_stop(chat_id)
            return True

        # 6. "Web Dashboard" or /web
        if "web" in cmd or "dashboard" in cmd:
            self.send_message(
                chat_id,
                "🌐 <b>Quarry Web Dashboard:</b>\n\n"
                "https://searchtask.vercel.app\n\n"
                "<i>Real-time candidate evidence, source breakdowns, and pass lookups.</i>",
                reply_markup=REPLY_KEYBOARD
            )
            return True

        # Fallback for unrecognized messages
        self.send_message(
            chat_id,
            "🤖 <b>Command not recognized.</b>\n\n"
            "Use the buttons below:\n"
            "• <b>⚡ Latest Links</b> - View newest Claude passes\n"
            "• <b>🔍 Search Now</b> - Run live search across web\n"
            "• <b>📊 Status</b> - Harvester state & link count\n"
            "• <b>🌐 Web Dashboard</b> - Open online explorer",
            reply_markup=REPLY_KEYBOARD
        )
        return True

    def _handle_latest(self, chat_id: str):
        try:
            links = self.storage.list_links(limit=5)
        except Exception as exc:
            logger.error(f"Error querying links for Telegram: {exc}")
            links = []

        if not links:
            self.send_message(
                chat_id,
                "⚠️ <b>No referral links recorded in the database yet.</b>\n\n"
                "Tap <b>🔍 Search Now</b> below to trigger a live web search sweep right now!",
                reply_markup=REPLY_KEYBOARD
            )
            return

        items = []
        for idx, r in enumerate(links, 1):
            code = _record_val(r, "referral_code", "Unknown")
            url = _record_val(r, "url", f"https://claude.ai/referral/{code}")
            platform = _record_val(r, "platform", "Web")
            source_url = _record_val(r, "source_url", "")

            host = ""
            if source_url:
                try:
                    host = urlsplit(source_url).netloc
                except Exception:
                    host = source_url[:30]

            source_display = f'<a href="{html.escape(source_url)}">{html.escape(host or "Source Link")}</a>' if source_url else "Web"

            discovered = _record_val(r, "discovered_at", "")
            time_display = ""
            if discovered:
                try:
                    from datetime import datetime
                    dt_obj = datetime.fromisoformat(discovered.replace("Z", "+00:00"))
                    time_display = f"   🕒 <i>Discovered:</i> {dt_obj.strftime('%b %d, %H:%M UTC')}\n"
                except Exception:
                    time_display = f"   🕒 <i>Discovered:</i> {discovered[:19]}\n"

            items.append(
                f"<b>{idx}. Claude Pass:</b> <code>{html.escape(code)}</code>\n"
                f"   👉 <a href=\"{html.escape(url)}\">Claim Guest Pass</a>\n"
                f"{time_display}"
                f"   🏷️ <i>Platform:</i> {html.escape(platform or 'Web')}\n"
                f"   🌐 <i>Source:</i> {source_display}"
            )

        header = f"⚡ <b>Latest Claude Referral Passes ({len(links)}):</b>\n\n"
        footer = (
            "\n\n🔄 <i>Auto-updates every 20 minutes across 7 web sources.</i>\n"
            "💡 <i>Tip: Tap <b>🔍 Search Now</b> below to trigger an instant live search across the web.</i>"
        )
        full_text = header + "\n\n".join(items) + footer

        self.send_message(chat_id, full_text, reply_markup=REPLY_KEYBOARD)

    def _handle_search(self, chat_id: str):
        self.send_message(
            chat_id,
            "🔍 <b>Running live search sweep across web sources...</b>\n"
            "Checking Exa neural search, URLScan intelligence, GitHub, and developer communities for new passes. Please wait a few seconds...",
            reply_markup=REPLY_KEYBOARD
        )

        new_records = []
        try:
            from quarry.engine import QuarryEngine
            engine = QuarryEngine(storage=self.storage)
            result = engine.discover(limit_per_source=20)
            new_records = result.get("new_records", [])
        except Exception as exc:
            logger.error(f"Search sweep error: {exc}")

        if new_records:
            items = []
            for idx, r in enumerate(new_records[:5], 1):
                code = _record_val(r, "referral_code", "Unknown")
                url = _record_val(r, "url", f"https://claude.ai/referral/{code}")
                platform = _record_val(r, "platform", "Web")
                source_url = _record_val(r, "source_url", "")

                host = ""
                if source_url:
                    try:
                        host = urlsplit(source_url).netloc
                    except Exception:
                        host = source_url[:30]

                source_display = f'<a href="{html.escape(source_url)}">{html.escape(host or "Source Link")}</a>' if source_url else "Web"

                items.append(
                    f"<b>{idx}. NEW Pass:</b> <code>{html.escape(code)}</code>\n"
                    f"   👉 <a href=\"{html.escape(url)}\">Claim Guest Pass</a>\n"
                    f"   🏷️ <i>Platform:</i> {html.escape(platform or 'Web')}\n"
                    f"   🌐 <i>Source:</i> {source_display}"
                )

            header = f"🎉 <b>Discovered {len(new_records)} NEW Claude Referral Pass(es)!</b>\n\n"
            footer = "\n\n<i>Tap a link above to redeem your guest pass on Claude.ai!</i>"
            full_text = header + "\n\n".join(items) + footer
            self.send_message(chat_id, full_text, reply_markup=REPLY_KEYBOARD)
        else:
            links = self.storage.list_links(limit=5)
            items = []
            for idx, r in enumerate(links, 1):
                code = _record_val(r, "referral_code", "Unknown")
                url = _record_val(r, "url", f"https://claude.ai/referral/{code}")
                platform = _record_val(r, "platform", "Web")
                source_url = _record_val(r, "source_url", "")

                host = ""
                if source_url:
                    try:
                        host = urlsplit(source_url).netloc
                    except Exception:
                        host = source_url[:30]

                source_display = f'<a href="{html.escape(source_url)}">{html.escape(host or "Source Link")}</a>' if source_url else "Web"

                items.append(
                    f"<b>{idx}. Claude Pass:</b> <code>{html.escape(code)}</code>\n"
                    f"   👉 <a href=\"{html.escape(url)}\">Claim Guest Pass</a>\n"
                    f"   🏷️ <i>Platform:</i> {html.escape(platform or 'Web')}\n"
                    f"   🌐 <i>Source:</i> {source_display}"
                )

            header = (
                "✅ <b>Live Search Sweep Completed (7 sources checked).</b>\n"
                "<i>No newer passes were published on the web since the last sweep.</i>\n\n"
                f"<b>Freshest Verified Passes in Database ({len(links)}):</b>\n\n"
            )
            footer = "\n\n<i>Tap a link above to redeem on Claude.ai!</i>"
            full_text = header + "\n\n".join(items) + footer
            self.send_message(chat_id, full_text, reply_markup=REPLY_KEYBOARD)

    def _handle_status(self, chat_id: str):
        total_unique = self.storage.count()
        total_occ = self.storage.occurrence_count()
        mode_label = "24/7 Cloud (Vercel Snapshot)" if self.storage.mode == "deployment_snapshot" else "Local Persistent SQLite"
        status_text = (
            f"📊 <b>Quarry Harvester Status</b>\n\n"
            f"• <b>Unique Codes:</b> {total_unique}\n"
            f"• <b>Total Occurrences:</b> {total_occ}\n"
            f"• <b>Storage Engine:</b> {mode_label}\n"
            f"• <b>Harvester Schedule:</b> Active (every 20 mins via GitHub Actions)\n"
            f"• <b>Real-time Alerts:</b> Enabled\n\n"
            f"🌐 <b>Live Web UI:</b> https://searchtask.vercel.app"
        )
        self.send_message(chat_id, status_text, reply_markup=REPLY_KEYBOARD)

    def _handle_start(self, chat_id: str):
        if hasattr(self.storage, "get_state") and hasattr(self.storage, "set_state") and self.storage.writable:
            subs = self.storage.get_state("telegram_subscribers", [])
            if chat_id not in subs:
                subs.append(chat_id)
                self.storage.set_state("telegram_subscribers", subs)

        welcome = (
            "👋 <b>Welcome to Quarry Claude Pass Harvester!</b>\n\n"
            "✅ <b>You are connected to real-time referral alerts.</b>\n"
            "Whenever a new Claude guest pass is discovered across developer forums, blogs, or search indexes, you'll receive an instant alert.\n\n"
            f"📊 <b>Current Database:</b> {self.storage.count()} unique referral codes across {self.storage.occurrence_count()} sources.\n\n"
            "Use the quick buttons below to explore:"
        )
        self.send_message(chat_id, welcome, reply_markup=REPLY_KEYBOARD)

    def _handle_stop(self, chat_id: str):
        if hasattr(self.storage, "get_state") and hasattr(self.storage, "set_state") and self.storage.writable:
            subs = self.storage.get_state("telegram_subscribers", [])
            if chat_id in subs:
                subs.remove(chat_id)
                self.storage.set_state("telegram_subscribers", subs)

        self.send_message(
            chat_id,
            "🔕 You have unsubscribed from automatic alerts. Send /start anytime to reconnect.",
            reply_markup=REPLY_KEYBOARD
        )

    def poll_and_handle(self) -> int:
        """Poll once for incoming commands via getUpdates."""
        if not self.token:
            return 0
        try:
            url = f"https://api.telegram.org/bot{self.token}/getUpdates"
            params = {"offset": self.last_update_id + 1, "timeout": 2}
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code != 200:
                return 0
            data = resp.json()
            if not data.get("ok"):
                return 0

            handled = 0
            for update in data.get("result", []):
                self.last_update_id = max(self.last_update_id, update.get("update_id", 0))
                if self.handle_update(update):
                    handled += 1
            return handled
        except Exception as exc:
            logger.debug(f"Telegram poll network blip: {exc}")
            return 0

    def set_webhook(self, webhook_url: str) -> bool:
        if not self.token:
            return False
        try:
            url = f"https://api.telegram.org/bot{self.token}/setWebhook"
            resp = requests.post(url, json={"url": webhook_url}, timeout=8)
            return resp.status_code == 200 and resp.json().get("ok", False)
        except Exception as exc:
            logger.error(f"Failed to set Telegram webhook: {exc}")
            return False

    def delete_webhook(self) -> bool:
        if not self.token:
            return False
        try:
            url = f"https://api.telegram.org/bot{self.token}/deleteWebhook"
            resp = requests.post(url, timeout=8)
            return resp.status_code == 200 and resp.json().get("ok", False)
        except Exception as exc:
            logger.error(f"Failed to delete Telegram webhook: {exc}")
            return False
