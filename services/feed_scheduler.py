"""Background ingestion scheduler for threat feeds."""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class FeedScheduler:
    """Run feed ingestion on a fixed interval in a background thread."""

    def __init__(
        self,
        feed_manager=None,
        interval_hours: int = 12,
        max_items_per_source: int = 50,
        enabled: bool = True,
    ):
        self.feed_manager = feed_manager
        self.interval_hours = max(1, int(interval_hours or 12))
        self.max_items_per_source = max(1, int(max_items_per_source or 50))
        self.enabled = bool(enabled)
        self.thread: Optional[threading.Thread] = None
        self.stop_event: Optional[threading.Event] = None
        self.last_run_stats: Optional[Dict[str, Any]] = None

    def _run(self) -> None:
        interval_seconds = self.interval_hours * 3600
        logger.info("Feed scheduler started (interval=%sh)", self.interval_hours)

        while self.stop_event and not self.stop_event.is_set():
            try:
                if self.feed_manager is not None:
                    stats = self.feed_manager.ingest_all_sources(
                        max_items_per_source=self.max_items_per_source,
                        skip_if_fresh=True,
                        fresh_hours=self.interval_hours,
                    )
                    self.last_run_stats = stats
                    logger.info(
                        "Feed scheduler run complete: success=%s failed=%s skipped=%s inserted=%s deduped=%s",
                        stats.get("sources_success", 0),
                        stats.get("sources_failed", 0),
                        stats.get("sources_skipped_fresh", 0),
                        stats.get("items_inserted", 0),
                        stats.get("items_deduped", 0),
                    )
            except Exception as sched_exc:
                logger.error("Feed scheduler run failed: %s", sched_exc)

            if self.stop_event:
                self.stop_event.wait(interval_seconds)

    def start(self) -> None:
        """Start the scheduler once."""
        if not self.enabled:
            logger.info("Feed scheduler disabled by configuration")
            return

        if self.thread and self.thread.is_alive():
            return

        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name="feed-scheduler")
        self.thread.start()

    def stop(self) -> None:
        """Stop the background scheduler."""
        if self.stop_event:
            self.stop_event.set()

    def is_alive(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "alive": self.is_alive(),
            "interval_hours": self.interval_hours,
            "max_items_per_source": self.max_items_per_source,
            "last_run_stats": self.last_run_stats,
        }
