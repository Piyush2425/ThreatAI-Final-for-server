"""Explicit chunking rules for threat actor data."""

from typing import List, Dict, Any, Tuple


class ChunkingRules:
    """Define how different fields should be chunked."""
    
    # Fields that should be treated as single chunks
    ATOMIC_FIELDS = {
        'id': True,
        'name': True,
        'first_seen': True,
        'last_seen': True,
        'last_updated': True,
        'last_card_change': True,
        'last-card-change': True,
        'sponsor': True,
        'sponsorship': True,
        'name_giver': True,
        'name-giver': True,
    }
    
    # Fields that can be split into chunks
    LIST_FIELDS = {
        'aliases': True,
        'ttps': True,
        'tactics': True,
        'targets': True,
        'tools': True,
        'campaigns': True,
        'operations': True,
        'alias_givers': True,
        'origins': True,
        'motivations': True,
        'observed_sectors': True,
        'observed-sectors': True,
        'observed_countries': True,
        'observed-countries': True,
    }
    
    # Fields that should be text-chunked
    TEXT_FIELDS = {
        'description': True,
    }
    
    @staticmethod
    def should_chunk(field_name: str) -> bool:
        """Determine if a field should be chunked."""
        return field_name in ChunkingRules.TEXT_FIELDS or field_name in ChunkingRules.LIST_FIELDS
    
    @staticmethod
    def get_field_type(field_name: str) -> str:
        """Get the type of field for chunking strategy."""
        if field_name in ChunkingRules.ATOMIC_FIELDS:
            return 'atomic'
        elif field_name in ChunkingRules.LIST_FIELDS:
            return 'list'
        elif field_name in ChunkingRules.TEXT_FIELDS:
            return 'text'
        return 'unknown'
