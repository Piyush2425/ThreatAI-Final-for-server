"""Evidence selection and retrieval with hybrid search."""

import logging
from typing import List, Dict, Any, Tuple, Optional
from .router import QueryRouter
from .alias_resolver import AliasResolver
from .query_parser import QueryParser
from .bm25_retriever import BM25Retriever

logger = logging.getLogger(__name__)


class EvidenceRetriever:
    """Select relevant evidence chunks using hybrid retrieval."""
    
    def __init__(self, vector_store, embedder, bm25_weight: float = 0.3, vector_weight: float = 0.7):
        """
        Initialize hybrid retriever.
        
        Args:
            vector_store: VectorStore instance
            embedder: LocalEmbedder instance
            bm25_weight: Weight for BM25 scores (default 0.3)
            vector_weight: Weight for vector similarity scores (default 0.7)
        """
        self.vector_store = vector_store
        self.embedder = embedder
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight
        
        # Initialize alias resolver and query parser
        try:
            self.alias_resolver = AliasResolver()
            self.query_parser = QueryParser(self.alias_resolver)
            logger.info("Initialized alias resolver and query parser")
        except Exception as e:
            logger.warning(f"Could not initialize alias resolver: {e}")
            self.alias_resolver = None
            self.query_parser = None
        
        # Initialize BM25 retriever
        try:
            self.bm25_retriever = BM25Retriever()
            logger.info(f"Initialized BM25 retriever with {self.bm25_retriever.get_size()} documents")
        except Exception as e:
            logger.warning(f"Could not initialize BM25 retriever: {e}")
            self.bm25_retriever = None
    
    def retrieve(self, query: str, top_k: int = 5, similarity_threshold: float = 0.6) -> List[Dict[str, Any]]:
        """
        Retrieve evidence chunks using hybrid search (BM25 + Vector).
        
        Args:
            query: Query string
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score
            
        Returns:
            List of relevant chunks with metadata
        """
        # Parse query to extract entities and intent
        parsed_query = None
        metadata_filter = None
        
        if self.query_parser:
            try:
                parsed_query = self.query_parser.parse(query)
                logger.info(f"Parsed query: actors={len(parsed_query.get('actors', []))}, intent={parsed_query.get('intent')}")
                
                # Build metadata filter if specific actors mentioned
                if self.query_parser.should_use_metadata_filter(parsed_query):
                    metadata_filter = self.query_parser.build_metadata_filter(parsed_query)
                    logger.info(f"Using metadata filter: {metadata_filter}")
            except Exception as e:
                logger.warning(f"Query parsing failed: {e}")
        
        # Classify query for retrieval plan
        query_type = QueryRouter.classify_query(query)
        retrieval_plan = QueryRouter.get_retrieval_plan(query_type)
        
        # Get results from both retrievers
        vector_results = self._vector_search(query, retrieval_plan['top_k'] * 2, metadata_filter)
        
        # If metadata filter was applied and returned nothing, it means specific actor was requested but not found
        # In this case, do NOT fall back to BM25 (would mix in other actors)
        # Instead, return empty to let user know specific actor has no data
        if not vector_results and metadata_filter:
            logger.info(f"No results for metadata filter: {metadata_filter}")
            bm25_results = []
        else:
            # Only use BM25 if no specific actor filter OR if vector search had results
            bm25_results = self._bm25_search(query, retrieval_plan['top_k'] * 2) if self.bm25_retriever else []

        # If a specific actor was requested, filter BM25 results to that actor
        if bm25_results and parsed_query and parsed_query.get('actors'):
            allowed_primaries = {
                actor.get('primary_name') for actor in parsed_query.get('actors', []) if actor.get('primary_name')
            }
            if allowed_primaries:
                bm25_results = [
                    (chunk, score)
                    for chunk, score in bm25_results
                    if chunk.get('primary_name') in allowed_primaries
                ]
        
        logger.info(f"Retrieved {len(vector_results)} vector results, {len(bm25_results)} BM25 results")
        
        # Combine and rerank results
        combined_results = self._hybrid_rerank(vector_results, bm25_results, top_k)
        
        # Filter by threshold
        allowed_names = set()
        if parsed_query and parsed_query.get('actors'):
            for actor in parsed_query.get('actors', []):
                primary = actor.get('primary_name')
                matched = actor.get('matched_text')
                if primary:
                    allowed_names.add(primary.lower())
                if matched:
                    allowed_names.add(matched.lower())

        evidence = []
        for chunk, score in combined_results:
            if allowed_names:
                metadata = chunk.get('metadata', {}) if isinstance(chunk, dict) else {}
                primary_name = (metadata.get('primary_name') or '').lower()
                actor_name = (metadata.get('actor_name') or '').lower()
                if primary_name not in allowed_names and actor_name not in allowed_names:
                    continue
            if score >= similarity_threshold:
                chunk_with_score = chunk.copy()
                chunk_with_score['similarity_score'] = score
                chunk_with_score['query_type'] = query_type.value
                if parsed_query:
                    chunk_with_score['matched_actors'] = parsed_query.get('actors', [])
                # Enrich with information sources if missing
                metadata = chunk_with_score.get('metadata', {}) if isinstance(chunk_with_score, dict) else {}
                if metadata is not None:
                    info_sources = metadata.get('information_sources', [])
                    if (not info_sources) and self.alias_resolver:
                        actor_name = metadata.get('primary_name') or metadata.get('actor_name')
                        if actor_name:
                            info_sources = self.alias_resolver.get_information_sources(actor_name)
                            if info_sources:
                                metadata['information_sources'] = info_sources
                    chunk_with_score['metadata'] = metadata
                evidence.append(chunk_with_score)
                
                if len(evidence) >= top_k:
                    break

        # Ensure last_updated is included for matched actors when available
        if parsed_query and parsed_query.get('actors') and self.alias_resolver:
            for actor in parsed_query.get('actors', []):
                primary_name = actor.get('primary_name')
                if not primary_name:
                    continue
                already_present = any(
                    (chunk.get('metadata', {}).get('source_field') == 'last_updated'
                     and chunk.get('metadata', {}).get('primary_name') == primary_name)
                    for chunk in evidence
                )
                if already_present:
                    continue
                last_updated = self.alias_resolver.get_last_updated(primary_name)
                if last_updated:
                    evidence.append({
                        'chunk_id': f"last_updated::{primary_name}",
                        'actor_id': actor.get('actor_id', ''),
                        'text': str(last_updated),
                        'metadata': {
                            'source_field': 'last_updated',
                            'chunk_type': 'atomic',
                            'chunk_index': 0,
                            'actor_name': actor.get('matched_text', primary_name),
                            'primary_name': primary_name,
                            'aliases': [],
                            'countries': []
                        },
                        'similarity_score': 0.95,
                        'query_type': query_type.value,
                        'matched_actors': parsed_query.get('actors', [])
                    })
        
        logger.info(f"Retrieved {len(evidence)} evidence chunks (vector={len(vector_results)}, bm25={len(bm25_results)})")
        
        # Extract response mode from parsed query
        response_mode = parsed_query.get('response_mode', 'adaptive') if parsed_query else 'adaptive'
        
        # Return evidence with metadata for adaptive responses
        return {
            'evidence': evidence,
            'response_mode': response_mode,
            'parsed_query': parsed_query
        }
    
    def _vector_search(self, query: str, k: int, metadata_filter: Optional[Dict] = None) -> List[Tuple[Dict[str, Any], float]]:
        """Perform vector similarity search."""
        try:
            query_embedding = self.embedder.embed_text(query)
            results = self.vector_store.search(query_embedding.tolist(), k=k, where=metadata_filter)
            return results
        except Exception as e:
            logger.error(f"Vector search error: {e}")
            return []
    
    def _bm25_search(self, query: str, k: int) -> List[Tuple[Dict[str, Any], float]]:
        """Perform BM25 keyword search."""
        if not self.bm25_retriever:
            return []
        
        try:
            return self.bm25_retriever.search(query, k=k)
        except Exception as e:
            logger.error(f"BM25 search error: {e}")
            return []
    
    def _hybrid_rerank(self, vector_results: List[Tuple[Dict, float]], 
                       bm25_results: List[Tuple[Dict, float]], 
                       top_k: int) -> List[Tuple[Dict, float]]:
        """
        Combine BM25 and vector search results with weighted scoring.
        
        Args:
            vector_results: Results from vector search
            bm25_results: Results from BM25 search
            top_k: Number of results to return
            
        Returns:
            Reranked results
        """
        # Build score maps
        vector_scores = {}
        bm25_scores = {}
        all_chunks = {}
        
        for chunk, score in vector_results:
            chunk_id = chunk.get('chunk_id') or chunk.get('actor_id', '')
            vector_scores[chunk_id] = score
            all_chunks[chunk_id] = chunk
        
        for chunk, score in bm25_results:
            chunk_id = chunk.get('actor_id', '')  # BM25 returns actor-level data
            bm25_scores[chunk_id] = score
            if chunk_id not in all_chunks:
                # Convert BM25 chunk format to match vector chunk format
                all_chunks[chunk_id] = {
                    'chunk_id': chunk_id,
                    'actor_id': chunk_id,
                    'text': chunk['text'],
                    'metadata': {
                        'actor_name': chunk.get('actor_name', ''),
                        'primary_name': chunk.get('primary_name', ''),
                        'aliases': chunk.get('aliases', []),
                        'countries': chunk.get('countries', []),
                        'source_field': 'bm25',
                        'chunk_type': 'entity_level',
                        'chunk_index': 0
                    }
                }
        
        # Combine scores
        combined = []
        for chunk_id, chunk in all_chunks.items():
            vector_score = vector_scores.get(chunk_id, 0.0)
            bm25_score = bm25_scores.get(chunk_id, 0.0)
            
            # Weighted combination
            hybrid_score = (self.vector_weight * vector_score) + (self.bm25_weight * bm25_score)
            combined.append((chunk, hybrid_score))
        
        # Sort by hybrid score
        combined.sort(key=lambda x: x[1], reverse=True)
        
        return combined[:top_k]
    
    def format_evidence(self, evidence: List[Dict[str, Any]]) -> str:
        """
        Format evidence for presentation.
        
        Args:
            evidence: List of evidence chunks
            
        Returns:
            Formatted evidence string
        """
        if not evidence:
            return "No evidence found."
        
        formatted = []
        for i, chunk in enumerate(evidence, 1):
            formatted.append(f"[{i}] (Score: {chunk['similarity_score']:.2f}) {chunk['text']}")
        
        return "\n".join(formatted)
