"""Intent Detection Module for User Queries and Conversation Context.

Handles detection of:
- Report generation requests (explicit and implicit)
- Threat intelligence context terms
- Simple user confirmations
- Report suggestions from assistant
"""

import re
from typing import Optional


def is_report_request(query: str) -> bool:
    """Detect whether user explicitly asks for a downloadable/report output.
    
    Args:
        query: User message text
        
    Returns:
        True if query contains report/export/download intent keywords
    """
    if not query:
        return False

    normalized = query.lower()

    # Keep this intent strict: only show report actions on explicit export/report ask.
    patterns = [
        r'\bpdf\b',
        r'\breport\b',
        r'\bdownload\b',
        r'\bexport\b',
        r'\bdownloadable\b',
        r'\bgenerate\s+(a\s+)?(pdf|report)\b',
        r'\bmake\s+(it\s+)?(a\s+)?(pdf|report)\b',
    ]

    return any(re.search(pattern, normalized) for pattern in patterns)


def contains_threat_context_terms(query: str) -> bool:
    """Check if text includes threat-intel domain terms that can drive retrieval.
    
    Args:
        query: User message text
        
    Returns:
        True if query contains threat intelligence relevant keywords
    """
    if not query:
        return False

    normalized = query.lower()
    patterns = [
        r'\bapt\d*\b',
        r'\blazarus\b',
        r'\brevil\b',
        r'\bturla\b',
        r'\bemotet\b',
        r'\bthreat\b',
        r'\bactor\b',
        r'\bmalware\b',
        r'\bransomware\b',
        r'\bttp\b',
        r'\bvulnerabilit(?:y|ies)\b',
        r'\bcve-\d{4}-\d+\b',
        r'\bio(?:c|cs)\b',
        r'\bcampaign\b',
        r'\binfrastructure\b',
    ]
    return any(re.search(pattern, normalized) for pattern in patterns)


def is_short_report_followup(query: str) -> bool:
    """Heuristic for short report confirmations like 'yes generate report'.
    
    Args:
        query: User message text
        
    Returns:
        True if query is short and contains report intent
    """
    if not query:
        return False
    return len(query.split()) <= 7 and is_report_request(query)


def is_simple_confirmation(query: str) -> bool:
    """Check if query is a simple confirmation like 'yes', 'ok', 'proceed', 'sure'.
    
    Args:
        query: User message text
        
    Returns:
        True if query is a simple affirmative confirmation
    """
    if not query:
        return False
    normalized = query.lower().strip()
    confirmations = {
        'yes', 'ok', 'okay', 'proceed', 'sure', 'yep',
        'go ahead', 'do it', 'generate', 'generate report'
    }
    return normalized in confirmations or len(normalized.split()) <= 2


def get_latest_substantive_user_query(conversation, current_user_message: str) -> str:
    """Find the most recent non-report user query to reuse for report generation.
    
    Traverses conversation history backwards to find the last user message
    that contains actual threat intelligence content (not a report request/confirmation).
    
    Args:
        conversation: Conversation object with messages list
        current_user_message: The current user message to skip
        
    Returns:
        Previous substantive user query, or empty string if none found
    """
    if not conversation or not getattr(conversation, 'messages', None):
        return ''

    # Traverse from newest to oldest and skip the current user message.
    skipped_current = False
    for message in reversed(conversation.messages):
        if message.get('role') != 'user':
            continue

        content = (message.get('content') or '').strip()
        if not content:
            continue

        if not skipped_current and content == current_user_message:
            skipped_current = True
            continue

        if not is_report_request(content):
            return content

    return ''


def last_assistant_message_had_report_suggestion(conversation) -> bool:
    """Check if the most recent assistant message offered a report suggestion.
    
    Args:
        conversation: Conversation object with messages list
        
    Returns:
        True if last assistant message had report_suggestion=True in metadata
    """
    if not conversation or not getattr(conversation, 'messages', None):
        return False
    
    # Find the most recent assistant message
    for message in reversed(conversation.messages):
        if message.get('role') == 'assistant':
            metadata = message.get('metadata') or {}
            return bool(metadata.get('report_suggestion'))
    
    return False


def should_offer_report_suggestion(result: dict, report_requested: bool) -> bool:
    """Offer a report CTA when we have useful evidence but no explicit report ask.
    
    Args:
        result: Query result with confidence and evidence
        report_requested: Whether user already explicitly asked for report
        
    Returns:
        True if we should offer a report suggestion to the user
    """
    if report_requested:
        return False
    if not result:
        return False

    source_count = result.get('source_count', 0) or 0
    confidence = result.get('confidence', 0.0) or 0.0
    return source_count > 0 and confidence >= 0.25
