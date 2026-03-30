"""Detect comparison and multi-actor queries in conversations."""

import logging
import re
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class ComparisonDetector:
    """Detect and handle comparison/multi-actor queries."""
    
    # Keywords that indicate comparison queries
    COMPARISON_KEYWORDS = {
        'vs', 'versus', 'compare', 'comparison',
        'difference', 'differences', 'differ',
        'similar', 'similarity', 'similarities',
        'both', 'between', 'connection',
        'relationship', 'related', 'link',
        'contrast', 'distinguish', 'same',
        'while', 'although', 'however'
    }
    
    # Keywords indicating context switch (don't compare)
    CONTEXT_SWITCH_KEYWORDS = {
        'also', 'next', 'now', 'instead', 'rather',
        'tell me about', 'what about', 'explain',
        'describe', 'summarize'
    }
    
    @staticmethod
    def is_comparison_query(query: str) -> bool:
        """
        Determine if query is asking for comparison of multiple actors.
        
        Args:
            query: User query string
            
        Returns:
            True if query appears to be a comparison
        """
        query_lower = query.lower()
        
        # Check for explicit comparison keywords
        has_comparison = any(keyword in query_lower for keyword in ComparisonDetector.COMPARISON_KEYWORDS)
        
        if not has_comparison:
            return False
        
        # Check for context switch indicators (false positives)
        has_switch_keyword = any(
            keyword in query_lower 
            for keyword in ComparisonDetector.CONTEXT_SWITCH_KEYWORDS
        )
        
        # If it has comparison keyword but also context-switch keyword, 
        # and the context-switch comes first, it's likely a context switch
        if has_switch_keyword:
            for switch_keyword in ComparisonDetector.CONTEXT_SWITCH_KEYWORDS:
                for comp_keyword in ComparisonDetector.COMPARISON_KEYWORDS:
                    switch_idx = query_lower.find(switch_keyword)
                    comp_idx = query_lower.find(comp_keyword)
                    if switch_idx >= 0 and comp_idx >= 0 and switch_idx < comp_idx:
                        return False
        
        return True
    
    @staticmethod
    def is_context_switch(query: str, current_actor: Optional[str]) -> bool:
        """
        Determine if query is switching to a different actor context.
        
        Args:
            query: User query string
            current_actor: Currently active actor (if any)
            
        Returns:
            True if switching to a different actor
        """
        if not current_actor:
            return False
        
        # If it's a comparison query, it's not a simple context switch
        if ComparisonDetector.is_comparison_query(query):
            return False
        
        # Check for context switch keywords
        query_lower = query.lower()
        has_switch_keyword = any(
            keyword in query_lower 
            for keyword in ['also', 'next', 'now', 'instead', 'rather', 'about', 'on']
        )
        
        return has_switch_keyword
    
    @staticmethod
    def get_query_type(query: str, current_actor: Optional[str]) -> str:
        """
        Classify query type for routing.
        
        Args:
            query: User query string
            current_actor: Currently active actor (if any)
            
        Returns:
            'comparison' | 'context_switch' | 'follow_up' | 'unknown'
        """
        if ComparisonDetector.is_comparison_query(query):
            return 'comparison'
        elif ComparisonDetector.is_context_switch(query, current_actor):
            return 'context_switch'
        elif current_actor and not any(keyword in query.lower() for keyword in ['who', 'what', 'tell me', 'explain']):
            # Likely a follow-up on current actor
            return 'follow_up'
        else:
            return 'unknown'

    @staticmethod
    def extract_all_actors(query: str, alias_resolver) -> List[Dict[str, str]]:
        """
        Extract all actor mentions from query using alias resolver.
        
        Args:
            query: User query string
            alias_resolver: AliasResolver instance
            
        Returns:
            List of {matched_text, primary_name, actor_id}
        """
        if not alias_resolver:
            return []
        
        return alias_resolver.extract_actors_from_query(query)

    @staticmethod
    def format_comparison_prompt(
        query: str,
        actor1_name: str,
        actor1_chunks: List[Dict],
        actor2_name: str,
        actor2_chunks: List[Dict]
    ) -> str:
        """
        Format a comparison prompt with chunks from both actors.
        
        Args:
            query: User query
            actor1_name: First actor name
            actor1_chunks: Chunks for first actor
            actor2_name: Second actor name  
            actor2_chunks: Chunks for second actor
            
        Returns:
            Formatted comparison prompt
        """
        def format_actor_evidence(name: str, chunks: List[Dict], max_chunks: int = 3) -> str:
            """Format evidence for one actor."""
            lines = [f"\n**{name}:**"]
            for chunk in chunks[:max_chunks]:
                source = chunk['metadata'].get('source_field', 'description')
                text = chunk.get('text', '')
                if len(text) > 150:
                    text = text[:150] + "..."
                lines.append(f"- ({source}) {text}")
            return "\n".join(lines)
        
        evidence1 = format_actor_evidence(actor1_name, actor1_chunks)
        evidence2 = format_actor_evidence(actor2_name, actor2_chunks)
        
        prompt = f"""Compare {actor1_name} and {actor2_name} based on this evidence:

{evidence1}

{evidence2}

User Query: {query}

Provide a clear comparison highlighting key differences and similarities."""
        
        return prompt
