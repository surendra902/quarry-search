"""Periodic free-web harvesting, with an explicit non-notifying verification mode."""
import logging
import os
import time
from dataclasses import fields
from quarry.engine import QuarryEngine
from quarry.storage import QuarryStorage
from quarry.alerts import AlertDispatcher
from quarry.models import ReferralRecord, utc_now

logger = logging.getLogger('quarry.harvester')


class QuietAlerts:
    def is_configured(self):
        return False
    def dispatch(self, record):
        return {'logged': False, 'telegram': False, 'discord': False, 'suppressed': True}


class ContinuousHarvester:
    def __init__(self, storage=None, alerts=None, interval_seconds=1200, export_snapshot=None,
                 notifications_enabled=True, auto_push=False):
        self.storage = storage if storage is not None else QuarryStorage()
        self.notifications_enabled = notifications_enabled
        self.alerts = (alerts if alerts is not None else AlertDispatcher(storage=self.storage)) if notifications_enabled else QuietAlerts()
        self.interval = max(10, interval_seconds)
        self.export_path = export_snapshot
        self.auto_push = auto_push
        self.running = False
        self.cycle_count = 0
        self.total_new_found = 0
        self.telegram_bot = None
        if notifications_enabled and os.environ.get('TELEGRAM_BOT_TOKEN'):
            from quarry.telegram_bot import TelegramBotService
            self.telegram_bot = TelegramBotService(storage=self.storage)
        self.engine = QuarryEngine(storage=self.storage)
        logger.info('Harvester sources: %s', [source.name for source in self.engine.sources])

    def update_heartbeat(self, status='running'):
        self.storage.set_state('collector', {
            'status': status, 'configured': True, 'last_heartbeat': utc_now(),
            'mode': 'continuous' if self.running else 'scheduled' if os.environ.get('GITHUB_EVENT_NAME') == 'schedule' else 'manual_workflow' if os.environ.get('GITHUB_ACTIONS') == 'true' else 'single_run',
            'cycles_completed': self.cycle_count, 'new_links_session': self.total_new_found,
            'total_links_in_db': self.storage.count(), 'total_occurrences': self.storage.occurrence_count(),
            'interval_seconds': self.interval, 'alerts_configured': self.alerts.is_configured(),
            'daily_yield': self.storage.yield_summary()})

    def sync_to_git(self):
        if not self.export_path:
            return False
        try:
            import subprocess
            from pathlib import Path
            root = Path(__file__).resolve().parent.parent
            snap_file = Path(self.export_path)
            if not snap_file.is_absolute():
                snap_file = root / snap_file

            check = subprocess.run(
                ["git", "status", "--porcelain", str(snap_file)],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=10
            )
            if not check.stdout.strip():
                logger.info("Snapshot unchanged; git push not required.")
                return False

            subprocess.run(
                ["git", "pull", "--rebase", "origin", "master"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=25
            )
            subprocess.run(
                ["git", "add", str(snap_file)],
                cwd=str(root),
                check=True,
                timeout=10
            )
            msg = f"chore(data): auto-update snapshot (every 20 min) [skip ci]"
            commit_res = subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=15
            )
            if commit_res.returncode != 0:
                logger.info("Git commit returned %s: %s", commit_res.returncode, commit_res.stderr.strip())
                return False

            push_res = subprocess.run(
                ["git", "push", "origin", "master"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=35
            )
            if push_res.returncode == 0:
                logger.info("Successfully pushed updated snapshot to GitHub master. Vercel deployment triggered.")
                return True
            else:
                logger.error("Git push failed: %s", push_res.stderr.strip())
                return False
        except Exception as exc:
            logger.error("Git sync error: %s", exc)
            return False

    def harvest_cycle(self):
        self.cycle_count += 1
        result = self.engine.discover(limit_per_source=100)
        valid_fields = {field.name for field in fields(ReferralRecord)}
        new_codes = set()
        for item in result.get('new_records', []):
            code = item.get('referral_code')
            if not code or code in new_codes:
                continue
            new_codes.add(code)
            record = ReferralRecord(**{key: value for key, value in item.items() if key in valid_fields})
            basis = (record.timestamp_basis or '').lower()
            if record.evidence_kind == 'direct_match' and not any(word in basis for word in ('archived', 'retired')):
                self.alerts.dispatch(record)
        self.total_new_found += len(new_codes)
        self.update_heartbeat('running' if self.running else 'completed')
        # Checkpoints and measurement state must survive fresh scheduled runners,
        # even when this cycle discovers no new code.
        if self.export_path:
            self.storage.export_snapshot(self.export_path)
            if self.auto_push:
                self.sync_to_git()
        logger.info('Cycle %s: %s first-observed codes; publication/validity are separate metrics.', self.cycle_count, len(new_codes))
        return len(new_codes)

    def run_forever(self):
        self.running = True
        self.update_heartbeat('running')
        try:
            while self.running:
                start = time.monotonic()
                try:
                    self.harvest_cycle()
                except Exception as exc:
                    logger.error('Cycle failed: %s', type(exc).__name__)
                    self.update_heartbeat('error')
                remaining = max(1.0, self.interval - (time.monotonic() - start))
                end = time.monotonic() + remaining
                while self.running and time.monotonic() < end:
                    if self.telegram_bot:
                        self.telegram_bot.poll_and_handle()
                    time.sleep(min(2.0, max(0.0, end - time.monotonic())))
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            self.update_heartbeat('stopped')
