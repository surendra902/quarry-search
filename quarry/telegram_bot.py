"""Telegram interactive polling bot for Quarry."""
import html
import logging
import os
from typing import Optional
import requests

from quarry.storage import QuarryStorage

logger = logging.getLogger("quarry.telegram")


class TelegramBotService:
    def __init__(self, token: Optional[str] = None, storage: Optional[QuarryStorage] = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.storage = storage or QuarryStorage()
        self.last_update_id = 0

    def send_message(self, chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
        if not self.token:
            return False
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            resp = requests.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }, timeout=8)
            return resp.status_code == 200
        except Exception as exc:
            logger.error(f"Telegram send error: {exc}")
            return False

    def poll_and_handle(self) -> int:
        """Poll once for incoming commands and handle them. Returns number of handled messages."""
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
                self.last_update_id = max(self.last_update_id, update["update_id"])
                msg = update.get("message")
                if not msg:
                    continue
                chat_id = str(msg["chat"]["id"])
                text = (msg.get("text") or "").strip()

                if text.startswith("/start"):
                    welcome = (
                        "👋 <b>Welcome to Quarry Harvester Bot!</b>\n\n"
                        "This bot sends instant alerts whenever a new Claude referral guest pass is discovered.\n\n"
                        f"📊 <b>Current Database:</b> {self.storage.count()} unique referral codes across {self.storage.occurrence_count()} sources.\n\n"
                        "Commands:\n"
                        "/status - View harvester status\n"
                        "/latest - View 3 most recent links\n"
                        "/help - Show command list"
                    )
                    self.send_message(chat_id, welcome)
                    handled += 1
                elif text.startswith("/status"):
                    status_text = (
                        f"📊 <b>Quarry Harvester Status</b>\n\n"
                        f"• Unique Codes: <b>{self.storage.count()}</b>\n"
                        f"• Total Occurrences: <b>{self.storage.occurrence_count()}</b>\n"
                        f"• Storage Engine: <b>SQLite ({self.storage.db_path})</b>\n"
                        f"• Harvester State: <b>Online</b>\n\n"
                        f"<i>Live Web UI: https://searchtask.vercel.app</i>"
                    )
                    self.send_message(chat_id, status_text)
                    handled += 1
                elif text.startswith("/latest"):
                    recent = self.storage.all_occurrences()[:3]
                    if not recent:
                        self.send_message(chat_id, "No links in database yet.")
                    else:
                        items = []
                        for r in recent:
                            items.append(
                                f"🔗 <b>Code:</b> <code>{html.escape(r.referral_code)}</code>\n"
                                f"   <b>URL:</b> {r.url}\n"
                                f"   <b>Platform:</b> {html.escape(r.platform or 'Web')}\n"
                                f"   <b>Source:</b> <a href=\"{r.source_url}\">{html.escape(r.source_url[:50])}...</a>"
                            )
                        msg_text = "<b>Latest Discovered Referral Links:</b>\n\n" + "\n\n".join(items)
                        self.send_message(chat_id, msg_text)
                    handled += 1
            return handled
        except Exception as exc:
            logger.error(f"Telegram poll error: {exc}")
            return 0
