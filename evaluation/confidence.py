"""Calculate confidence and coverage metrics."""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class ConfidenceCalculator:
    """Calculate confidence scores for responses."""
    
    @staticmethod
    def calculate_coverage(evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate evidence coverage metrics.
        
        Args:
            evidence: List of evidence chunks
            
        Returns:
            Coverage metrics
        """
        if not evidence:
            return {
                'coverage_score': 0.0,
                'source_diversity': 0.0,
                'evidence_count': 0,
                'unique_sources': 0,
            }
        
        # Count unique source fields
        source_fields = {}
        for chunk in evidence:
            field = chunk['metadata'].get('source_field', 'unknown')
            source_fields[field] = source_fields.get(field, 0) + 1
        
        unique_sources = len(source_fields)
        total_evidence = len(evidence)
        
        # Coverage score: more sources and more evidence = higher score
        coverage_score = min(
            (unique_sources / 5.0) * 0.5 + (total_evidence / 10.0) * 0.5,
            1.0
        )
        
        # Source diversity: how evenly distributed are sources?
        if unique_sources > 0:
            max_from_one_source = max(source_fields.values())
            diversity = 1.0 - (max_from_one_source / total_evidence)
        else:
            diversity = 0.0
        
        return {
            'coverage_score': coverage_score,
            'source_diversity': diversity,
            'evidence_count': total_evidence,
            'unique_sources': unique_sources,
            'source_breakdown': source_fields,
        }
    
    @staticmethod
    def calculate_quality(evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate quality metrics for evidence.
        
        Args:
            evidence: List of evidence chunks
            
        Returns:
            Quality metrics
        """
        if not evidence:
            return {
                'avg_similarity': 0.0,
                'min_similarity': 0.0,
                'max_similarity': 0.0,
                'quality_score': 0.0,
            }
        
        similarities = [chunk.get('similarity_score', 0.5) for chunk in evidence]
        
        avg_similarity = sum(similarities) / len(similarities)
        min_similarity = min(similarities)
        max_similarity = max(similarities)
        
        # Quality score based on consistency of similarity scores
        variance = sum((s - avg_similarity) ** 2 for s in similarities) / len(similarities)
        consistency = 1.0 / (1.0 + variance)
        
        quality_score = (avg_similarity * 0.7) + (consistency * 0.3)
        
        return {
            'avg_similarity': avg_similarity,
            'min_similarity': min_similarity,
            'max_similarity': max_similarity,
            'consistency': consistency,
            'quality_score': quality_score,
        }
