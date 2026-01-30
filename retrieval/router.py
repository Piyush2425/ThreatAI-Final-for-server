"""Query router for determining retrieval strategy."""

import logging
from typing import Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


class QueryType(Enum):
    """Types of queries the system can handle."""
    ACTOR_PROFILE = "actor_profile"
    TTP_ANALYSIS = "ttp_analysis"
    TARGET_ANALYSIS = "target_analysis"
    TIMELINE_ANALYSIS = "timeline_analysis"
    GENERAL = "general"


class QueryRouter:
    """Route queries to appropriate retrieval strategy."""
    
    # Keywords for each query type
    QUERY_KEYWORDS = {
        QueryType.ACTOR_PROFILE: ['profile', 'background', 'description', 'overview', 'history'],
        QueryType.TTP_ANALYSIS: ['technique', 'tactic', 'ttp', 'method', 'attack'],
        QueryType.TARGET_ANALYSIS: ['target', 'victim', 'industry', 'sector', 'organization'],
        QueryType.TIMELINE_ANALYSIS: ['timeline', 'first seen', 'last seen', 'activity', 'when', 'date'],
    }
    
    @staticmethod
    def classify_query(query: str) -> QueryType:
        """
        Classify query to determine retrieval strategy.
        
        Args:
            query: User query string
            
        Returns:
            QueryType classification
        """
        query_lower = query.lower()
        
        for query_type, keywords in QueryRouter.QUERY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in query_lower:
                    logger.debug(f"Classified query as {query_type.value}")
                    return query_type
        
        return QueryType.GENERAL
    
    @staticmethod
    def get_retrieval_plan(query_type: QueryType) -> Dict[str, Any]:
        """
        Get retrieval plan for query type.
        
        Args:
            query_type: Type of query
            
        Returns:
            Retrieval plan configuration
        """
        plans = {
            QueryType.ACTOR_PROFILE: {
                'top_k': 5,
                'weight_fields': {'description': 1.0, 'aliases': 0.8, 'origins': 0.6},
            },
            QueryType.TTP_ANALYSIS: {
                'top_k': 3,
                'weight_fields': {'ttps': 1.0, 'description': 0.5},
            },
            QueryType.TARGET_ANALYSIS: {
                'top_k': 4,
                'weight_fields': {'targets': 1.0, 'description': 0.5},
            },
            QueryType.TIMELINE_ANALYSIS: {
                'top_k': 3,
                'weight_fields': {'first_seen': 1.0, 'last_seen': 1.0, 'description': 0.3},
            },
            QueryType.GENERAL: {
                'top_k': 5,
                'weight_fields': {'description': 1.0},
            },
        }
        
        return plans.get(query_type, plans[QueryType.GENERAL])
