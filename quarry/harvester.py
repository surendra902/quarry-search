"""Continuous 24/7 Harvester for newly published Claude referral passes."""
import logging
import os
import sys
import time
from typing import Optional

from quarry.engine import QuarryEngine
from quarry.storage import QuarryStorage
from quarry.alerts import AlertDispatcher
from quarry.models import ReferralRecord, utc_now
from quarry.sources.github_source import GitHubSource
from quarry.sources.hackernews_source import HackerNewsSource
from quarry.sources.web_directory_source import WebDirectorySource

try:
    from quarry.sources.exa_source import ExaSource
except ImportError:
    ExaSource = None

try:
    from quarry.sources.tavily_source import TavilySource
except ImportError:
    TavilySource = None

try:
    from quarry.sources.apify_source import ApifySource
except ImportError:
    ApifySource = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("quarry.harvester")


class ContinuousHarvester:
    def __init__(
        self,
        storage: Optional[QuarryStorage] = None,
        alerts: Optional[AlertDispatcher] = None,
        interval_seconds: int = 60,
        export_snapshot: Optional[str] = None
    ):
        self.storage = storage or QuarryStorage()
        self.alerts = alerts or AlertDispatcher()
        self.interval = max(10, interval_seconds)
        self.export_path = export_snapshot
        self.running = False
        self.cycle_count = 0
        self.total_new_found = 0

        # Build comprehensive source list
        sources = [
            GitHubSource(token=os.environ.get("GITHUB_TOKEN")),
            HackerNewsSource(),
            WebDirectorySource()
        ]
        if ExaSource and os.environ.get("EXA_API_KEY"):
            sources.append(ExaSource(api_key=os.environ.get("EXA_API_KEY")))
        if TavilySource and os.environ.get("TAVILY_API_KEY"):
            sources.append(TavilySource(api_key=os.environ.get("TAVILY_API_KEY")))
        if ApifySource and os.environ.get("APIFY_API_TOKEN"):
            sources.append(ApifySource(api_token=os.environ.get("APIFY_API_TOKEN")))

        self.engine = QuarryEngine(storage=self.storage, sources=sources)
        logger.info(f"Initialized Harvester with {len(sources)} sources: {[s.name for s in sources]}")

    def update_heartbeat(self, status: str = "running"):
        state = {
            "status": status,
            "configured": True,
            "last_heartbeat": utc_now(),
            "cycles_completed": self.cycle_count,
            "new_links_session": self.total_new_found,
            "total_links_in_db": self.storage.count(),
            "total_occurrences": self.storage.occurrence_count(),
            "interval_seconds": self.interval,
            "alerts_configured": self.alerts.is_configured()
        }
        self.storage.set_state("collector", state)

    def harvest_cycle(self) -> int:
        """Run a single harvesting cycle across all configured sources."""
        self.cycle_count += 1
        logger.info(f"--- Starting Harvest Cycle #{self.cycle_count} ---")

        # Get existing codes set before sweep
        existing_codes = {r["referral_code"] for r in self.storage.all_occurrences()}
        discovered_new = 0

        result = self.engine.discover(limit_per_source=30)
        candidates = result.get("candidate_records", []) + result.get("new_records", [])

        valid_fields = {
            "referral_code", "url", "platform", "source_url", "author",
            "published_at", "discovered_at", "evidence_snippet", "status",
            "evidence_kind", "source_updated_at", "timestamp_basis"
        }

        for item in candidates:
            if isinstance(item, dict):
                code = item.get("referral_code")
                clean = {k: v for k, v in item.items() if k in valid_fields}
                record = ReferralRecord(**clean)
            else:
                code = item.referral_code
                record = item

            if code and code not in existing_codes:
                discovered_new += 1
                self.total_new_found += 1
                existing_codes.add(code)

                # Save to database
                self.storage.save_link(record)

                # Send instant alert
                logger.info(f"🎉 NEW LINK DETECTED: {code} from {record.platform} ({record.source_url})")
                alert_res = self.alerts.dispatch(record)
                if alert_res.get("telegram"):
                    logger.info(f"✅ Telegram alert sent for {code}")
                if alert_res.get("discord"):
                    logger.info(f"✅ Discord alert sent for {code}")

        self.update_heartbeat(status="running")

        if self.export_path and discovered_new > 0:
            self.storage.export_snapshot(self.export_path)
            logger.info(f"Exported updated snapshot to {self.export_path}")

        logger.info(
            f"Cycle #{self.cycle_count} complete: {discovered_new} new links found. "
            f"Total unique in DB: {self.storage.count()}."
        )
        return discovered_new

    def run_forever(self):
        """Run 24/7 continuous harvesting loop."""
        self.running = True
        logger.info(f"Starting 24/7 Continuous Harvester (interval: {self.interval}s)... Press Ctrl+C to stop.")
        self.update_heartbeat(status="running")

        try:
            while self.running:
                start_time = time.monotonic()
                try:
                    self.harvest_cycle()
                except Exception as exc:
                    logger.error(f"Error during harvest cycle: {exc}", exc_info=True)

                elapsed = time.monotonic() - start_time
                sleep_time = max(1.0, self.interval - elapsed)
                time.sleep(sleep_time)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received. Shutting down gracefully...")
        finally:
            self.running = False
            self.update_heartbeat(status="stopped")
            logger.info("Harvester stopped.")
