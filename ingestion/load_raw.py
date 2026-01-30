"""Load raw threat actor JSON data."""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def load_raw_actors(file_path: str) -> List[Dict[str, Any]]:
    """
    Load threat actor profiles from raw JSON file.
    
    Args:
        file_path: Path to the raw JSON file
        
    Returns:
        List of threat actor profiles
    """
    path = Path(file_path)
    
    if not path.exists():
        logger.warning(f"Raw data file not found: {file_path}")
        return []
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"Loaded {len(data)} threat actors from {file_path}")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        raise
    except Exception as e:
        logger.error(f"Error loading raw data: {e}")
        raise
