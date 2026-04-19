"""Ingest all configured cyber threat feeds into normalized storage and SQLite index."""

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from feeds import ThreatFeedManager


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest threat RSS/Atom feeds")
    parser.add_argument("--max-items-per-source", type=int, default=50, help="Max entries to process per feed source")
    parser.add_argument("--source-limit", type=int, default=0, help="Only process first N feed sources (0 = all)")
    parser.add_argument("--csv", type=str, default="feed/Data-feed/Threatactix - OpenCTI -RSS Feeds.csv", help="Feed source CSV path")
    parser.add_argument("--storage", type=str, default="feed/Data-feed", help="Feed data storage root")
    parser.add_argument("--fresh-hours", type=int, default=12, help="Skip sources already ingested within this many hours")
    parser.add_argument("--request-timeout", type=int, default=8, help="HTTP timeout in seconds per feed request")
    parser.add_argument("--max-retries", type=int, default=0, help="Retry count per feed request")
    parser.add_argument("--force", action="store_true", help="Force ingest all sources (ignore freshness skip)")
    args = parser.parse_args()

    manager = ThreatFeedManager(
        feed_csv_path=args.csv,
        storage_root=args.storage,
        request_timeout=max(1, args.request_timeout),
        max_retries=max(0, args.max_retries),
    )
    stats = manager.ingest_all_sources(
        max_items_per_source=max(1, args.max_items_per_source),
        skip_if_fresh=not bool(args.force),
        fresh_hours=max(1, args.fresh_hours),
        source_limit=max(0, args.source_limit),
    )

    logger.info("Feed ingestion completed")
    logger.info(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
