"""Store and manage analyst feedback."""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import uuid

logger = logging.getLogger(__name__)


class FeedbackStore:
    """Manage feedback storage and retrieval."""
    
    def __init__(self, storage_path: str = "data/feedback.jsonl"):
        """
        Initialize feedback store.
        
        Args:
            storage_path: Path to feedback storage file
        """
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
    
    def store_feedback(self, feedback: Dict[str, Any]) -> str:
        """
        Store analyst feedback.
        
        Args:
            feedback: Feedback dictionary
            
        Returns:
            Feedback ID
        """
        feedback_id = str(uuid.uuid4())
        feedback['feedback_id'] = feedback_id
        feedback['timestamp'] = datetime.utcnow().isoformat()
        
        try:
            with open(self.storage_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(feedback) + '\n')
            logger.info(f"Stored feedback: {feedback_id}")
            return feedback_id
        except Exception as e:
            logger.error(f"Failed to store feedback: {e}")
            raise
    
    def get_feedback(self, feedback_id: str) -> Dict[str, Any]:
        """
        Retrieve specific feedback.
        
        Args:
            feedback_id: Feedback ID to retrieve
            
        Returns:
            Feedback dictionary or None
        """
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                for line in f:
                    feedback = json.loads(line)
                    if feedback.get('feedback_id') == feedback_id:
                        return feedback
        except Exception as e:
            logger.error(f"Failed to retrieve feedback: {e}")
        
        return None
    
    def get_all_feedback(self) -> List[Dict[str, Any]]:
        """
        Get all feedback entries.
        
        Returns:
            List of feedback dictionaries
        """
        feedback_list = []
        try:
            if self.storage_path.exists():
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        feedback = json.loads(line)
                        feedback_list.append(feedback)
        except Exception as e:
            logger.error(f"Failed to retrieve all feedback: {e}")
        
        return feedback_list
    
    def get_feedback_for_query(self, query: str) -> List[Dict[str, Any]]:
        """
        Get feedback for a specific query.
        
        Args:
            query: Query string to filter by
            
        Returns:
            List of feedback dictionaries for the query
        """
        feedback_list = []
        for feedback in self.get_all_feedback():
            if feedback.get('query') == query:
                feedback_list.append(feedback)
        
        return feedback_list
