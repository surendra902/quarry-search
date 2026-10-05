import argparse
import json
import sys
from quarry.engine import QuarryEngine
from quarry.storage import QuarryStorage

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    parser = argparse.ArgumentParser(description='Bounded source discovery; results may be historical.')
    parser.add_argument('--db')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--export-snapshot')
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error('--limit must be 1..100')
    store = QuarryStorage(args.db)
    result = QuarryEngine(store).discover(args.limit)
    if args.export_snapshot:
        store.export_snapshot(args.export_snapshot)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
