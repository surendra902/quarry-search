import argparse
import json
import sys
from quarry.engine import QuarryEngine
from quarry.storage import QuarryStorage

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    parser = argparse.ArgumentParser(description='Find evidenced occurrences, not a guaranteed original post.')
    parser.add_argument('target')
    parser.add_argument('--db')
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    try:
        result = QuarryEngine(QuarryStorage(args.db)).lookup_detailed(args.target, refresh=args.refresh)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
