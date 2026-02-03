"""Query parser for extracting entities and intent from user queries."""

import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class QueryParser:
    """Parse user queries to extract entities, dates, and intent."""
    
    # Common date patterns
    DATE_PATTERNS = [
        r'\b(20\d{2})\b',  # Year: 2022
        r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),?\s+(20\d{2})\b',
        r'\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b',  # Date: 01/15/2023
        r'\bbetween\s+(20\d{2})\s+(?:and|to)\s+(20\d{2})\b',  # Range: between 2022 and 2024
        r'\bfrom\s+(20\d{2})\s+to\s+(20\d{2})\b',  # Range: from 2022 to 2024
        r'\b(20\d{2})\s*-\s*(20\d{2})\b',  # Range: 2022-2024
    ]
    
    # Query intent keywords
    INTENT_KEYWORDS = {
        'list': ['list', 'show', 'what are', 'give me', 'enumerate'],
        'explain': ['explain', 'describe', 'what is', 'tell me about', 'information about'],
        'compare': ['compare', 'difference', 'versus', 'vs', 'compared to'],
        'timeline': ['timeline', 'history', 'when', 'first seen', 'last seen', 'activity'],
        'find': ['find', 'search', 'look for', 'locate'],
    }
    
    # Specific question patterns - short, direct answers expected
    SPECIFIC_QUESTION_PATTERNS = [
        r'\b(who|what|where|when|how|why|is|does|can|have|has|did)\b.*\?',  # Question words
        r'.*\s(from|in|with|by|during|between)\s.*\?',  # Location/time questions
        r'.*(country|origin|location|founded|created|active|sector|target|based)\b.*\?',  # Specific attribute questions
    ]
    
    # Report/profile request patterns - comprehensive answers expected
    REPORT_REQUEST_PATTERNS = [
        r'\b(tell me about|give me|generate|create|write|provide|explain|describe|profile|report|summary)\b',
        r'\b(full|complete|comprehensive|detailed|in-depth)\s+(report|profile|information|analysis)\b',
        r'(everything|all information|all details)\s+(about|on|regarding)\b',
    ]
    
    # Comparison patterns
    COMPARISON_PATTERNS = [
        r'\b(compare|comparison|difference|versus|vs|similar|alike|related)\b',
        r'\b(between|against|with)\s+\w+\s+(and|vs|versus)',
    ]
    
    def __init__(self, alias_resolver=None):
        """
        Initialize query parser.
        
        Args:
            alias_resolver: AliasResolver instance for actor name extraction
        """
        self.alias_resolver = alias_resolver
    
    def parse(self, query: str) -> Dict[str, Any]:
        """
        Parse query to extract structured information.
        
        Args:
            query: User query string
            
        Returns:
            Dict with extracted entities, dates, intent, filters, and response_mode
        """
        result = {
            'original_query': query,
            'actors': [],
            'dates': [],
            'date_range': None,
            'intent': 'general',
            'response_mode': 'adaptive',  # adaptive, concise, report, comparison
            'filters': {},
            'keywords': []
        }
        
        # Extract threat actors
        if self.alias_resolver:
            actors = self.alias_resolver.extract_actors_from_query(query)
            result['actors'] = actors
        
        # Extract dates and date ranges
        dates, date_range = self._extract_dates(query)
        result['dates'] = dates
        result['date_range'] = date_range
        
        # Determine intent
        result['intent'] = self._determine_intent(query)
        
        # Detect response mode (new!)
        result['response_mode'] = self._detect_response_mode(query)
        
        # Extract other keywords
        result['keywords'] = self._extract_keywords(query)
        
        return result
    
    def _extract_dates(self, query: str) -> tuple:
        """Extract dates and date ranges from query."""
        dates = []
        date_range = None
        query_lower = query.lower()
        
        # Check for date ranges
        range_match = re.search(r'\bbetween\s+(20\d{2})\s+(?:and|to)\s+(20\d{2})\b', query_lower, re.IGNORECASE)
        if range_match:
            start_year = int(range_match.group(1))
            end_year = int(range_match.group(2))
            date_range = {'start': start_year, 'end': end_year}
            return dates, date_range
        
        range_match = re.search(r'\bfrom\s+(20\d{2})\s+to\s+(20\d{2})\b', query_lower, re.IGNORECASE)
        if range_match:
            start_year = int(range_match.group(1))
            end_year = int(range_match.group(2))
            date_range = {'start': start_year, 'end': end_year}
            return dates, date_range
        
        range_match = re.search(r'\b(20\d{2})\s*-\s*(20\d{2})\b', query_lower)
        if range_match:
            start_year = int(range_match.group(1))
            end_year = int(range_match.group(2))
            date_range = {'start': start_year, 'end': end_year}
            return dates, date_range
        
        # Extract individual years
        year_matches = re.findall(r'\b(20\d{2})\b', query)
        for year_str in year_matches:
            dates.append(int(year_str))
        
        return dates, date_range
    
    def _determine_intent(self, query: str) -> str:
        """Determine query intent from keywords."""
        query_lower = query.lower()
        
        for intent, keywords in self.INTENT_KEYWORDS.items():
            for keyword in keywords:
                if keyword in query_lower:
                    return intent
        
        return 'general'
    
    def _extract_keywords(self, query: str) -> List[str]:
        """Extract important keywords from query."""
        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
                     'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
                     'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                     'would', 'could', 'should', 'may', 'might', 'can', 'about', 'me',
                     'what', 'when', 'where', 'who', 'which', 'how', 'tell', 'give'}
        
        # Tokenize and filter
        words = re.findall(r'\b[a-z]{3,}\b', query.lower())
        keywords = [w for w in words if w not in stop_words]
        
        return keywords
    
    def _detect_response_mode(self, query: str) -> str:
        """
        Detect what type of response is needed.
        
        Args:
            query: User query string
            
        Returns:
            'concise' (short answer), 'report' (full details), 'comparison', or 'adaptive' (default)
        """
        query_lower = query.lower()
        
        # Check for comparison requests
        for pattern in self.COMPARISON_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return 'comparison'
        
        # Check for report/profile requests
        for pattern in self.REPORT_REQUEST_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return 'report'
        
        # Check for specific questions
        for pattern in self.SPECIFIC_QUESTION_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return 'concise'
        
        return 'adaptive'
    
    def should_use_metadata_filter(self, parsed: Dict[str, Any]) -> bool:
        """
        Determine if metadata filtering should be used.
        
        Args:
            parsed: Parsed query dict
            
        Returns:
            True if specific actors were mentioned
        """
        return len(parsed.get('actors', [])) > 0
    
    def build_metadata_filter(self, parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Build ChromaDB metadata filter from parsed query.
        
        Args:
            parsed: Parsed query dict
            
        Returns:
            ChromaDB where clause, or None
        """
        actors = parsed.get('actors', [])
        
        if not actors:
            return None
        
        # If single actor, use simple filter
        if len(actors) == 1:
            primary_name = actors[0]['primary_name']
            return {'primary_name': primary_name}
        
        # If multiple actors, use $or operator
        actor_filters = []
        for actor in actors:
            actor_filters.append({'primary_name': actor['primary_name']})
        
        return {'$or': actor_filters}
