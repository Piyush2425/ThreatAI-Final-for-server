"""Audit trails and traceability."""

import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import uuid

logger = logging.getLogger(__name__)


class AuditTrail:
    """Maintain audit trail for traceability."""
    
    def __init__(self, audit_log_path: str = "logs/audit.jsonl"):
        """
        Initialize audit trail.
        
        Args:
            audit_log_path: Path to audit log file
        """
        self.audit_log_path = Path(audit_log_path)
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    
    def log_query(self, query: str, query_type: str, evidence: List[Dict[str, Any]]) -> str:
        """
        Log a query and its evidence.
        
        Args:
            query: Query string
            query_type: Type of query
            evidence: Retrieved evidence
            
        Returns:
            Query trace ID
        """
        trace_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()
        
        log_entry = {
            'trace_id': trace_id,
            'timestamp': timestamp,
            'query': query,
            'query_type': query_type,
            'evidence_count': len(evidence),
            'evidence_ids': [chunk.get('chunk_id', 'unknown') for chunk in evidence],
        }
        
        self._write_audit_log(log_entry)
        logger.debug(f"Logged query trace: {trace_id}")
        
        return trace_id
    
    def log_response(self, trace_id: str, response: Dict[str, Any]) -> None:
        """
        Log response for a trace.
        
        Args:
            trace_id: Query trace ID
            response: Response dictionary
        """
        log_entry = {
            'event': 'response',
            'trace_id': trace_id,
            'timestamp': datetime.utcnow().isoformat(),
            'confidence': response.get('confidence', 0.0),
            'answer_length': len(response.get('answer', '')),
        }
        
        self._write_audit_log(log_entry)
    
    def log_feedback(self, trace_id: str, feedback: Dict[str, Any]) -> None:
        """
        Log feedback for a trace.
        
        Args:
            trace_id: Query trace ID
            feedback: Feedback dictionary
        """
        log_entry = {
            'event': 'feedback',
            'trace_id': trace_id,
            'timestamp': datetime.utcnow().isoformat(),
            'rating': feedback.get('rating', 0),
            'relevance': feedback.get('relevance', 'unknown'),
            'accuracy': feedback.get('accuracy', 'unknown'),
        }
        
        self._write_audit_log(log_entry)
    
    def _write_audit_log(self, entry: Dict[str, Any]) -> None:
        """Write entry to audit log."""
        try:
            with open(self.audit_log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
    
    def get_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        """
        Get all events for a trace.
        
        Args:
            trace_id: Query trace ID
            
        Returns:
            List of events for the trace
        """
        events = []
        try:
            if self.audit_log_path.exists():
                with open(self.audit_log_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        entry = json.loads(line)
                        if entry.get('trace_id') == trace_id:
                            events.append(entry)
        except Exception as e:
            logger.error(f"Failed to retrieve trace: {e}")
        
        return events
