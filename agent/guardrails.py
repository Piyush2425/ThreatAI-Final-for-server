"""Guardrails for confidence and uncertainty handling."""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class ConfidenceGuardrail:
    """Ensure confidence claims are grounded in evidence."""
    
    # Confidence thresholds
    HIGH_CONFIDENCE_THRESHOLD = 0.8
    MEDIUM_CONFIDENCE_THRESHOLD = 0.6
    LOW_CONFIDENCE_THRESHOLD = 0.3
    
    @staticmethod
    def assess_confidence(evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Assess confidence level based on evidence.
        
        Args:
            evidence: List of evidence chunks
            
        Returns:
            Confidence assessment with reasoning
        """
        if not evidence:
            return {
                'level': 'none',
                'score': 0.0,
                'reason': 'No evidence provided',
                'recommendation': 'Insufficient data for analysis',
            }
        
        # Calculate average similarity
        avg_similarity = sum(
            chunk.get('similarity_score', 0.5) for chunk in evidence
        ) / len(evidence)
        
        # Consider number of sources
        source_count = len(evidence)
        source_bonus = min(source_count / 5.0, 0.2)  # Max +0.2 for multiple sources
        
        final_score = min(avg_similarity + source_bonus, 1.0)
        
        # Determine confidence level
        if final_score >= ConfidenceGuardrail.HIGH_CONFIDENCE_THRESHOLD:
            level = 'high'
        elif final_score >= ConfidenceGuardrail.MEDIUM_CONFIDENCE_THRESHOLD:
            level = 'medium'
        elif final_score >= ConfidenceGuardrail.LOW_CONFIDENCE_THRESHOLD:
            level = 'low'
        else:
            level = 'very_low'
        
        return {
            'level': level,
            'score': final_score,
            'avg_similarity': avg_similarity,
            'source_count': source_count,
            'reason': f"Based on {source_count} sources with avg similarity {avg_similarity:.2f}",
            'recommendation': ConfidenceGuardrail._get_recommendation(level),
        }
    
    @staticmethod
    def _get_recommendation(level: str) -> str:
        """Get recommendation based on confidence level."""
        recommendations = {
            'high': 'Safe for operational use',
            'medium': 'Suitable for analysis with caveats',
            'low': 'Requires additional verification',
            'very_low': 'Insufficient for actionable intelligence',
            'none': 'No analysis possible',
        }
        return recommendations.get(level, 'Unknown')


class UncertaintyHandler:
    """Handle and communicate uncertainty."""
    
    @staticmethod
    def flag_gaps(evidence: List[Dict[str, Any]], query_type: str) -> List[str]:
        """
        Flag information gaps for a query.
        
        Args:
            evidence: List of evidence chunks
            query_type: Type of query being answered
            
        Returns:
            List of potential information gaps
        """
        gaps = []
        
        source_fields = set(
            chunk['metadata'].get('source_field', '') for chunk in evidence
        )
        
        # Check for expected fields based on query type
        expected_fields = {
            'actor_profile': ['name', 'description', 'origins'],
            'ttp_analysis': ['ttps', 'description'],
            'target_analysis': ['targets', 'description'],
            'timeline_analysis': ['first_seen', 'last_seen'],
        }
        
        expected = set(expected_fields.get(query_type, []))
        missing = expected - source_fields
        
        for field in missing:
            gaps.append(f"Missing information about {field}")
        
        return gaps
    
    @staticmethod
    def add_caveats(explanation: Dict[str, Any], gaps: List[str]) -> Dict[str, Any]:
        """
        Add caveats to explanation based on gaps.
        
        Args:
            explanation: Explanation response
            gaps: List of information gaps
            
        Returns:
            Explanation with added caveats
        """
        if gaps:
            caveat_text = "Note: " + "; ".join(gaps)
            explanation['caveats'] = caveat_text
        
        return explanation
