"""Schema validation for threat actor data."""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from jsonschema import validate, ValidationError

logger = logging.getLogger(__name__)


def load_schema(schema_path: str) -> Dict[str, Any]:
    """Load JSON schema for validation."""
    with open(schema_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def validate_actor(actor: Dict[str, Any], schema: Dict[str, Any]) -> bool:
    """
    Validate a single threat actor against schema.
    
    Args:
        actor: Threat actor profile to validate
        schema: JSON schema for validation
        
    Returns:
        True if valid, False otherwise
    """
    try:
        validate(instance=actor, schema=schema)
        return True
    except ValidationError as e:
        logger.warning(f"Validation error for actor: {e.message}")
        return False


def validate_actors(actors: List[Dict[str, Any]], schema: Dict[str, Any]) -> tuple:
    """
    Validate a list of threat actors.
    
    Args:
        actors: List of threat actor profiles
        schema: JSON schema for validation
        
    Returns:
        Tuple of (valid_actors, invalid_count)
    """
    valid = []
    invalid_count = 0
    
    for actor in actors:
        if validate_actor(actor, schema):
            valid.append(actor)
        else:
            invalid_count += 1
    
    if invalid_count > 0:
        logger.warning(f"Validation failed for {invalid_count} actors")
    
    return valid, invalid_count
