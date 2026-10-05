"""Serve the same free-source demo dashboard/API as Vercel."""
import os
import sys
from http.server import ThreadingHTTPServer
from quarry.web import QuarryHandler


def run_server(port=8080, host=None):
    host = host or os.environ.get('HOST', '127.0.0.1')
    server = ThreadingHTTPServer((host, port), QuarryHandler)
    print(f'Quarry demo: http://{host}:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    run_server(int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get('PORT', '8080')))
