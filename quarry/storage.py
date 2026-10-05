import sqlite3
import os
from typing import Optional, List, Dict
from datetime import datetime
from quarry.models import ReferralRecord

class QuarryStorage:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            if os.environ.get("VERCEL"):
                import shutil
                db_path = "/tmp/quarry.db"
                seed_db = os.path.join(os.path.dirname(os.path.dirname(__file__)), "quarry.db")
                if not os.path.exists(db_path) and os.path.exists(seed_db):
                    shutil.copyfile(seed_db, db_path)
            else:
                base_dir = os.path.dirname(os.path.dirname(__file__))
                db_path = os.path.join(base_dir, "quarry.db")
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS referral_links (
                    referral_code TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    author TEXT,
                    published_at TEXT,
                    discovered_at TEXT NOT NULL,
                    evidence_snippet TEXT,
                    status TEXT DEFAULT 'unknown'
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_platform ON referral_links(platform)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_discovered ON referral_links(discovered_at)
            """)
            conn.commit()

    def save_link(self, record: ReferralRecord) -> bool:
        """Saves a referral record. Returns True if inserted, False if already exists (deduplicated)."""
        data = record.to_dict()
        with self._get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO referral_links (
                        referral_code, url, platform, source_url, author, 
                        published_at, discovered_at, evidence_snippet, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    data["referral_code"],
                    data["url"],
                    data["platform"],
                    data["source_url"],
                    data.get("author"),
                    data.get("published_at"),
                    data.get("discovered_at") or datetime.utcnow().isoformat() + "Z",
                    data.get("evidence_snippet"),
                    data.get("status", "unknown")
                ))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                # Link already exists; keep original first-seen record
                return False

    def get_by_code(self, referral_code: str) -> Optional[Dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM referral_links WHERE referral_code = ?", (referral_code,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def list_links(self, limit: int = 100) -> List[Dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM referral_links ORDER BY discovered_at DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def count(self) -> int:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM referral_links")
            return cursor.fetchone()[0]
