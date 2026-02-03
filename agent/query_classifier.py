"""Query classification to identify user intent and information needs."""

import re
import logging
from typing import Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """Types of information users can request about threat actors."""
    TACTICS = "tactics"  # TTPs, techniques, methods
    ASSOCIATIONS = "associations"  # Related actors, connections
    TARGETS = "targets"  # Victims, sectors, regions
    TOOLS = "tools"  # Malware, toolsets, infrastructure
    ORIGIN = "origin"  # Country, attribution
    CAMPAIGNS = "campaigns"  # Specific operations
    TIMELINE = "timeline"  # Activity period, first seen
    OVERVIEW = "overview"  # General profile
    ALIASES = "aliases"  # Alternative names
    CAPABILITIES = "capabilities"  # Technical sophistication
    MOTIVATION = "motivation"  # Goals, objectives
    SOURCES = "sources"  # Information sources, references


class QueryClassifier:
    """Classify user queries to understand what information they're requesting."""
    
    # Keywords for each intent type
    INTENT_KEYWORDS = {
        QueryIntent.TACTICS: [
            "tactic", "tactics", "ttp", "ttps", "technique", "techniques",
            "method", "methods", "procedure", "procedures", "attack",
            "how do they", "how does", "approach", "strategy"
        ],
        QueryIntent.ASSOCIATIONS: [
            "associated", "association", "related", "connection", "linked",
            "tied to", "work with", "collaborate", "partnership", "group",
            "similar to", "connected to", "affiliate", "between", "and"
        ],
        QueryIntent.TARGETS: [
            "target", "targets", "victim", "victims", "sector", "sectors",
            "industry", "industries", "attack who", "targeting", "focus on",
            "compromise", "attack against", "region"
        ],
        QueryIntent.TOOLS: [
            "tool", "tools", "malware", "backdoor", "trojan", "rat",
            "implant", "payload", "exploit", "software", "infrastructure",
            "c2", "command and control", "domain", "ip"
        ],
        QueryIntent.ORIGIN: [
            "origin", "country", "from", "where", "location", "nation",
            "attribution", "attributed", "state", "sponsor", "government"
        ],
        QueryIntent.CAMPAIGNS: [
            "campaign", "campaigns", "operation", "operations", "incident",
            "breach", "attack on", "specific"
        ],
        QueryIntent.TIMELINE: [
            "when", "timeline", "first seen", "active since", "history",
            "started", "began", "period", "emerged", "discovered"
        ],
        QueryIntent.ALIASES: [
            "alias", "aliases", "also known as", "aka", "other names",
            "called", "named", "alternative name"
        ],
        QueryIntent.CAPABILITIES: [
            "capability", "capabilities", "sophisticated", "advanced",
            "skill", "expertise", "level", "technical"
        ],
        QueryIntent.MOTIVATION: [
            "motivation", "motivate", "goal", "goals", "objective",
            "objectives", "purpose", "why", "intent", "aim"
        ],
        QueryIntent.SOURCES: [
            "source", "sources", "reference", "references", 
            "research paper", "documentation", "citation", "bibliography",
            "where did", "where does this come from"
        ],
    }
    
    def __init__(self):
        """Initialize the query classifier."""
        pass
    
    def classify(self, query: str) -> Dict[str, any]:
        """
        Classify a query to determine user intent.
        
        Args:
            query: User query string
            
        Returns:
            Dict with 'primary_intent', 'secondary_intents', and 'confidence'
        """
        query_lower = query.lower()
        
        # Special case: "write a report", "tell me about", "overview of" should be OVERVIEW
        overview_triggers = [
            'write a report', 'write report', 'generate report', 'create report',
            'tell me about', 'tell me everything', 'what is', 'who is',
            'overview of', 'profile of', 'information about', 'describe',
            'give me info', 'explain'
        ]
        
        if any(trigger in query_lower for trigger in overview_triggers):
            logger.info(f"Classified query as: overview (special trigger matched)")
            return {
                'primary_intent': QueryIntent.OVERVIEW,
                'secondary_intents': [],
                'confidence': 0.9,
                'all_scores': {QueryIntent.OVERVIEW: 9}
            }
        
        # Score each intent
        intent_scores = {}
        for intent, keywords in self.INTENT_KEYWORDS.items():
            score = self._calculate_intent_score(query_lower, keywords)
            if score > 0:
                intent_scores[intent] = score
        
        # Determine primary and secondary intents
        if not intent_scores:
            primary_intent = QueryIntent.OVERVIEW
            secondary_intents = []
            confidence = 0.5
        else:
            sorted_intents = sorted(intent_scores.items(), key=lambda x: x[1], reverse=True)
            primary_intent = sorted_intents[0][0]
            confidence = min(sorted_intents[0][1] / 10.0, 1.0)  # Normalize to 0-1
            
            # Secondary intents are those with score >= 50% of primary
            threshold = sorted_intents[0][1] * 0.5
            secondary_intents = [
                intent for intent, score in sorted_intents[1:]
                if score >= threshold
            ]
        
        logger.info(f"Classified query as: {primary_intent.value} (confidence: {confidence:.2f})")
        
        return {
            'primary_intent': primary_intent,
            'secondary_intents': secondary_intents,
            'confidence': confidence,
            'all_scores': intent_scores
        }
    
    def _calculate_intent_score(self, query: str, keywords: List[str]) -> int:
        """Calculate score for an intent based on keyword matches."""
        score = 0
        for keyword in keywords:
            if keyword in query:
                # Give higher score for exact phrase matches
                if f" {keyword} " in f" {query} ":
                    score += 3
                else:
                    score += 1
        return score
    
    def get_extraction_hints(self, intent: QueryIntent) -> Dict[str, any]:
        """
        Get hints for what to extract from evidence based on intent.
        
        Args:
            intent: The classified query intent
            
        Returns:
            Dict with extraction guidance
        """
        hints = {
            QueryIntent.TACTICS: {
                'focus_on': ['methods', 'techniques', 'attack vectors', 'phishing', 'exploits'],
                'look_for_patterns': [
                    r'phishing', r'spear.?phishing', r'watering.?hole',
                    r'exploit', r'0.?day', r'vulnerability', r'credential',
                    r'lateral.?movement', r'persistence'
                ],
                'response_format': 'list'
            },
            QueryIntent.ASSOCIATIONS: {
                'focus_on': ['related groups', 'connections', 'links', 'similar to'],
                'look_for_patterns': [
                    r'\{\{[^}]+\}\}',  # {{Actor Name}} pattern in description
                    r'related to', r'linked to', r'connected to', r'associated with'
                ],
                'response_format': 'list'
            },
            QueryIntent.TARGETS: {
                'focus_on': ['victims', 'sectors', 'industries', 'organizations', 'government'],
                'look_for_patterns': [
                    r'target', r'victim', r'government', r'military',
                    r'sector', r'industry', r'organization', r'embassy'
                ],
                'response_format': 'structured'
            },
            QueryIntent.TOOLS: {
                'focus_on': ['malware', 'backdoors', 'tools', 'infrastructure'],
                'look_for_patterns': [
                    r'malware', r'backdoor', r'trojan', r'RAT', r'implant',
                    r'tool', r'exploit', r'c2', r'infrastructure'
                ],
                'response_format': 'list'
            },
            QueryIntent.ORIGIN: {
                'focus_on': ['country', 'attribution', 'sponsor'],
                'look_for_patterns': [
                    r'Russia', r'China', r'Iran', r'North Korea', r'attributed',
                    r'government', r'state.?sponsored', r'GRU', r'PLA'
                ],
                'response_format': 'direct'
            },
            QueryIntent.CAMPAIGNS: {
                'focus_on': ['operations', 'incidents', 'attacks'],
                'look_for_patterns': [
                    r'operation', r'campaign', r'attack', r'incident',
                    r'breach', r'compromise'
                ],
                'response_format': 'structured'
            },
            QueryIntent.TIMELINE: {
                'focus_on': ['dates', 'first seen', 'active since'],
                'look_for_patterns': [
                    r'\d{4}', r'since', r'first', r'began', r'started',
                    r'active', r'emerged'
                ],
                'response_format': 'direct'
            },
            QueryIntent.ALIASES: {
                'focus_on': ['alternative names', 'also known as'],
                'field_preference': ['aliases', 'name'],
                'response_format': 'list'
            },
            QueryIntent.CAPABILITIES: {
                'focus_on': ['sophisticated', 'advanced', 'skilled'],
                'look_for_patterns': [
                    r'advanced', r'sophisticated', r'capable', r'skilled',
                    r'complex', r'technical'
                ],
                'response_format': 'structured'
            },
            QueryIntent.MOTIVATION: {
                'focus_on': ['goals', 'objectives', 'purpose', 'intent'],
                'look_for_patterns': [
                    r'seek', r'goal', r'objective', r'purpose', r'intent',
                    r'motive', r'espionage', r'financial', r'disruption'
                ],
                'response_format': 'structured'
            },
            QueryIntent.SOURCES: {
                'field_preference': ['information_sources'],
                'response_format': 'list'
            },
            QueryIntent.OVERVIEW: {
                'focus_on': ['all'],
                'response_format': 'comprehensive'
            }
        }
        
        return hints.get(intent, {'response_format': 'comprehensive'})
