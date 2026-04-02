"""Recompute feed actor/tactic tags for existing rows using strict extraction."""

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
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-tag existing feed items with strict actor/tactic extraction")
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of newest items to retag (0 = all)")
    parser.add_argument("--storage", type=str, default="feed/Data-feed", help="Feed data storage root")
    parser.add_argument("--csv", type=str, default="feed/Data-feed/Threatactix - OpenCTI -RSS Feeds.csv", help="Feed source CSV path")
    args = parser.parse_args()

    manager = ThreatFeedManager(feed_csv_path=args.csv, storage_root=args.storage)
    result = manager.rebuild_item_tags(limit=max(0, int(args.limit or 0)))
    logger.info("Feed retag complete")
    logger.info(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
