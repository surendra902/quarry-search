"""Local SQLite persistence, or an explicitly read-only deployment snapshot."""
import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from quarry.models import ReferralRecord, utc_now

FIELDS = tuple(f.name for f in fields(ReferralRecord))


def normalized_time(value):
    if not value:
        return None
    try:
        if isinstance(value, (int, float)) or str(value).replace('.', '', 1).isdigit():
            dt = datetime.fromtimestamp(float(value), timezone.utc)
        else:
            dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            if dt.tzinfo is None:
                return None  # Do not invent a timezone.
        return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def evidence_order(row):
    quality = {'direct_match': 0, 'archive_match': 1, 'candidate_only': 2, 'legacy_unverified': 3}
    date = normalized_time(row.get('published_at'))
    return (quality.get(row.get('evidence_kind'), 3), date is None, date or '', row.get('source_url') or '')


class QuarryStorage:
    def __init__(self, db_path=None):
        self.mode = 'deployment_snapshot' if os.environ.get('VERCEL') and db_path is None else 'local_persistent'
        self.writable = self.mode == 'local_persistent'
        self.persistent = self.writable
        self.snapshot = {'records': []}
        root = Path(__file__).resolve().parent.parent
        if not self.writable:
            path = Path(os.environ.get('QUARRY_SNAPSHOT_PATH', str(root / 'data' / 'snapshot.json')))
            if path.exists():
                self.snapshot = json.loads(path.read_text(encoding='utf-8'))
            self.db_path = None
            return
        self.db_path = str(db_path or os.environ.get('QUARRY_DB_PATH') or root / 'quarry.db')
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('''CREATE TABLE IF NOT EXISTS referral_links (
                referral_code TEXT PRIMARY KEY, url TEXT NOT NULL, platform TEXT NOT NULL,
                source_url TEXT NOT NULL, author TEXT, published_at TEXT, discovered_at TEXT NOT NULL,
                evidence_snippet TEXT, status TEXT DEFAULT 'unknown')''')
            conn.execute('''CREATE TABLE IF NOT EXISTS occurrences (
                referral_code TEXT NOT NULL, url TEXT NOT NULL, platform TEXT NOT NULL,
                source_url TEXT NOT NULL, author TEXT, published_at TEXT, discovered_at TEXT NOT NULL,
                evidence_snippet TEXT, status TEXT NOT NULL DEFAULT 'unknown',
                evidence_kind TEXT NOT NULL DEFAULT 'legacy_unverified', source_updated_at TEXT,
                timestamp_basis TEXT, last_seen_at TEXT NOT NULL,
                PRIMARY KEY (referral_code, source_url))''')
            conn.execute('''INSERT OR IGNORE INTO occurrences
                (referral_code,url,platform,source_url,author,published_at,discovered_at,evidence_snippet,status,last_seen_at)
                SELECT referral_code,url,platform,source_url,author,published_at,discovered_at,evidence_snippet,
                COALESCE(status,'unknown'),discovered_at FROM referral_links''')
            conn.execute('CREATE INDEX IF NOT EXISTS occurrence_code ON occurrences(referral_code)')
            conn.execute('CREATE TABLE IF NOT EXISTS runtime_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')

    def seed_from_snapshot(self, path=None):
        if not self.writable:
            return 0
        with self._get_conn() as conn:
            occ_count = conn.execute('SELECT COUNT(*) FROM occurrences').fetchone()[0]
            if occ_count > 0:
                return 0
            root = Path(__file__).resolve().parent.parent
            snap_path = Path(path or os.environ.get('QUARRY_SNAPSHOT_PATH', str(root / 'data' / 'snapshot.json')))
            if not snap_path.exists():
                return 0
            try:
                snap_data = json.loads(snap_path.read_text(encoding='utf-8'))
                inserted = 0
                for r in snap_data.get('records', []):
                    conn.execute('''INSERT OR IGNORE INTO occurrences
                        (referral_code,url,platform,source_url,author,published_at,discovered_at,evidence_snippet,status,evidence_kind,source_updated_at,timestamp_basis,last_seen_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (r.get('referral_code'), r.get('url'), r.get('platform'), r.get('source_url'),
                         r.get('author'), r.get('published_at'), r.get('discovered_at'), r.get('evidence_snippet'),
                         r.get('status', 'unknown'), r.get('evidence_kind', 'direct_match'),
                         r.get('source_updated_at'), r.get('timestamp_basis'), r.get('last_seen_at') or utc_now()))
                    conn.execute('''INSERT OR IGNORE INTO referral_links
                        (referral_code,url,platform,source_url,author,published_at,discovered_at,evidence_snippet,status)
                        VALUES (?,?,?,?,?,?,?,?,?)''',
                        (r.get('referral_code'), r.get('url'), r.get('platform'), r.get('source_url'),
                         r.get('author'), r.get('published_at'), r.get('discovered_at'), r.get('evidence_snippet'),
                         r.get('status', 'unknown')))
                    inserted += 1
                return inserted
            except Exception:
                return 0

    def save_link(self, record):
        if not self.writable:
            return False
        data = record.to_dict()
        if not data.get('source_url'):
            raise ValueError('A source URL is required for an occurrence.')
        data['published_at'] = normalized_time(data.get('published_at'))
        data['source_updated_at'] = normalized_time(data.get('source_updated_at'))
        data['discovered_at'] = normalized_time(data.get('discovered_at')) or utc_now()
        data['status'] = data.get('status') or 'unknown'
        with self._get_conn() as conn:
            basic = FIELDS[:9]
            cur = conn.execute('INSERT OR IGNORE INTO referral_links (' + ','.join(basic) + ') VALUES (' + ','.join('?' for _ in basic) + ')', tuple(data[k] for k in basic))
            is_new = cur.rowcount == 1
            # Never downgrade existing verified source evidence to a snippet/legacy claim.
            old = conn.execute('SELECT * FROM occurrences WHERE referral_code=? AND source_url=?', (data['referral_code'], data['source_url'])).fetchone()
            if old and evidence_order(dict(old))[0] < evidence_order(data)[0]:
                conn.execute('UPDATE occurrences SET last_seen_at=? WHERE referral_code=? AND source_url=?', (utc_now(), data['referral_code'], data['source_url']))
                return is_new
            if old:
                data['discovered_at'] = old['discovered_at']
            columns = FIELDS + ('last_seen_at',)
            values = tuple(data[k] for k in FIELDS) + (utc_now(),)
            conn.execute('INSERT OR REPLACE INTO occurrences (' + ','.join(columns) + ') VALUES (' + ','.join('?' for _ in columns) + ')', values)
            return is_new

    def all_occurrences(self):
        if not self.writable:
            return [dict(row) for row in self.snapshot.get('records', [])]
        with self._get_conn() as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM occurrences')]

    def get_occurrences(self, code):
        if not self.writable:
            rows = [row for row in self.all_occurrences() if row.get('referral_code') == code]
        else:
            with self._get_conn() as conn:
                rows = [dict(row) for row in conn.execute('SELECT * FROM occurrences WHERE referral_code=?', (code,))]
        return sorted(rows, key=evidence_order)

    def get_by_code(self, code):
        rows = self.get_occurrences(code)
        return rows[0] if rows else None

    def list_links(self, limit=100, offset=0):
        grouped = {}
        for row in self.all_occurrences():
            grouped.setdefault(row['referral_code'], []).append(row)
        rows = []
        for occurrences in grouped.values():
            row = min(occurrences, key=evidence_order).copy()
            row['occurrence_count'] = len(occurrences)
            rows.append(row)
        rows.sort(key=lambda r: (normalized_time(r.get('discovered_at')) or '', r['referral_code']), reverse=True)
        return rows[offset:offset + limit]

    def count(self):
        if not self.writable:
            return len({r['referral_code'] for r in self.all_occurrences()})
        with self._get_conn() as conn:
            return conn.execute('SELECT COUNT(DISTINCT referral_code) FROM occurrences').fetchone()[0]

    def occurrence_count(self):
        if not self.writable:
            return len(self.all_occurrences())
        with self._get_conn() as conn:
            return conn.execute('SELECT COUNT(*) FROM occurrences').fetchone()[0]

    def invalidate_source(self, source_url):
        if self.writable:
            with self._get_conn() as conn:
                conn.execute("UPDATE occurrences SET evidence_kind='removed', evidence_snippet=NULL, author=NULL, last_seen_at=? WHERE source_url=?", (utc_now(), source_url))

    def set_state(self, key, value):
        if self.writable:
            with self._get_conn() as conn:
                conn.execute('INSERT OR REPLACE INTO runtime_state(key,value) VALUES (?,?)', (key, json.dumps(value)))

    def get_state(self, key, default=None):
        if not self.writable:
            return default
        with self._get_conn() as conn:
            row = conn.execute('SELECT value FROM runtime_state WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def export_snapshot(self, path):
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        collector_state = self.get_state('collector', {
            'status': 'Active (24/7 Cloud)',
            'configured': True,
            'last_heartbeat': utc_now(),
            'schedule': 'GitHub Actions Cloud Harvester (Every 20m) + Daemon',
            'interval_minutes': 20
        })
        payload = {
            'generated_at': utc_now(),
            'collector': collector_state,
            'notifications': 'telegram_configured' if os.environ.get('TELEGRAM_BOT_TOKEN') else 'not_configured',
            'records': self.all_occurrences()
        }
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        return payload
