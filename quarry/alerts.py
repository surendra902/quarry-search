"""Alert dispatcher for newly discovered Claude referral passes."""
import html
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
import requests

from quarry.models import ReferralRecord, utc_now

logger = logging.getLogger("quarry.alerts")


class AlertDispatcher:
    def __init__(
        self,
        telegram_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        discord_webhook_url: Optional[str] = None,
        log_file: Optional[str] = None,
        storage: Optional[Any] = None
    ):
        self.telegram_token = telegram_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = telegram_chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        self.discord_webhook = discord_webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
        self.log_file = Path(log_file or os.environ.get("QUARRY_ALERT_LOG", "data/alerts.log"))
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.storage = storage

    def is_configured(self) -> bool:
        return bool((self.telegram_token and self.telegram_chat_id) or self.discord_webhook)

    def get_recipient_chat_ids(self) -> list:
        recipients = set()
        if self.telegram_chat_id:
            for cid in str(self.telegram_chat_id).split(","):
                cid = cid.strip()
                if cid:
                    recipients.add(cid)
        if self.storage and hasattr(self.storage, "get_state"):
            subs = self.storage.get_state("telegram_subscribers", [])
            for s in subs:
                recipients.add(str(s).strip())
        return list(recipients)

    def format_telegram_message(self, record: ReferralRecord) -> str:
        code = html.escape(record.referral_code)
        url = html.escape(record.url)
        platform = html.escape(record.platform or "Web")
        source_url = html.escape(record.source_url or "Unknown")
        author = html.escape(record.author or "Anonymous")
        time_str = html.escape(record.published_at or record.discovered_at or "Just now")
        snippet = html.escape((record.evidence_snippet or "")[:250])

        return (
            f"🚨 <b>NEW CLAUDE REFERRAL PASS DETECTED!</b>\n\n"
            f"🔗 <b>Claim Link:</b> {url}\n"
            f"🏷️ <b>Code:</b> <code>{code}</code>\n"
            f"🌐 <b>Platform:</b> {platform}\n"
            f"📌 <b>Source:</b> <a href=\"{source_url}\">{source_url[:60]}...</a>\n"
            f"👤 <b>Author:</b> {author}\n"
            f"⏱️ <b>Published:</b> {time_str}\n\n"
            f"💬 <b>Snippet:</b>\n<i>{snippet}</i>\n\n"
            f"⚡ <i>Discovered by Quarry 24/7 Harvester</i>"
        )

    def send_telegram(self, message: str) -> bool:
        if not self.telegram_token:
            return False
        chat_ids = self.get_recipient_chat_ids()
        if not chat_ids:
            return False

        any_success = False
        api_url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        for cid in chat_ids:
            try:
                payload = {
                    "chat_id": cid,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False
                }
                resp = requests.post(api_url, json=payload, timeout=8)
                if resp.status_code == 200:
                    any_success = True
            except Exception as exc:
                logger.error(f"Telegram alert error for chat {cid}: {exc}")
        return any_success

    def send_discord(self, record: ReferralRecord) -> bool:
        if not self.discord_webhook:
            return False
        try:
            payload = {
                "content": f"🚨 **New Claude Referral Pass Detected!**\n<{record.url}>",
                "embeds": [{
                    "title": f"Claude Referral: {record.referral_code}",
                    "url": record.url,
                    "color": 3878655,  # #3b82f6
                    "fields": [
                        {"name": "Platform", "value": record.platform or "Web", "inline": True},
                        {"name": "Author", "value": record.author or "Unknown", "inline": True},
                        {"name": "Published", "value": record.published_at or "Unknown", "inline": True},
                        {"name": "Source URL", "value": record.source_url or "N/A", "inline": False},
                        {"name": "Evidence Snippet", "value": (record.evidence_snippet or "")[:300], "inline": False}
                    ],
                    "footer": {"text": "Quarry 24/7 Harvester"}
                }]
            }
            resp = requests.post(self.discord_webhook, json=payload, timeout=8)
            return resp.status_code in (200, 204)
        except Exception as exc:
            logger.error(f"Discord alert error: {exc}")
            return False

    def log_alert(self, record: ReferralRecord):
        entry = {
            "timestamp": utc_now(),
            "referral_code": record.referral_code,
            "url": record.url,
            "platform": record.platform,
            "source_url": record.source_url,
            "author": record.author,
            "published_at": record.published_at
        }
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def dispatch(self, record: ReferralRecord) -> Dict[str, Any]:
        """Dispatch new referral pass alert across all configured channels."""
        results = {"logged": False, "telegram": False, "discord": False}
        self.log_alert(record)
        results["logged"] = True

        msg = self.format_telegram_message(record)
        if self.telegram_token and self.telegram_chat_id:
            results["telegram"] = self.send_telegram(msg)
        if self.discord_webhook:
            results["discord"] = self.send_discord(record)

        return results
