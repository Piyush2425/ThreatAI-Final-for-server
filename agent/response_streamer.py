"""Response Streaming Module for Token-by-Token Progressive Reveal.

Handles generation of complete responses and chunks them for frontend streaming.
Creates illusion of real-time generation while working with cached/complete responses.
"""

import json
import re
from typing import List, Dict, Generator


class ResponseStreamer:
    """Chunks responses into tokens for progressive client-side reveal."""
    
    # Configuration for streaming behavior
    CONFIG = {
        'token_delay_ms': 50,          # Delay between tokens (50ms = natural speed)
        'sentence_delay_multiplier': 2, # Double delay at sentence end (period/question mark)
        'paragraph_delay_multiplier': 4, # Quadruple delay at paragraph end
    }
    
    @staticmethod
    def split_into_tokens(text: str) -> List[str]:
        """Split text into stream-safe tokens while preserving exact spacing.

        Uses regex tokenization that keeps whitespace as separate tokens so
        progressive concatenation reproduces the original text exactly.
        
        Args:
            text: Full response text
            
        Returns:
            List of tokens including whitespace segments
        """
        if not text:
            return []

        # Capture either runs of whitespace or runs of non-whitespace chars.
        return re.findall(r'\s+|\S+', text)
    
    @staticmethod
    def create_stream_chunks(
        answer_text: str,
        followup_questions: List[str],
        metadata: Dict,
        chunk_size: int = 1
    ) -> Generator[Dict, None, None]:
        """Generate stream chunks for progressive frontend reveal.
        
        Yields chunks containing:
        - Answer tokens (progressive)
        - Metadata only on completion
        - Follow-up questions after answer done
        
        Args:
            answer_text: Full assistant answer
            followup_questions: List of follow-up question suggestions
            metadata: Response metadata (confidence, evidence, etc.)
            chunk_size: Tokens per chunk (1 = most fluid)
            
        Yields:
            Dict chunks for streaming to client
        """
        tokens = ResponseStreamer.split_into_tokens(answer_text)
        
        if not tokens:
            yield {
                'type': 'complete',
                'metadata': metadata,
                'followup_questions': followup_questions,
            }
            return
        
        # Stream answer tokens
        for i in range(0, len(tokens), chunk_size):
            chunk_tokens = tokens[i:i+chunk_size]
            token_text = ''.join(chunk_tokens)
            
            # Calculate delay based on token content
            delay = ResponseStreamer.CONFIG['token_delay_ms']
            stripped = token_text.strip()
            if '\n\n' in token_text:
                delay = ResponseStreamer.CONFIG['token_delay_ms'] * ResponseStreamer.CONFIG['paragraph_delay_multiplier']
            elif stripped.endswith(('.', '!', '?')):
                delay = ResponseStreamer.CONFIG['token_delay_ms'] * ResponseStreamer.CONFIG['sentence_delay_multiplier']
            
            yield {
                'type': 'token',
                'token': token_text,
                'delay_ms': delay,
                'progress': (i + chunk_size) / len(tokens),  # 0.0 to 1.0
            }
        
        # Signal answer complete, return metadata and suggestions
        yield {
            'type': 'complete',
            'metadata': metadata,
            'followup_questions': followup_questions,
        }
    
    @staticmethod
    def serialize_stream_chunk(chunk: Dict) -> str:
        """Serialize chunk to JSON for SSE transmission.
        
        Args:
            chunk: Chunk dict from create_stream_chunks
            
        Returns:
            JSON string for sending over SSE
        """
        return json.dumps(chunk)
