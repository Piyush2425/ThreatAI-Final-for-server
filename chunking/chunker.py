"""Convert JSON threat actor profiles into semantic text chunks."""

import logging
import uuid
from typing import Dict, Any, List
from .rules import ChunkingRules

logger = logging.getLogger(__name__)


class SemanticChunker:
    """Convert threat actor JSON into semantic chunks."""
    
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 128, min_length: int = 50):
        """
        Initialize chunker.
        
        Args:
            chunk_size: Target size for text chunks
            chunk_overlap: Number of overlapping characters between chunks
            min_length: Minimum chunk length
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_length = min_length
    
    def chunk_actor(self, actor: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Convert a threat actor profile into semantic chunks.
        
        Args:
            actor: Threat actor profile
            
        Returns:
            List of semantic chunks with metadata
        """
        chunks = []
        actor_id = actor.get('id', 'unknown')
        
        for field_name, field_value in actor.items():
            field_type = ChunkingRules.get_field_type(field_name)
            
            if field_type == 'atomic':
                chunks.append(self._create_atomic_chunk(actor_id, field_name, field_value))
            elif field_type == 'list':
                chunks.extend(self._chunk_list_field(actor_id, field_name, field_value))
            elif field_type == 'text':
                chunks.extend(self._chunk_text_field(actor_id, field_name, field_value))
        
        return chunks
    
    def _create_atomic_chunk(self, actor_id: str, field_name: str, value: Any) -> Dict[str, Any]:
        """Create a chunk for atomic fields."""
        return {
            'chunk_id': str(uuid.uuid4()),
            'actor_id': actor_id,
            'text': f"{field_name}: {value}",
            'metadata': {
                'source_field': field_name,
                'chunk_type': 'atomic',
                'chunk_index': 0
            }
        }
    
    def _chunk_list_field(self, actor_id: str, field_name: str, items: List[Any]) -> List[Dict[str, Any]]:
        """Create chunks for list fields."""
        chunks = []
        if not items:
            return chunks
        
        chunk_text = f"{field_name}: {', '.join(str(item) for item in items)}"
        return [
            {
                'chunk_id': str(uuid.uuid4()),
                'actor_id': actor_id,
                'text': chunk_text,
                'metadata': {
                    'source_field': field_name,
                    'chunk_type': 'list',
                    'chunk_index': 0,
                    'item_count': len(items)
                }
            }
        ]
    
    def _chunk_text_field(self, actor_id: str, field_name: str, text: str) -> List[Dict[str, Any]]:
        """Split text field into semantic chunks."""
        chunks = []
        
        if not text or len(text) < self.min_length:
            return [self._create_atomic_chunk(actor_id, field_name, text)]
        
        # Simple sliding window chunking
        sentences = text.split('.')
        current_chunk = []
        current_length = 0
        chunk_index = 0
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            sentence_with_period = sentence + '.'
            if current_length + len(sentence_with_period) > self.chunk_size and current_chunk:
                chunk_text = ' '.join(current_chunk)
                if len(chunk_text) >= self.min_length:
                    chunks.append({
                        'chunk_id': str(uuid.uuid4()),
                        'actor_id': actor_id,
                        'text': chunk_text,
                        'metadata': {
                            'source_field': field_name,
                            'chunk_type': 'text',
                            'chunk_index': chunk_index
                        }
                    })
                    chunk_index += 1
                    current_chunk = [sentence_with_period]
                    current_length = len(sentence_with_period)
            else:
                current_chunk.append(sentence_with_period)
                current_length += len(sentence_with_period)
        
        # Add remaining chunk
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            if len(chunk_text) >= self.min_length:
                chunks.append({
                    'chunk_id': str(uuid.uuid4()),
                    'actor_id': actor_id,
                    'text': chunk_text,
                    'metadata': {
                        'source_field': field_name,
                        'chunk_type': 'text',
                        'chunk_index': chunk_index
                    }
                })
        
        return chunks
