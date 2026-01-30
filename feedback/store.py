"""Store and manage analyst feedback."""

import json
import logging
import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import uuid

logger = logging.getLogger(__name__)


class FeedbackStore:
    """Manage feedback storage and retrieval."""
    
    def __init__(self, storage_path: str = "data/feedback.jsonl", csv_path: str = "data/feedback.csv", json_path: str = "data/feedback.json"):
        """
        Initialize feedback store.
        
        Args:
            storage_path: Path to feedback storage file
        """
        self.storage_path = Path(storage_path)
        self.csv_path = Path(csv_path)
        self.json_path = Path(json_path)
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
            self._append_jsonl(feedback)
            self._append_csv(feedback)
            self._append_json_array(feedback)
            logger.info(f"Stored feedback: {feedback_id}")
            return feedback_id
        except Exception as e:
            logger.error(f"Failed to store feedback: {e}")
            raise

    def _append_jsonl(self, feedback: Dict[str, Any]) -> None:
        with open(self.storage_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(feedback, ensure_ascii=False) + '\n')

    def _append_csv(self, feedback: Dict[str, Any]) -> None:
        fieldnames = [
            'feedback_id', 'timestamp', 'query', 'answer', 'trace_id', 'model',
            'source_count', 'confidence', 'response_id', 'rating', 'relevance',
            'accuracy', 'completeness', 'comments', 'corrections'
        ]

        write_header = not self.csv_path.exists()
        with open(self.csv_path, 'a', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            row = {key: feedback.get(key) for key in fieldnames}
            writer.writerow(row)

    def _append_json_array(self, feedback: Dict[str, Any]) -> None:
        data = []
        if self.json_path.exists():
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not isinstance(data, list):
                    data = []
            except Exception:
                data = []

        data.append(feedback)
        with open(self.json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
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
