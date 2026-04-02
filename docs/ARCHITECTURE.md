# Threat-AI Architecture

## Runtime Boundaries

- `app.py` is the thin bootstrap and Flask entrypoint.
- `services/query_orchestrator.py` handles query routing, cache lookup, feed-first answers, retrieval, and response assembly.
- `services/feed_scheduler.py` owns the background ingest loop.
- `feeds/manager.py` owns feed loading, normalization, dedupe, per-source cursors, persistence, and recent-news lookup.
- `retrieval/`, `embeddings/`, `chunking/`, and `agent/` contain the main RAG pipeline.
- `conversation/` stores multi-turn context.
- `export/` generates reports.
- `evaluation/` handles audit/confidence.

## Data Boundary

- `data/` stores canonical threat data, conversation logs, and Chroma vector data.
- `feed/Data-feed/` stores the cyber feed ingester state and raw/normalized feed artifacts.
- `feeds/` is the code package.
- `feed/` is the data directory. The two names are intentionally different.

## Feed Ingestion Rules

- The scheduler runs on a fixed interval.
- Each source keeps its own ingest cursor in SQLite.
- New daily runs skip entries at or below the last cursor.
- Row-level dedupe still exists as a safety net.
- This prevents re-adding old items while still allowing new feed items to flow in.

## Deployment Notes

- Bind the web server to `0.0.0.0` on a remote server.
- Put a reverse proxy in front of Flask for production use.
- Keep Ollama local to the server or point the app to a reachable Ollama host.
- Run the ingest scheduler as part of the app process, or disable it and use an external scheduler if you want a stricter ops model.
