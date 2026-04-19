"""Production-ready threat feed ingestion and retrieval manager."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from retrieval.alias_resolver import AliasResolver

logger = logging.getLogger(__name__)


class ThreatFeedManager:
    """Handles feed source loading, ingestion, normalization, and actor-news retrieval."""

    def __init__(
        self,
        feed_csv_path: str = "feed/Data-feed/Threatactix - OpenCTI -RSS Feeds.csv",
        storage_root: str = "feed/Data-feed",
        actors_data_path: str = "data/canonical/actors.json",
        request_timeout: int = 20,
        max_retries: int = 2,
    ):
        self.feed_csv_path = Path(feed_csv_path)
        self.storage_root = Path(storage_root)
        self.request_timeout = request_timeout
        self.max_retries = max_retries

        self.raw_dir = self.storage_root / "raw"
        self.normalized_dir = self.storage_root / "normalized"
        self.state_dir = self.storage_root / "state"
        self.db_path = self.state_dir / "feed_items.db"
        self.runs_path = self.state_dir / "ingest_runs.jsonl"
        self.normalized_items_path = self.normalized_dir / "news_items.jsonl"

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.normalized_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.alias_resolver = AliasResolver(actors_data_path=actors_data_path)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ThreatActixFeedIngest/1.0 (+https://threatactix.local)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        })

        self._setup_db()

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _setup_db(self) -> None:
        """Initialize SQLite schema and indexes for production retrieval."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feed_sources (
                    source_id TEXT PRIMARY KEY,
                    source_name TEXT NOT NULL,
                    website TEXT,
                    feed_url TEXT NOT NULL UNIQUE,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_checked_at TEXT,
                    last_success_at TEXT,
                    last_cursor_published_at TEXT,
                    last_cursor_entry_id TEXT,
                    last_cursor_content_hash TEXT,
                    last_error TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feed_items (
                    news_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    source_url TEXT,
                    feed_url TEXT,
                    entry_id TEXT,
                    title TEXT NOT NULL,
                    summary TEXT,
                    content_text TEXT,
                    link TEXT NOT NULL,
                    canonical_url TEXT,
                    published_at TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    actor_tags_json TEXT NOT NULL,
                    tactic_tags_json TEXT NOT NULL,
                    ioc_tags_json TEXT NOT NULL,
                    language TEXT,
                    content_hash TEXT NOT NULL,
                    ingest_run_id TEXT,
                    UNIQUE(canonical_url, content_hash)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feed_item_actors (
                    news_id TEXT NOT NULL,
                    actor_name TEXT NOT NULL,
                    PRIMARY KEY(news_id, actor_name)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_feed_items_published ON feed_items(published_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_feed_items_source ON feed_items(source_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_feed_items_hash ON feed_items(content_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_feed_item_actors_actor ON feed_item_actors(actor_name)")

            # Backfill cursor columns for existing databases.
            existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(feed_sources)").fetchall()}
            for column_name, column_type in [
                ("last_cursor_published_at", "TEXT"),
                ("last_cursor_entry_id", "TEXT"),
                ("last_cursor_content_hash", "TEXT"),
            ]:
                if column_name not in existing_columns:
                    conn.execute(f"ALTER TABLE feed_sources ADD COLUMN {column_name} {column_type}")
            conn.commit()

    def _slugify(self, text: str) -> str:
        value = (text or "").strip().lower()
        value = re.sub(r"[^a-z0-9]+", "-", value)
        value = re.sub(r"-+", "-", value).strip("-")
        return value or "unknown"

    def _extract_first_url(self, value: str) -> Optional[str]:
        if not value:
            return None
        match = re.search(r"https?://[^\s,]+", value)
        return match.group(0).strip() if match else None

    def _source_id(self, source_name: str, feed_url: str) -> str:
        base = f"{source_name}|{feed_url}".encode("utf-8")
        digest = hashlib.sha256(base).hexdigest()[:10]
        return f"src-{self._slugify(source_name)}-{digest}"

    def _clean_html(self, value: str) -> str:
        if not value:
            return ""
        text = re.sub(r"<script[\s\S]*?</script>", " ", value, flags=re.IGNORECASE)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _to_iso(self, value: Any) -> str:
        """Convert feed date values to ISO-8601 (UTC) with robust fallback."""
        if value is None:
            return self._utc_now()

        if isinstance(value, str):
            v = value.strip()
            if not v:
                return self._utc_now()
            try:
                # Support trailing Z format.
                if v.endswith("Z"):
                    v = v[:-1] + "+00:00"
                dt = datetime.fromisoformat(v)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).isoformat()
            except Exception:
                pass

        if isinstance(value, (tuple, list)) and len(value) >= 6:
            try:
                dt = datetime(*value[:6], tzinfo=timezone.utc)
                return dt.isoformat()
            except Exception:
                pass

        return self._utc_now()

    def _extract_iocs(self, text: str) -> List[str]:
        if not text:
            return []
        iocs = set()
        for pattern in [
            r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b",  # IPv4
            r"\b[a-fA-F0-9]{32}\b",  # MD5
            r"\b[a-fA-F0-9]{40}\b",  # SHA1
            r"\b[a-fA-F0-9]{64}\b",  # SHA256
            r"\b[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b",  # Domain-like
        ]:
            for match in re.findall(pattern, text):
                iocs.add(match)
        return sorted(list(iocs))[:25]

    def _extract_tactic_tags(self, text: str) -> List[str]:
        if not text:
            return []
        text_l = text.lower()
        patterns = {
            "phishing": ["phishing", "spear-phishing", "phish"],
            "ransomware": ["ransomware", "encryptor"],
            "exploitation": ["exploit", "vulnerability", "cve-"],
            "credential_theft": ["credential", "password", "token theft"],
            "malware_delivery": ["dropper", "loader", "payload"],
            "supply_chain": ["supply chain", "third-party compromise"],
            "lateral_movement": ["lateral movement", "pivot"],
            "command_and_control": ["c2", "command and control", "beacon"],
        }
        tags = []
        for tag, kws in patterns.items():
            if any(k in text_l for k in kws):
                tags.append(tag)
        return tags

    def _extract_tactics_from_query(self, query: str) -> List[str]:
        """Extract tactic intent terms from a user query."""
        if not query:
            return []
        return self._extract_tactic_tags(query)

    def _extract_actor_tags(self, text: str, headline_text: str = "") -> List[str]:
        if not text:
            return []
        # Legacy behavior: allow fuzzy extraction over the full normalized text.
        matches = self.alias_resolver.extract_actors_from_query(text, allow_fuzzy=True)
        tags = sorted({m.get("primary_name") for m in matches if m.get("primary_name")})
        return tags[:20]

    def load_sources(self) -> List[Dict[str, str]]:
        """Load and sanitize source list from provided CSV (supports malformed rows)."""
        if not self.feed_csv_path.exists():
            raise FileNotFoundError(f"Feed CSV not found: {self.feed_csv_path}")

        rows: List[Dict[str, str]] = []
        seen_urls = set()

        with self.feed_csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for raw in reader:
                website = (raw.get("Wevsite") or raw.get("Website") or "").strip()
                feed_name = (raw.get("RSS Feed Name") or "").strip()
                feed_url = self._extract_first_url(feed_name)
                if not feed_url:
                    logger.warning("Skipping malformed feed row: website=%s feed_name=%s", website, feed_name)
                    continue
                if feed_url in seen_urls:
                    continue
                seen_urls.add(feed_url)

                source_name = website or urlparse(feed_url).netloc or "unknown-source"
                rows.append({
                    "source_id": self._source_id(source_name, feed_url),
                    "source_name": source_name,
                    "website": website,
                    "feed_url": feed_url,
                })

        self._upsert_sources(rows)
        return rows

    def _upsert_sources(self, sources: List[Dict[str, str]]) -> None:
        now = self._utc_now()
        with sqlite3.connect(self.db_path) as conn:
            for src in sources:
                conn.execute(
                    """
                    INSERT INTO feed_sources(source_id, source_name, website, feed_url, enabled, created_at)
                    VALUES(?, ?, ?, ?, 1, ?)
                    ON CONFLICT(source_id) DO UPDATE SET
                        source_name=excluded.source_name,
                        website=excluded.website,
                        feed_url=excluded.feed_url
                    """,
                    (
                        src["source_id"],
                        src["source_name"],
                        src.get("website"),
                        src["feed_url"],
                        now,
                    ),
                )
            conn.commit()

    def _fetch_feed(self, feed_url: str) -> Tuple[int, bytes, Optional[str]]:
        """Fetch one feed with retries and timeout; returns status, content, and error."""
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(feed_url, timeout=self.request_timeout)
                status = response.status_code
                if status >= 400:
                    last_error = f"HTTP {status}"
                    continue
                return status, response.content, None
            except Exception as exc:
                last_error = str(exc)
                if attempt < self.max_retries:
                    time.sleep(1.0 * (attempt + 1))
        return 0, b"", last_error

    def _parse_feed(self, raw_xml: bytes) -> Dict[str, Any]:
        import feedparser  # Imported lazily so app startup is not blocked if feed ingestion is unused.

        parsed = feedparser.parse(raw_xml)
        return {
            "feed": parsed.get("feed", {}),
            "entries": parsed.get("entries", []),
            "bozo": getattr(parsed, "bozo", False),
            "bozo_exception": str(getattr(parsed, "bozo_exception", "")) if getattr(parsed, "bozo", False) else "",
        }

    def _entry_content_text(self, entry: Dict[str, Any]) -> str:
        content = ""
        if isinstance(entry.get("content"), list) and entry.get("content"):
            first = entry["content"][0]
            content = first.get("value", "") if isinstance(first, dict) else str(first)
        elif entry.get("summary"):
            content = entry.get("summary", "")
        return self._clean_html(content)

    def _entry_summary(self, entry: Dict[str, Any]) -> str:
        return self._clean_html(entry.get("summary", ""))

    def _canonicalize_url(self, url: str) -> str:
        if not url:
            return ""
        parsed = urlparse(url)
        # Strip query params used for tracking where possible.
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")

    def _news_id(self, source_id: str, canonical_url: str, title: str) -> str:
        seed = f"{source_id}|{canonical_url}|{title}".encode("utf-8")
        return "news-" + hashlib.sha256(seed).hexdigest()[:24]

    def _content_hash(self, title: str, summary: str, content_text: str) -> str:
        base = f"{title}|{summary}|{content_text}".encode("utf-8")
        return hashlib.sha256(base).hexdigest()

    def _entry_cursor(self, item: Dict[str, Any]) -> Tuple[str, str, str]:
        published_at = str(item.get("published_at") or "")
        entry_id = str(item.get("entry_id") or "")
        content_hash = str(item.get("content_hash") or "")
        return published_at, entry_id, content_hash

    def _source_cursor(self, source_id: str) -> Optional[Tuple[str, str, str]]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT last_cursor_published_at, last_cursor_entry_id, last_cursor_content_hash
                FROM feed_sources
                WHERE source_id = ?
                """,
                (source_id,),
            ).fetchone()
        if not row or not any(row):
            return None
        return str(row[0] or ""), str(row[1] or ""), str(row[2] or "")

    def _update_source_cursor(self, source_id: str, cursor: Tuple[str, str, str]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE feed_sources
                SET last_cursor_published_at = ?,
                    last_cursor_entry_id = ?,
                    last_cursor_content_hash = ?
                WHERE source_id = ?
                """,
                (cursor[0], cursor[1], cursor[2], source_id),
            )
            conn.commit()

    def _normalize_entry(self, source: Dict[str, str], entry: Dict[str, Any], ingest_run_id: str) -> Dict[str, Any]:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        summary = self._entry_summary(entry)
        content_text = self._entry_content_text(entry)

        published_raw = entry.get("published_parsed") or entry.get("updated_parsed") or entry.get("published") or entry.get("updated")
        published_at = self._to_iso(published_raw)
        fetched_at = self._utc_now()

        searchable_text = " ".join([title, summary, content_text]).strip()
        actor_tags = self._extract_actor_tags(searchable_text, headline_text=" ".join([title, summary]).strip())
        tactic_tags = self._extract_tactic_tags(searchable_text)
        ioc_tags = self._extract_iocs(searchable_text)

        canonical_url = self._canonicalize_url(link)
        content_hash = self._content_hash(title, summary, content_text)
        news_id = self._news_id(source["source_id"], canonical_url, title)

        return {
            "news_id": news_id,
            "source_id": source["source_id"],
            "source_name": source["source_name"],
            "source_url": source.get("website") or None,
            "feed_url": source.get("feed_url"),
            "entry_id": (entry.get("id") or entry.get("guid") or "")[:512] or None,
            "title": title or "(untitled)",
            "summary": summary or None,
            "content_text": content_text or None,
            "link": link,
            "canonical_url": canonical_url or None,
            "published_at": published_at,
            "fetched_at": fetched_at,
            "actor_tags": actor_tags,
            "tactic_tags": tactic_tags,
            "ioc_tags": ioc_tags,
            "language": None,
            "content_hash": content_hash,
            "ingest_run_id": ingest_run_id,
        }

    def _save_raw_feed(self, source: Dict[str, str], payload: bytes, ingest_run_id: str) -> Path:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        source_dir = self.raw_dir / day
        source_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"{source['source_id']}-{ingest_run_id}.xml"
        path = source_dir / file_name
        path.write_bytes(payload)
        return path

    def _insert_item(self, item: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> bool:
        """Insert normalized item, deduping by news_id and canonical_url/content_hash constraints."""
        own_conn = conn is None
        db = conn or sqlite3.connect(self.db_path)
        try:
            # Stronger duplicate guard for scheduler runs:
            # 1) Same source + entry_id
            # 2) Same canonical URL
            entry_id = item.get("entry_id")
            if entry_id:
                row = db.execute(
                    """
                    SELECT 1 FROM feed_items
                    WHERE source_id = ? AND entry_id = ?
                    LIMIT 1
                    """,
                    (item["source_id"], entry_id),
                ).fetchone()
                if row:
                    return False

            canonical_url = item.get("canonical_url")
            if canonical_url:
                row = db.execute(
                    """
                    SELECT 1 FROM feed_items
                    WHERE canonical_url = ?
                    LIMIT 1
                    """,
                    (canonical_url,),
                ).fetchone()
                if row:
                    return False

            db.execute(
                """
                INSERT INTO feed_items(
                    news_id, source_id, source_name, source_url, feed_url, entry_id, title,
                    summary, content_text, link, canonical_url, published_at, fetched_at,
                    actor_tags_json, tactic_tags_json, ioc_tags_json, language, content_hash, ingest_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["news_id"],
                    item["source_id"],
                    item["source_name"],
                    item.get("source_url"),
                    item.get("feed_url"),
                    item.get("entry_id"),
                    item["title"],
                    item.get("summary"),
                    item.get("content_text"),
                    item["link"],
                    item.get("canonical_url"),
                    item["published_at"],
                    item["fetched_at"],
                    json.dumps(item.get("actor_tags", []), ensure_ascii=True),
                    json.dumps(item.get("tactic_tags", []), ensure_ascii=True),
                    json.dumps(item.get("ioc_tags", []), ensure_ascii=True),
                    item.get("language"),
                    item["content_hash"],
                    item.get("ingest_run_id"),
                ),
            )
            for actor in item.get("actor_tags", []):
                db.execute(
                    "INSERT OR IGNORE INTO feed_item_actors(news_id, actor_name) VALUES(?, ?)",
                    (item["news_id"], actor),
                )
            if own_conn:
                db.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            if own_conn:
                db.close()

    def _append_normalized_item(self, item: Dict[str, Any]) -> None:
        with self.normalized_items_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=True) + "\n")

    def _mark_source_status(self, source_id: str, success: bool, error: Optional[str]) -> None:
        now = self._utc_now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE feed_sources
                SET last_checked_at = ?,
                    last_success_at = CASE WHEN ? = 1 THEN ? ELSE last_success_at END,
                    last_error = ?
                WHERE source_id = ?
                """,
                (now, 1 if success else 0, now, error, source_id),
            )
            conn.commit()

    def _source_last_success_at(self, source_id: str) -> Optional[datetime]:
        """Return last successful ingest timestamp for a source."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT last_success_at FROM feed_sources WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        if not row or not row[0]:
            return None
        try:
            value = str(row[0])
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None

    def _should_skip_source(self, source_id: str, fresh_hours: int) -> bool:
        """Check whether source is fresh enough to skip this run."""
        last_success = self._source_last_success_at(source_id)
        if not last_success:
            return False
        age = datetime.now(timezone.utc) - last_success
        return age < timedelta(hours=max(1, fresh_hours))

    def ingest_all_sources(
        self,
        max_items_per_source: int = 50,
        skip_if_fresh: bool = True,
        fresh_hours: int = 12,
        source_limit: int = 0,
    ) -> Dict[str, Any]:
        """Fetch and normalize all feed sources from CSV with production-safe error handling."""
        sources = self.load_sources()
        if source_limit and int(source_limit) > 0:
            sources = sources[: int(source_limit)]
        ingest_run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

        run_stats = {
            "ingest_run_id": ingest_run_id,
            "started_at": self._utc_now(),
            "sources_total": len(sources),
            "sources_success": 0,
            "sources_failed": 0,
            "items_seen": 0,
            "items_inserted": 0,
            "items_deduped": 0,
            "sources_skipped_fresh": 0,
            "errors": [],
        }

        for source in sources:
            if skip_if_fresh and self._should_skip_source(source["source_id"], fresh_hours=fresh_hours):
                run_stats["sources_skipped_fresh"] += 1
                continue

            status, payload, error = self._fetch_feed(source["feed_url"])
            if error:
                run_stats["sources_failed"] += 1
                run_stats["errors"].append({"source": source["source_name"], "error": error})
                self._mark_source_status(source["source_id"], success=False, error=error)
                continue

            self._save_raw_feed(source, payload, ingest_run_id)
            parsed = self._parse_feed(payload)
            entries = parsed.get("entries", [])[:max_items_per_source]
            run_stats["sources_success"] += 1
            self._mark_source_status(source["source_id"], success=True, error=None)

            current_cursor = self._source_cursor(source["source_id"])
            newest_cursor = current_cursor
            prior_cursor = None
            cursors_descending = True

            with sqlite3.connect(self.db_path) as conn:
                for entry in entries:
                    link = (entry.get("link") or "").strip()
                    title = (entry.get("title") or "").strip()
                    if not link or not title:
                        continue

                    run_stats["items_seen"] += 1
                    item = self._normalize_entry(source, entry, ingest_run_id)
                    item_cursor = self._entry_cursor(item)

                    if prior_cursor is not None and item_cursor > prior_cursor:
                        cursors_descending = False
                    prior_cursor = item_cursor

                    if current_cursor and item_cursor <= current_cursor:
                        if cursors_descending:
                            # Feed appears newest-first: once cursor is reached, remaining entries are older.
                            break
                        continue

                    if newest_cursor is None or item_cursor > newest_cursor:
                        newest_cursor = item_cursor

                    inserted = self._insert_item(item, conn=conn)
                    if inserted:
                        run_stats["items_inserted"] += 1
                        self._append_normalized_item(item)
                    else:
                        run_stats["items_deduped"] += 1

                conn.commit()

            if newest_cursor and newest_cursor != current_cursor:
                self._update_source_cursor(source["source_id"], newest_cursor)

        run_stats["ended_at"] = self._utc_now()
        with self.runs_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(run_stats, ensure_ascii=True) + "\n")

        return run_stats

    def get_ingestion_health(self, failed_limit: int = 25, source_limit: int = 200) -> Dict[str, Any]:
        """Return scheduler/ingestion health: last run, per-source success, and failed sources."""
        latest_run = None
        if self.runs_path.exists():
            try:
                with self.runs_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            latest_run = json.loads(line)
            except Exception as exc:
                logger.warning("Unable to read latest feed ingest run: %s", exc)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            failed_rows = conn.execute(
                """
                SELECT source_id, source_name, feed_url, last_checked_at, last_success_at, last_error,
                       last_cursor_published_at, last_cursor_entry_id, last_cursor_content_hash
                FROM feed_sources
                WHERE enabled = 1 AND last_error IS NOT NULL AND TRIM(last_error) != ''
                ORDER BY last_checked_at DESC
                LIMIT ?
                """,
                (max(1, failed_limit),),
            ).fetchall()

            source_rows = conn.execute(
                """
                SELECT source_id, source_name, feed_url, enabled, last_checked_at, last_success_at, last_error,
                       last_cursor_published_at, last_cursor_entry_id, last_cursor_content_hash
                FROM feed_sources
                ORDER BY source_name ASC
                LIMIT ?
                """,
                (max(1, source_limit),),
            ).fetchall()

            total_sources = conn.execute("SELECT COUNT(*) FROM feed_sources").fetchone()[0]
            enabled_sources = conn.execute("SELECT COUNT(*) FROM feed_sources WHERE enabled = 1").fetchone()[0]

        failed_sources = [
            {
                "source_id": row["source_id"],
                "source_name": row["source_name"],
                "feed_url": row["feed_url"],
                "last_checked_at": row["last_checked_at"],
                "last_success_at": row["last_success_at"],
                "last_error": row["last_error"],
                "cursor_published_at": row["last_cursor_published_at"],
                "cursor_entry_id": row["last_cursor_entry_id"],
                "cursor_content_hash": row["last_cursor_content_hash"],
            }
            for row in failed_rows
        ]

        source_status = [
            {
                "source_id": row["source_id"],
                "source_name": row["source_name"],
                "feed_url": row["feed_url"],
                "enabled": bool(row["enabled"]),
                "last_checked_at": row["last_checked_at"],
                "last_success_at": row["last_success_at"],
                "last_error": row["last_error"],
                "cursor_published_at": row["last_cursor_published_at"],
                "cursor_entry_id": row["last_cursor_entry_id"],
                "cursor_content_hash": row["last_cursor_content_hash"],
            }
            for row in source_rows
        ]

        return {
            "as_of": self._utc_now(),
            "last_run": latest_run,
            "summary": {
                "total_sources": int(total_sources or 0),
                "enabled_sources": int(enabled_sources or 0),
                "failed_sources_count": len(failed_sources),
                "sources_reported": len(source_status),
            },
            "failed_sources": failed_sources,
            "source_status": source_status,
        }

    def rebuild_item_tags(self, limit: int = 0) -> Dict[str, Any]:
        """Recompute actor/tactic tags for existing feed items using strict extraction rules."""
        updated = 0
        scanned = 0

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            query = (
                "SELECT news_id, title, summary, content_text "
                "FROM feed_items ORDER BY published_at DESC"
            )
            params: List[Any] = []
            if limit and int(limit) > 0:
                query += " LIMIT ?"
                params.append(int(limit))

            rows = conn.execute(query, params).fetchall()

            for row in rows:
                scanned += 1
                text = " ".join([
                    str(row["title"] or ""),
                    str(row["summary"] or ""),
                    str(row["content_text"] or ""),
                ]).strip()

                actor_tags = self._extract_actor_tags(text)
                tactic_tags = self._extract_tactic_tags(text)

                conn.execute(
                    """
                    UPDATE feed_items
                    SET actor_tags_json = ?, tactic_tags_json = ?
                    WHERE news_id = ?
                    """,
                    (
                        json.dumps(actor_tags, ensure_ascii=True),
                        json.dumps(tactic_tags, ensure_ascii=True),
                        row["news_id"],
                    ),
                )

                conn.execute("DELETE FROM feed_item_actors WHERE news_id = ?", (row["news_id"],))
                for actor in actor_tags:
                    conn.execute(
                        "INSERT OR IGNORE INTO feed_item_actors(news_id, actor_name) VALUES(?, ?)",
                        (row["news_id"], actor),
                    )

                updated += 1

            conn.commit()

        return {
            "scanned": scanned,
            "updated": updated,
            "limited": bool(limit and int(limit) > 0),
            "limit": int(limit or 0),
        }

    def get_recent_actor_news(self, actor_name: str, days: int = 90, limit: int = 8) -> List[Dict[str, Any]]:
        """Get recent news for a canonical actor name, sorted newest first."""
        if not actor_name:
            return []

        actor_primary = self.alias_resolver.resolve(actor_name) or actor_name
        since = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT i.news_id, i.source_name, i.title, i.summary, i.link, i.published_at, i.actor_tags_json
                FROM feed_items i
                INNER JOIN feed_item_actors a ON a.news_id = i.news_id
                WHERE a.actor_name = ?
                  AND i.published_at >= ?
                ORDER BY i.published_at DESC
                LIMIT ?
                """,
                (actor_primary, since, max(1, limit)),
            ).fetchall()

            if not rows:
                # Fallback: alias text search in title/summary/content when actor tag index misses.
                aliases = set(self.alias_resolver.get_aliases(actor_primary) or set())
                aliases.add(actor_primary)
                alias_terms = [a.strip().lower() for a in aliases if a and 4 <= len(a.strip()) <= 50 and "," not in a]
                # Include common "group"-stripped variant for better recall.
                for term in list(alias_terms):
                    if term.endswith(" group") and len(term) > 10:
                        alias_terms.append(term[:-6].strip())
                alias_terms = sorted(set(alias_terms))[:20]

                if alias_terms:
                    like_clauses = " OR ".join([
                        "lower(i.title) LIKE ? OR lower(i.summary) LIKE ? OR lower(i.content_text) LIKE ?"
                        for _ in alias_terms
                    ])
                    params: List[Any] = [since]
                    for term in alias_terms:
                        pattern = f"%{term}%"
                        params.extend([pattern, pattern, pattern])
                    params.append(max(1, limit))

                    rows = conn.execute(
                        f"""
                        SELECT i.news_id, i.source_name, i.title, i.summary, i.link, i.published_at, i.actor_tags_json
                        FROM feed_items i
                        WHERE i.published_at >= ?
                          AND ({like_clauses})
                        ORDER BY i.published_at DESC
                        LIMIT ?
                        """,
                        params,
                    ).fetchall()

        result = []
        for row in rows:
            result.append(
                {
                    "news_id": row["news_id"],
                    "source_name": row["source_name"],
                    "title": row["title"],
                    "summary": row["summary"] or "",
                    "link": row["link"],
                    "published_at": row["published_at"],
                    "actor_tags": json.loads(row["actor_tags_json"] or "[]"),
                }
            )
        return result

    def get_recent_tactic_news(
        self,
        tactic_tags: List[str],
        days: int = 90,
        limit: int = 8,
        actor_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get recent news filtered by one or more tactic tags, optionally scoped to actor."""
        tactic_tags = [t for t in (tactic_tags or []) if t]
        if not tactic_tags:
            return []

        since = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).isoformat()
        like_clauses = " OR ".join(["i.tactic_tags_json LIKE ?" for _ in tactic_tags])
        like_values = [f'%"{tag}"%' for tag in tactic_tags]

        actor_primary = None
        if actor_name:
            actor_primary = self.alias_resolver.resolve(actor_name) or actor_name

        query = (
            "SELECT i.news_id, i.source_name, i.title, i.summary, i.link, i.published_at, "
            "i.actor_tags_json, i.tactic_tags_json "
            "FROM feed_items i "
        )
        params: List[Any] = []

        if actor_primary:
            query += "INNER JOIN feed_item_actors a ON a.news_id = i.news_id "

        query += f"WHERE i.published_at >= ? AND ({like_clauses}) "
        params.append(since)
        params.extend(like_values)

        if actor_primary:
            query += "AND a.actor_name = ? "
            params.append(actor_primary)

        query += "ORDER BY i.published_at DESC LIMIT ?"
        params.append(max(1, limit))

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()

        result = []
        for row in rows:
            result.append(
                {
                    "news_id": row["news_id"],
                    "source_name": row["source_name"],
                    "title": row["title"],
                    "summary": row["summary"] or "",
                    "link": row["link"],
                    "published_at": row["published_at"],
                    "actor_tags": json.loads(row["actor_tags_json"] or "[]"),
                    "tactic_tags": json.loads(row["tactic_tags_json"] or "[]"),
                }
            )
        return result

    def is_recent_attack_query(self, query: str) -> bool:
        """Determine whether query asks for recent actor attack/news updates."""
        q = (query or "").lower()
        recent_terms = ["recent", "latest", "news", "update", "updates", "headline", "headlines", "today"]
        attack_terms = [
            "attack", "attacks", "campaign", "operation", "incident", "breach",
            "phishing", "ransomware", "exploit", "exploitation", "tactic", "tactics",
        ]
        return any(t in q for t in recent_terms) and any(t in q for t in attack_terms)

    def answer_recent_attack_query(self, query: str, days: int = 90, limit: int = 5) -> Optional[Dict[str, Any]]:
        """Answer recent actor attack query from feed storage with direct links."""
        if not self.is_recent_attack_query(query):
            return None

        actors = self.alias_resolver.extract_actors_from_query(query, allow_fuzzy=True)
        tactic_filters = self._extract_tactics_from_query(query)

        actor_primary = None
        if actors:
            actor_primary = actors[0].get("primary_name")

        if not actor_primary:
            # Single-name typo fallback (e.g., "alazarouse group").
            words = re.findall(r"[A-Za-z0-9-]{4,}", query)
            for w in words:
                resolved = self.alias_resolver.resolve(w)
                if resolved:
                    actor_primary = resolved
                    break

        if not actor_primary and not tactic_filters:
            return None

        if tactic_filters:
            items = self.get_recent_tactic_news(
                tactic_tags=tactic_filters,
                days=days,
                limit=limit,
                actor_name=actor_primary,
            )
        else:
            items = self.get_recent_actor_news(actor_primary, days=days, limit=limit)

        focus_label = actor_primary or ", ".join(tactic_filters)
        if not items:
            return {
                "query": query,
                "answer": f"No recent feed updates found for {focus_label} in the last {days} days.",
                "confidence": 0.35,
                "source_count": 0,
                "model": "feed-index",
                "response_mode": "feed_news",
                "query_type": "recent_attack_news",
                "primary_actors": [actor_primary] if actor_primary else [],
                "timings": {"retrieval": 0.0, "generation": 0.0, "audit": 0.0, "total": 0.0},
                "actor_name": actor_primary or "",
                "tactic_filters": tactic_filters,
                "news_items": [],
                "evidence": [],
            }

        lines = [f"Recent threat feed updates for {focus_label}:"]
        evidence = []
        for idx, item in enumerate(items, 1):
            date_label = item.get("published_at", "")[:10]
            title = item.get("title", "Untitled")
            source = item.get("source_name", "Unknown Source")
            link = item.get("link", "")
            lines.append(f"{idx}. [{date_label}] {title} ({source})")
            lines.append(f"   Link: {link}")

            evidence.append(
                {
                    "text": f"{title}. {item.get('summary', '')}".strip(),
                    "score": 0.95 - (idx * 0.03),
                    "source": "threat_feed",
                    "actor": actor_primary or "",
                    "links": [link],
                }
            )

        return {
            "query": query,
            "answer": "\n".join(lines),
            "confidence": 0.82,
            "source_count": len(items),
            "model": "feed-index",
            "response_mode": "feed_news",
            "query_type": "recent_attack_news",
            "primary_actors": [actor_primary] if actor_primary else [],
            "timings": {"retrieval": 0.0, "generation": 0.0, "audit": 0.0, "total": 0.0},
            "actor_name": actor_primary or "",
            "tactic_filters": tactic_filters,
            "news_items": items,
            "evidence": evidence,
        }
