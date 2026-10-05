"""Shared local/Vercel HTTP surface. No import-time DB writes or network calls."""
import hmac
import json
import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from quarry.engine import QuarryEngine
from quarry.extractors import extract_code_from_url

VERSION = '2026.10.05.1'
ROOT = Path(__file__).resolve().parent.parent
_NETWORK_SLOTS = threading.BoundedSemaphore(2)
_SWEEP_LOCK = threading.Lock()
_LAST_SWEEP = 0.0


class RequestError(ValueError):
    pass


class QuarryHandler(BaseHTTPRequestHandler):
    def _send(self, status, value, content_type='application/json; charset=utf-8'):
        body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(body)

    def _engine(self):
        return getattr(self.server, 'engine', None) or QuarryEngine()

    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def _dispatch(self):
        global _LAST_SWEEP
        parsed = urlsplit(self.path)
        path = parsed.path.rstrip('/') or '/'
        params = parse_qs(parsed.query, keep_blank_values=True)
        try:
            if path in ('/', '/index.html', '/app.js') and self.command == 'GET':
                file = ROOT / 'public' / ('app.js' if path == '/app.js' else 'index.html')
                kind = 'text/javascript; charset=utf-8' if path == '/app.js' else 'text/html; charset=utf-8'
                self._send(200, file.read_bytes(), kind)
                return
            routes = {'/api/links', '/api/lookup', '/api/discover', '/api/status', '/api/health'}
            if path not in routes:
                self._send(404, {'error': 'Not found.'})
                return
            expected = 'POST' if path == '/api/discover' else 'GET'
            if self.command != expected:
                self._send(405, {'error': 'Use ' + expected + ' for this endpoint.'})
                return
            try:
                if path == '/api/lookup':
                    extract_code_from_url(params.get('q', [''])[0])
                if path == '/api/links':
                    limit = int(params.get('limit', ['100'])[0])
                    offset = int(params.get('offset', ['0'])[0])
                    if not 1 <= limit <= 500 or offset < 0:
                        raise ValueError('limit must be 1..500 and offset non-negative.')
            except (ValueError, TypeError) as exc:
                raise RequestError('Invalid request input.') from exc
            engine = self._engine()
            if path == '/api/links':
                self._send(200, engine.storage.list_links(limit, offset))
                return
            if path in ('/api/status', '/api/health'):
                store = engine.storage
                collector = store.get_state('collector', {})
                heartbeat = collector.get('last_heartbeat')
                state = collector.get('status', 'not_running')
                if heartbeat:
                    age = (datetime.now(timezone.utc) - datetime.fromisoformat(heartbeat.replace('Z', '+00:00'))).total_seconds()
                    if age > 120:
                        state = 'stale'
                self._send(200, {'version': VERSION, 'commit': os.environ.get('VERCEL_GIT_COMMIT_SHA'),
                    'storage': {'mode': store.mode, 'persistent': store.persistent, 'writable': store.writable},
                    'total_links': store.count(), 'total_occurrences': store.occurrence_count(),
                    'sources': [source.name for source in engine.sources],
                    'collector': {**collector, 'configured': False, 'last_heartbeat': heartbeat, 'status': state},
                    'validation': 'not_configured', 'notifications': 'not_configured',
                    'snapshot_generated_at': store.snapshot.get('generated_at'),
                    'last_sweep': store.get_state('last_sweep')})
                return
            if path == '/api/discover':
                origin = self.headers.get('Origin')
                if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                    self._send(403, {'error': 'Cross-origin discovery is not allowed.'})
                    return
                token = os.environ.get('QUARRY_ADMIN_TOKEN')
                if token and not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                    self._send(403, {'error': 'Operator authorization required.'})
                    return
            if not _NETWORK_SLOTS.acquire(blocking=False):
                self._send(429, {'error': 'Source checks are busy. Please retry shortly.'})
                return
            try:
                if path == '/api/lookup':
                    result = engine.lookup_detailed(params['q'][0], refresh=params.get('refresh') == ['1'])
                else:
                    with _SWEEP_LOCK:
                        now = time.monotonic()
                        if now - _LAST_SWEEP < 60:
                            self._send(429, {'error': 'Please wait before starting another sweep.'})
                            return
                        _LAST_SWEEP = now
                    result = engine.discover(limit_per_source=20)
                self._send(200, result)
            finally:
                _NETWORK_SLOTS.release()
        except RequestError:
            self._send(400, {'error': 'Invalid request. Use a complete claude.ai/referral URL or an unmodified code; check numeric limits.'})
        except Exception:
            # Do not expose tokens, database paths or stack traces in public responses.
            self._send(503, {'error': 'The service could not complete this request. Please retry.'})

    def log_message(self, format, *args):
        pass
