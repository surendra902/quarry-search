"""CLI Runner for 24/7 Continuous Referral Link Harvester."""
import argparse
import os
import sys
from pathlib import Path

# Safe UTF-8 encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Load .env file if available
env_file = Path(__file__).resolve().parent / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

from quarry.alerts import AlertDispatcher
from quarry.harvester import ContinuousHarvester
from quarry.storage import QuarryStorage


def main():
    parser = argparse.ArgumentParser(description="24/7 Continuous Claude Referral Link Harvester")
    parser.add_argument("--interval", type=int, default=int(os.environ.get("HARVESTER_INTERVAL", 60)),
                        help="Harvest interval in seconds (default: 60)")
    parser.add_argument("--telegram-token", type=str, default=os.environ.get("TELEGRAM_BOT_TOKEN"),
                        help="Telegram Bot token")
    parser.add_argument("--telegram-chat", type=str, default=os.environ.get("TELEGRAM_CHAT_ID"),
                        help="Telegram Chat ID or Group ID")
    parser.add_argument("--discord-webhook", type=str, default=os.environ.get("DISCORD_WEBHOOK_URL"),
                        help="Discord Webhook URL")
    parser.add_argument("--oneshot", action="store_true", help="Run a single harvest cycle and exit")
    parser.add_argument("--export-snapshot", type=str, default="data/snapshot.json",
                        help="Auto-export snapshot path after each cycle")
    args = parser.parse_args()

    storage = QuarryStorage("quarry.db")
    alerts = AlertDispatcher(
        telegram_token=args.telegram_token,
        telegram_chat_id=args.telegram_chat,
        discord_webhook_url=args.discord_webhook,
        storage=storage
    )

    harvester = ContinuousHarvester(
        storage=storage,
        alerts=alerts,
        interval_seconds=args.interval,
        export_snapshot=args.export_snapshot
    )

    if args.oneshot:
        new_count = harvester.harvest_cycle()
        print(f"\n[Oneshot Run Complete] Discovered {new_count} new referral links. Total in DB: {storage.count()}.")
    else:
        harvester.run_forever()


if __name__ == "__main__":
    main()
