"""Normalization of threat actor data fields."""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def normalize_actor(actor: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize optional fields in threat actor profile.
    
    Args:
        actor: Threat actor profile to normalize
        
    Returns:
        Normalized threat actor profile
    """
    normalized = actor.copy()
    
    # Ensure list fields are lists
    for field in ['aliases', 'ttps', 'targets', 'origins', 'motivations']:
        if field in normalized:
            if isinstance(normalized[field], str):
                normalized[field] = [normalized[field]]
        else:
            normalized[field] = []
    
    # Normalize name field
    if 'name' in normalized and normalized['name']:
        normalized['name'] = normalized['name'].strip()
    
    # Normalize description
    if 'description' in normalized and normalized['description']:
        normalized['description'] = normalized['description'].strip()
    
    return normalized


def normalize_actors(actors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize a list of threat actor profiles.
    
    Args:
        actors: List of threat actor profiles
        
    Returns:
        List of normalized threat actor profiles
    """
    return [normalize_actor(actor) for actor in actors]
