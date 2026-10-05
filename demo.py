"""Compatibility entrypoint for the real dashboard; no canned audit conclusions."""
import argparse
import json
from quarry.storage import QuarryStorage
from demo_server import run_server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--auto', '--all', action='store_true')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    if args.auto:
        store = QuarryStorage()
        print(json.dumps({'storage_mode': store.mode, 'total_links': store.count(),
                          'records': store.list_links(), 'note': 'Stored evidence does not establish redeemability or global origin.'}, indent=2))
    else:
        run_server(args.port)


if __name__ == '__main__':
    main()
