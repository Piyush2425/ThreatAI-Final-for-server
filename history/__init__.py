"""Store and manage query history."""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import uuid

logger = logging.getLogger(__name__)


class QueryHistory:
    """Manage query history storage and retrieval."""
    
    def __init__(self, storage_path: str = "data/history/queries.jsonl"):
        """Initialize query history store."""
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
    
    def save_query(self, query: str, result: Dict[str, Any]) -> str:
        """
        Save query and result to history.
        
        Args:
            query: User query text
            result: Query result dictionary
            
        Returns:
            Query ID
        """
        query_id = str(uuid.uuid4())
        
        history_entry = {
            'query_id': query_id,
            'query': query,
            'answer': result.get('answer', ''),
            'confidence': result.get('confidence', 0),
            'model': result.get('model', 'N/A'),
            'source_count': result.get('source_count', 0),
            'trace_id': result.get('trace_id', ''),
            'timestamp': datetime.utcnow().isoformat(),
            'evidence_count': len(result.get('evidence', []))
        }
        
        try:
            with open(self.storage_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(history_entry, ensure_ascii=False) + '\n')
            logger.info(f"Saved query to history: {query_id}")
            return query_id
        except Exception as e:
            logger.error(f"Failed to save query history: {e}")
            raise
    
    def get_all_queries(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get all queries from history (most recent first).
        
        Args:
            limit: Number of queries to return
            offset: Number of queries to skip
            
        Returns:
            List of query history entries
        """
        queries = []
        try:
            if self.storage_path.exists():
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    all_lines = f.readlines()
                    # Reverse to get most recent first
                    for line in reversed(all_lines):
                        if line.strip():
                            queries.append(json.loads(line))
        except Exception as e:
            logger.error(f"Failed to retrieve query history: {e}")
        
        # Apply pagination
        return queries[offset:offset + limit]
    
    def get_query(self, query_id: str) -> Dict[str, Any]:
        """
        Get specific query by ID.
        
        Args:
            query_id: Query ID
            
        Returns:
            Query entry or None
        """
        try:
            if self.storage_path.exists():
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            entry = json.loads(line)
                            if entry.get('query_id') == query_id:
                                return entry
        except Exception as e:
            logger.error(f"Failed to retrieve query: {e}")
        
        return None
    
    def delete_query(self, query_id: str) -> bool:
        """
        Delete query from history.
        
        Args:
            query_id: Query ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        try:
            if not self.storage_path.exists():
                return False
            
            queries = []
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)
                        if entry.get('query_id') != query_id:
                            queries.append(entry)
            
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                for entry in queries:
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            
            logger.info(f"Deleted query from history: {query_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete query: {e}")
            return False
    
    def clear_all(self) -> bool:
        """Clear all query history."""
        try:
            self.storage_path.write_text('')
            logger.info("Cleared all query history")
            return True
        except Exception as e:
            logger.error(f"Failed to clear history: {e}")
            return False
    
    def search_queries(self, search_term: str) -> List[Dict[str, Any]]:
        """
        Search queries by text.
        
        Args:
            search_term: Text to search for
            
        Returns:
            List of matching queries
        """
        results = []
        search_lower = search_term.lower()
        
        try:
            if self.storage_path.exists():
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            entry = json.loads(line)
                            if (search_lower in entry.get('query', '').lower() or
                                search_lower in entry.get('answer', '').lower()):
                                results.append(entry)
        except Exception as e:
            logger.error(f"Failed to search queries: {e}")
        
        return list(reversed(results))  # Most recent first
    
    def get_stats(self) -> Dict[str, Any]:
        """Get query history statistics."""
        try:
            total = 0
            if self.storage_path.exists():
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    total = len(f.readlines())
            
            return {
                'total_queries': total,
                'storage_size_kb': round(self.storage_path.stat().st_size / 1024, 2) if self.storage_path.exists() else 0
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {'total_queries': 0, 'storage_size_kb': 0}
