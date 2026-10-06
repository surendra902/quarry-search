"""Run harvesting explicitly; --dry-run never loads .env or sends notifications."""
import argparse
import json
import logging
import os
from pathlib import Path
from quarry.harvester import ContinuousHarvester
from quarry.alerts import AlertDispatcher
from quarry.storage import QuarryStorage


def main():
    parser = argparse.ArgumentParser(description='Bounded or periodic public-web harvesting')
    parser.add_argument('--interval', type=int, default=60)
    parser.add_argument('--telegram-token')
    parser.add_argument('--telegram-chat')
    parser.add_argument('--discord-webhook')
    parser.add_argument('--oneshot', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='One isolated cycle, no .env, bot polling or notifications')
    parser.add_argument('--no-env', action='store_true')
    parser.add_argument('--db')
    parser.add_argument('--export-snapshot')
    args = parser.parse_args()
    if args.dry_run:
        os.environ['QUARRY_ENABLE_PAID_SOURCES'] = '0'
    if not args.no_env and not args.dry_run:
        env = Path(__file__).resolve().parent / '.env'
        if env.exists():
            for line in env.read_text(encoding='utf-8').splitlines():
                if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"\''))
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
    path = args.db or ('.audit/dry-run.db' if args.dry_run else os.environ.get('QUARRY_DB_PATH', 'quarry.db'))
    export = args.export_snapshot or ('.audit/dry-run-snapshot.json' if args.dry_run else 'data/snapshot.json')
    store = QuarryStorage(path)
    store.seed_from_snapshot()
    alerts = None if args.dry_run else AlertDispatcher(telegram_token=args.telegram_token,
        telegram_chat_id=args.telegram_chat, discord_webhook_url=args.discord_webhook, storage=store)
    harvester = ContinuousHarvester(store, alerts=alerts, interval_seconds=args.interval,
        export_snapshot=export, notifications_enabled=not args.dry_run)
    if args.oneshot or args.dry_run:
        count = harvester.harvest_cycle()
        print(json.dumps({'new_to_history': count, 'dry_run': args.dry_run,
                          'daily_yield': store.yield_summary(), 'sources': [source.name for source in harvester.engine.sources]}, indent=2))
    else:
        harvester.run_forever()


if __name__ == '__main__':
    main()
