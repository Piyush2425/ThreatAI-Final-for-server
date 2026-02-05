"""BM25 keyword-based retrieval for exact term matching."""

import logging
from typing import List, Dict, Any, Tuple
import json
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import rank_bm25, fall back to simple keyword matching if not available
try:
    from rank_bm25 import BM25Okapi
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False
    logger.warning("rank_bm25 not installed, using simple keyword matching")


class BM25Retriever:
    """BM25-based retrieval for exact keyword matching."""
    
    def __init__(self, actors_data_path: str = "data/canonical/actors.json"):
        """
        Initialize BM25 retriever.
        
        Args:
            actors_data_path: Path to canonical actors JSON
        """
        self.actors_data_path = actors_data_path
        self.documents = []
        self.actor_chunks = []
        self.bm25 = None
        self._build_index()
    
    def _build_index(self):
        """Build BM25 index from actor data."""
        try:
            path = Path(self.actors_data_path)
            if not path.exists():
                logger.warning(f"Actors data not found: {self.actors_data_path}")
                return
            
            with open(path, 'r', encoding='utf-8') as f:
                actors = json.load(f)
            
            # Create text representations of each actor
            for actor in actors:
                name = actor.get('name', 'Unknown')
                primary_name = actor.get('primary_name', name)
                aliases = actor.get('aliases', [])
                countries = actor.get('countries', [])
                description = actor.get('description', '')
                information_sources = actor.get('information_sources', [])
                last_updated = (
                    actor.get('last_updated')
                    or actor.get('last_card_change')
                    or actor.get('last-card-change')
                )
                
                # Build searchable text
                text_parts = [name, primary_name]
                text_parts.extend(aliases)
                text_parts.extend(countries)
                text_parts.append(description)
                
                # Add other fields
                for field in ['motivations', 'targets', 'first_seen', 'last_seen']:
                    value = actor.get(field)
                    if value:
                        if isinstance(value, list):
                            text_parts.extend([str(v) for v in value])
                        else:
                            text_parts.append(str(value))

                if last_updated:
                    text_parts.append(str(last_updated))
                
                full_text = ' '.join(str(p) for p in text_parts if p)
                
                # Store document and metadata
                self.actor_chunks.append({
                    'text': full_text,
                    'actor_id': actor.get('id', ''),
                    'actor_name': name,
                    'primary_name': primary_name,
                    'aliases': aliases,
                    'countries': countries,
                    'information_sources': information_sources
                })
                
                # Tokenize for BM25 (simple whitespace + lowercase)
                tokens = full_text.lower().split()
                self.documents.append(tokens)
            
            # Build BM25 index if library available
            if HAS_BM25 and self.documents:
                self.bm25 = BM25Okapi(self.documents)
                logger.info(f"Built BM25 index with {len(self.documents)} actors")
            else:
                logger.info(f"Using simple keyword matching for {len(self.documents)} actors")
                
        except Exception as e:
            logger.error(f"Error building BM25 index: {e}")
            raise
    
    def search(self, query: str, k: int = 5) -> List[Tuple[Dict[str, Any], float]]:
        """
        Search using BM25 keyword matching.
        
        Args:
            query: Query string
            k: Number of results to return
            
        Returns:
            List of (chunk, score) tuples
        """
        if not self.documents:
            return []
        
        query_tokens = query.lower().split()
        
        if HAS_BM25 and self.bm25:
            # Use BM25 scoring
            scores = self.bm25.get_scores(query_tokens)
            
            # Get top-k indices
            top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
            
            results = []
            for idx in top_indices:
                if scores[idx] > 0:  # Only include non-zero scores
                    chunk = self.actor_chunks[idx].copy()
                    # Normalize BM25 score to 0-1 range (rough approximation)
                    normalized_score = min(scores[idx] / 10.0, 1.0)
                    results.append((chunk, normalized_score))
            
            return results
        else:
            # Fallback: simple keyword matching
            return self._simple_keyword_search(query_tokens, k)
    
    def _simple_keyword_search(self, query_tokens: List[str], k: int = 5) -> List[Tuple[Dict[str, Any], float]]:
        """Simple keyword matching fallback."""
        results = []
        
        for idx, doc_tokens in enumerate(self.documents):
            # Count matching tokens
            matches = sum(1 for qt in query_tokens if qt in doc_tokens)
            
            if matches > 0:
                score = matches / len(query_tokens)  # Simple relevance score
                chunk = self.actor_chunks[idx].copy()
                results.append((chunk, score))
        
        # Sort by score and return top-k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:k]
    
    def get_size(self) -> int:
        """Get number of indexed documents."""
        return len(self.documents)
