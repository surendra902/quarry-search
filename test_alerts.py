"""Test alert dispatching to Telegram and Discord."""
import argparse
import os
import sys
from pathlib import Path

# Safe UTF-8 encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Load .env
env_file = Path(__file__).resolve().parent / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

from quarry.alerts import AlertDispatcher
from quarry.models import ReferralRecord, utc_now


def main():
    parser = argparse.ArgumentParser(description="Test Alert Dispatcher")
    parser.add_argument("--telegram-token", type=str, default=os.environ.get("TELEGRAM_BOT_TOKEN"))
    parser.add_argument("--telegram-chat", type=str, default=os.environ.get("TELEGRAM_CHAT_ID"))
    parser.add_argument("--discord-webhook", type=str, default=os.environ.get("DISCORD_WEBHOOK_URL"))
    args = parser.parse_args()

    dispatcher = AlertDispatcher(
        telegram_token=args.telegram_token,
        telegram_chat_id=args.telegram_chat,
        discord_webhook_url=args.discord_webhook
    )

    sample = ReferralRecord(
        referral_code="TEST-PASS-2026",
        url="https://claude.ai/referral/TEST-PASS-2026",
        platform="Web (Exa Neural Deep Search)",
        author="Quarry Harvester",
        published_at=utc_now(),
        discovered_at=utc_now(),
        source_url="https://help.apiyi.com/en/claude-code-guest-pass-free-week-en.html",
        evidence_snippet="Claude Code guest pass referral link: https://claude.ai/referral/TEST-PASS-2026 (1-week free trial access)",
        status="test"
    )

    print("=" * 60)
    print("QUARRY HARVESTER ALERT TEST")
    print("=" * 60)
    print(f"Telegram Configured: {bool(args.telegram_token and args.telegram_chat)}")
    print(f"Discord Configured:  {bool(args.discord_webhook)}")
    print("-" * 60)

    if args.telegram_token and args.telegram_chat:
        msg = dispatcher.format_telegram_message(sample)
        print("Sending Telegram message...")
        ok = dispatcher.send_telegram(msg)
        if ok:
            print("[SUCCESS] Telegram alert successfully delivered to chat:", args.telegram_chat)
        else:
            print("[FAILED] Telegram alert failed to send. Check bot token and chat permissions.")
    else:
        print("[SKIP] Telegram chat ID not provided. Set TELEGRAM_CHAT_ID in .env or pass --telegram-chat.")

    if args.discord_webhook:
        print("Sending Discord webhook...")
        ok = dispatcher.send_discord(sample)
        if ok:
            print("[SUCCESS] Discord webhook delivered.")
        else:
            print("[FAILED] Discord webhook failed.")

    print("=" * 60)


if __name__ == "__main__":
    main()
