"""Query recent actor-related feed news from local feed storage."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from feeds import ThreatFeedManager


def main() -> int:
    parser = argparse.ArgumentParser(description="Query recent feed news by actor")
    parser.add_argument("actor", type=str, help="Actor name or alias, e.g. APT28")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    manager = ThreatFeedManager()
    rows = manager.get_recent_actor_news(args.actor, days=max(1, args.days), limit=max(1, args.limit))
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
