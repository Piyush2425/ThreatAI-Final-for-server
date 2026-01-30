"""Evidence selection and retrieval."""

import logging
from typing import List, Dict, Any, Tuple
from .router import QueryRouter

logger = logging.getLogger(__name__)


class EvidenceRetriever:
    """Select relevant evidence chunks for queries."""
    
    def __init__(self, vector_store, embedder):
        """
        Initialize retriever.
        
        Args:
            vector_store: VectorStore instance
            embedder: LocalEmbedder instance
        """
        self.vector_store = vector_store
        self.embedder = embedder
    
    def retrieve(self, query: str, top_k: int = 5, similarity_threshold: float = 0.6) -> List[Dict[str, Any]]:
        """
        Retrieve evidence chunks for a query.
        
        Args:
            query: Query string
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score
            
        Returns:
            List of relevant chunks with metadata
        """
        # Classify query
        query_type = QueryRouter.classify_query(query)
        retrieval_plan = QueryRouter.get_retrieval_plan(query_type)
        
        # Generate query embedding
        query_embedding = self.embedder.embed_text(query)
        
        # Search vector store
        results = self.vector_store.search(query_embedding.tolist(), k=retrieval_plan['top_k'])
        
        # Filter by threshold
        evidence = []
        for chunk, similarity in results:
            if similarity >= similarity_threshold:
                chunk_with_score = chunk.copy()
                chunk_with_score['similarity_score'] = similarity
                chunk_with_score['query_type'] = query_type.value
                evidence.append(chunk_with_score)
                
                if len(evidence) >= top_k:
                    break
        
        logger.debug(f"Retrieved {len(evidence)} evidence chunks for query")
        return evidence
    
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
