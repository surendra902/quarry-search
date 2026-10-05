"""Test utility to verify Telegram Bot alerts to private inbox or group."""
import argparse
import os
import sys

from dotenv import load_dotenv
load_dotenv()

from quarry.alerts import AlertDispatcher
from quarry.models import ReferralRecord, utc_now

def main():
    parser = argparse.ArgumentParser(description="Test Telegram alert delivery")
    parser.add_argument("--token", help="Telegram Bot Token (default: env TELEGRAM_BOT_TOKEN)")
    parser.add_argument("--chat_id", help="Telegram Chat ID or Group ID (default: env TELEGRAM_CHAT_ID)")
    args = parser.parse_args()

    token = args.token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = args.chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("❌ Error: Missing Telegram credentials.")
        print("Please provide --token and --chat_id or set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        print("\nQuick setup:")
        print("1. Message @BotFather on Telegram to create a bot and get your BOT_TOKEN.")
        print("2. For Direct Inbox: Message @userinfobot to get your personal numeric Chat ID.")
        print("   For Group Inbox: Add your bot to your group and use the group Chat ID (starts with -100).")
        print("3. Run: python scripts/test_telegram_alert.py --token <YOUR_TOKEN> --chat_id <YOUR_CHAT_ID>")
        sys.exit(1)

    print(f"📡 Testing Telegram alert with Bot Token: {token[:8]}... and Chat ID: {chat_id}")
    dispatcher = AlertDispatcher(telegram_token=token, telegram_chat_id=chat_id)

    sample_record = ReferralRecord(
        referral_code="TEST_PASS_99",
        url="https://claude.ai/referral/TEST_PASS_99",
        platform="Quarry 24/7 Harvester (Test)",
        source_url="https://claude.ai/referral/TEST_PASS_99",
        author="Quarry Engine",
        published_at=utc_now(),
        evidence_snippet="This is a test alert confirming your Telegram integration is 100% active and receiving live alerts."
    )

    msg = dispatcher.format_telegram_message(sample_record)
    success = dispatcher.send_telegram(msg)

    if success:
        print("🎉 SUCCESS! Test alert message successfully delivered to your Telegram!")
    else:
        print("❌ FAILED to send alert. Please verify your bot token, chat ID, and ensure you have pressed /start with the bot.")
        sys.exit(1)

if __name__ == "__main__":
    main()
