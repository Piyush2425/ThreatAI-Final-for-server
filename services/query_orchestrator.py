"""Query orchestration, cache, and feed-first response handling."""

from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class QueryOrchestrator:
    """Coordinate cache lookup, feed-first queries, retrieval, and answer generation."""

    def __init__(
        self,
        retriever=None,
        interpreter=None,
        audit=None,
        conversation_manager=None,
        threat_feed_manager=None,
        cache: Optional[Dict[str, Dict[str, Any]]] = None,
        cache_ttl_seconds: int = 3600,
    ):
        self.retriever = retriever
        self.interpreter = interpreter
        self.audit = audit
        self.conversation_manager = conversation_manager
        self.threat_feed_manager = threat_feed_manager
        self.cache = cache if cache is not None else {}
        self.cache_ttl_seconds = cache_ttl_seconds

    def _normalize_cache_query(self, text: str) -> str:
        value = (text or "").strip().lower()
        value = re.sub(r"\s+", " ", value)
        value = re.sub(r"[\?\.!;:,]+$", "", value)
        return value

    def _token_jaccard(self, a: str, b: str) -> float:
        sa = set((a or "").split())
        sb = set((b or "").split())
        if not sa or not sb:
            return 0.0
        union = len(sa | sb)
        if union == 0:
            return 0.0
        return len(sa & sb) / union

    def _fuzzy_threshold(self, normalized_query: str) -> float:
        length = len(normalized_query or "")
        if length <= 18:
            return 0.92
        if length <= 35:
            return 0.86
        return 0.84

    def _extract_actor_hint(self, text: str) -> str:
        if not text:
            return ""
        q = text.lower()
        apt_match = re.search(r"\bapt\s*-?\s*(\d+)\b", q)
        if apt_match:
            return f"apt{apt_match.group(1)}"
        ta_match = re.search(r"\bta\s*-?\s*(\d+)\b", q)
        if ta_match:
            return f"ta{ta_match.group(1)}"
        return ""

    def _find_cached_response(self, query_text: str):
        normalized_query = self._normalize_cache_query(query_text)
        actor_hint = self._extract_actor_hint(query_text)
        now = time.time()

        for item in self.cache.values():
            cache_age = now - item.get("cached_at", 0)
            if cache_age >= self.cache_ttl_seconds:
                continue
            if item.get("normalized_query") == normalized_query:
                return item, "exact", 1.0

        best_item = None
        best_score = 0.0
        threshold = self._fuzzy_threshold(normalized_query)

        for item in self.cache.values():
            cache_age = now - item.get("cached_at", 0)
            if cache_age >= self.cache_ttl_seconds:
                continue

            candidate = item.get("normalized_query") or self._normalize_cache_query(item.get("query", ""))
            if not candidate:
                continue

            if actor_hint:
                candidate_actor = self._extract_actor_hint(item.get("query", ""))
                if candidate_actor and candidate_actor != actor_hint:
                    continue

            char_score = SequenceMatcher(None, normalized_query, candidate).ratio()
            token_score = self._token_jaccard(normalized_query, candidate)
            score = max(char_score, (0.9 * char_score) + (0.1 * token_score))

            if score > best_score:
                best_score = score
                best_item = item

        if best_item and best_score >= threshold:
            return best_item, "fuzzy", round(best_score, 4)

        return None, None, 0.0

    def _summarize_recent_feed_with_llm(self, query_text: str, actor_name: str, news_items: list) -> str:
        if not news_items:
            return ""

        top_items = news_items[:5]
        evidence_lines = []
        for idx, item in enumerate(top_items, 1):
            date_label = (item.get("published_at") or "")[:10]
            evidence_lines.append(
                f"{idx}. date={date_label} | source={item.get('source_name', 'Unknown')} | "
                f"title={item.get('title', '')} | summary={item.get('summary', '')} | link={item.get('link', '')}"
            )

        if self.interpreter is not None and getattr(self.interpreter, "use_ollama", False):
            prompt = (
                "You are a cybersecurity analyst assistant.\n"
                "Task: summarize recent actor-related threat news strictly from provided feed evidence.\n"
                "Rules:\n"
                "1) Do not invent facts.\n"
                "2) Keep summary short (4-6 lines).\n"
                "3) Then output a bullet list with Date, Source, Headline, and Link for each item.\n"
                "4) Keep links exactly as provided.\n\n"
                f"User query: {query_text}\n"
                f"Actor: {actor_name}\n\n"
                "Feed evidence:\n"
                + "\n".join(evidence_lines)
            )
            try:
                answer = self.interpreter.llm.generate(prompt=prompt, temperature=0.1, max_tokens=650, timeout=60)
                if answer and answer.strip():
                    return answer.strip()
            except Exception as llm_exc:
                logger.warning("Feed LLM summarization failed, using structured fallback: %s", llm_exc)

        lines = [f"Recent threat feed updates for {actor_name}:"]
        for idx, item in enumerate(top_items, 1):
            date_label = (item.get("published_at") or "")[:10]
            lines.append(f"{idx}. [{date_label}] {item.get('title', 'Untitled')} ({item.get('source_name', 'Unknown')})")
            lines.append(f"   Link: {item.get('link', '')}")
        return "\n".join(lines)

    def process_query(self, query_text: str, use_cache: bool = True, conversation_id: str = None) -> dict:
        import hashlib as _hashlib
        from agent.comparison_detector import ComparisonDetector

        start_time = time.time()

        try:
            if not query_text.strip():
                return {"error": "Query cannot be empty"}

            if not self.retriever or not self.interpreter:
                return {"error": "System not initialized"}

            if self.threat_feed_manager is not None:
                try:
                    feed_start = time.time()
                    feed_result = self.threat_feed_manager.answer_recent_attack_query(query_text, days=90, limit=5)
                    if feed_result:
                        news_items = feed_result.get("news_items", [])
                        actor_name = (feed_result.get("actor_name") or (feed_result.get("primary_actors") or [""])[0]).strip()
                        if news_items and actor_name:
                            summary_start = time.time()
                            feed_result["answer"] = self._summarize_recent_feed_with_llm(query_text, actor_name, news_items)
                            feed_result["timings"]["generation"] = round(time.time() - summary_start, 4)

                        feed_result["timings"]["retrieval"] = round(time.time() - feed_start, 4)
                        feed_result["timings"]["total"] = round(time.time() - start_time, 4)
                        feed_result["timestamp"] = datetime.now().isoformat()
                        feed_result["trace_id"] = "feed-news-" + _hashlib.md5(query_text.encode()).hexdigest()[:12]
                        feed_result["processing_time"] = time.time() - start_time
                        feed_result["from_cache"] = False
                        return feed_result
                except Exception as feed_exc:
                    logger.warning("Threat feed query path failed, falling back to RAG: %s", feed_exc)

            cache_key = _hashlib.md5(self._normalize_cache_query(query_text).encode()).hexdigest()
            if use_cache:
                cached_result, match_type, match_score = self._find_cached_response(query_text)
                if cached_result:
                    logger.info("⚡ Main cache hit (%s, score=%.3f)", match_type, match_score)
                    cached_result["from_cache"] = True
                    cached_result["cache_match_type"] = match_type
                    cached_result["cache_match_score"] = match_score
                    cached_result["processing_time"] = time.time() - start_time
                    return cached_result

            logger.info("Processing query: %s", query_text)

            conversation = None
            if conversation_id and self.conversation_manager:
                conversation = self.conversation_manager.load_or_create_conversation(conversation_id)
                logger.info("📋 Loaded conversation: %s", conversation_id)

            current_actor = conversation.current_actor if conversation else None
            query_type = ComparisonDetector.get_query_type(query_text, current_actor)
            logger.info("Query type: %s", query_type)

            retrieval_start = time.time()
            retrieval_result = self.retriever.retrieve_actor_scoped(query_text, retrieval_mode="full_actor")
            retrieval_time = time.time() - retrieval_start
            logger.info("⏱️ Retrieval completed in %.2fs (mode: %s)", retrieval_time, retrieval_result.get("retrieval_mode", "hybrid"))

            evidence = retrieval_result.get("evidence", [])
            response_mode = retrieval_result.get("response_mode", "adaptive")
            parsed_query = retrieval_result.get("parsed_query") or {}
            primary_actors = [
                actor.get("primary_name")
                for actor in parsed_query.get("actors", [])
                if actor.get("primary_name")
            ]
            if not primary_actors and evidence:
                seen = set()
                ordered = []
                for chunk in evidence:
                    primary = chunk.get("metadata", {}).get("primary_name")
                    if primary and primary not in seen:
                        seen.add(primary)
                        ordered.append(primary)
                primary_actors = ordered

            if conversation and primary_actors:
                for actor_name in primary_actors:
                    actor_chunks = [e for e in evidence if e.get("metadata", {}).get("primary_name") == actor_name]
                    if actor_chunks:
                        conversation.cache_actor_chunks(actor_name, actor_chunks)
                        if actor_name not in conversation.actors_mentioned:
                            conversation.actors_mentioned.append(actor_name)

                if primary_actors:
                    conversation.current_actor = primary_actors[0]
                    logger.info("💾 Cached %s actor(s) in conversation", len(primary_actors))

            if query_type == "comparison" and ComparisonDetector.is_comparison_query(query_text) and conversation:
                alias_resolver = self.retriever.alias_resolver if hasattr(self.retriever, "alias_resolver") else None
                if alias_resolver:
                    all_actors = ComparisonDetector.extract_all_actors(query_text, alias_resolver)
                    for actor_info in all_actors:
                        actor_name = actor_info.get("primary_name")
                        if actor_name and not conversation.has_actor_cached(actor_name):
                            actor_retrieval = self.retriever.retrieve_actor_scoped(f"information about {actor_name}", retrieval_mode="full_actor")
                            actor_chunks = actor_retrieval.get("evidence", [])
                            if actor_chunks:
                                conversation.cache_actor_chunks(actor_name, actor_chunks)
                                if actor_name not in conversation.actors_mentioned:
                                    conversation.actors_mentioned.append(actor_name)
                                logger.info("💾 Cached comparison actor: %s", actor_name)

            if not evidence:
                return {
                    "query": query_text,
                    "answer": "No relevant threat intelligence found for this query.",
                    "evidence": [],
                    "confidence": 0.0,
                    "source_count": 0,
                    "model": "N/A",
                    "timestamp": datetime.now().isoformat(),
                    "response_mode": response_mode,
                    "primary_actors": primary_actors,
                    "processing_time": time.time() - start_time,
                    "from_cache": False,
                    "query_type": query_type,
                }

            generation_start = time.time()
            retrieval_mode = retrieval_result.get("retrieval_mode", "hybrid")

            if query_type == "comparison" and conversation:
                all_cached_chunks = conversation.get_all_cached_chunks()
                if len(all_cached_chunks) > 1:
                    logger.info("Generating comparison answer for %s actors", len(all_cached_chunks))
                    result = self.interpreter.comparison_answer(query_text, all_cached_chunks)
                    response_mode = "comparison"
                else:
                    result = self.interpreter.explain(query_text, evidence, response_mode=response_mode, retrieval_mode=retrieval_mode)
            else:
                result = self.interpreter.explain(query_text, evidence, response_mode=response_mode, retrieval_mode=retrieval_mode)

            generation_time = time.time() - generation_start
            logger.info("⏱️ Answer generation completed in %.2fs", generation_time)

            audit_start = time.time()
            trace_id = self.audit.log_query(query_text, result.get("query_type", query_type), evidence)
            self.audit.log_response(trace_id, result)
            audit_time = time.time() - audit_start
            logger.info("⏱️ Audit logging completed in %.2fs", audit_time)

            total_time = time.time() - start_time
            logger.info("⏱️ Total query processing time: %.2fs", total_time)

            response = {
                "query": query_text,
                "answer": result["answer"],
                "confidence": result["confidence"],
                "source_count": result["source_count"],
                "model": result.get("model", "N/A"),
                "timestamp": datetime.now().isoformat(),
                "trace_id": trace_id,
                "response_mode": response_mode,
                "query_type": query_type,
                "primary_actors": primary_actors,
                "processing_time": total_time,
                "from_cache": False,
                "timings": {
                    "retrieval": retrieval_time,
                    "generation": generation_time,
                    "audit": audit_time,
                    "total": total_time,
                },
                "evidence": [
                    {
                        "text": e["text"],
                        "score": round(e.get("similarity_score", 0), 4),
                        "source": e["metadata"].get("source_field", "unknown"),
                        "actor": e["metadata"].get("actor_name", "unknown"),
                        "links": e["metadata"].get("information_sources", []),
                    }
                    for e in evidence
                ],
            }

            if conversation:
                conversation.add_message("user", query_text)
                conversation.add_message("assistant", result["answer"])
                self.conversation_manager.save_conversation(conversation)
                logger.info("💾 Conversation saved with %s actors", len(conversation.actors_mentioned))

            response["cached_at"] = time.time()
            response["normalized_query"] = self._normalize_cache_query(query_text)
            self.cache[cache_key] = response.copy()

            if len(self.cache) > 1000:
                oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k].get("cached_at", 0))
                del self.cache[oldest_key]
                logger.info("🗑️ Cache cleaned - removed oldest entry")

            logger.info("✓ Query processed successfully")
            return response

        except Exception as exc:
            logger.error("Error processing query: %s", exc)
            return {"error": str(exc)}
