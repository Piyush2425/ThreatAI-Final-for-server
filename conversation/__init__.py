"""Conversation Management for Threat-AI Chat System."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


class ConversationManager:
    """Manages chat conversations with context retention."""
    
    def __init__(self, storage_dir: str = "data/conversations"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.active_conversations: Dict[str, 'Conversation'] = {}
    
    def create_conversation(self, title: str = "New Chat") -> str:
        """Create a new conversation and return its ID."""
        conv_id = str(uuid.uuid4())
        conversation = Conversation(conv_id, title)
        self.active_conversations[conv_id] = conversation
        return conv_id
    
    def get_conversation(self, conv_id: str) -> Optional['Conversation']:
        """Get conversation by ID, load from disk if needed."""
        if conv_id in self.active_conversations:
            return self.active_conversations[conv_id]
        
        # Try loading from disk
        conv_file = self.storage_dir / f"{conv_id}.json"
        if conv_file.exists():
            conversation = Conversation.load_from_file(str(conv_file))
            self.active_conversations[conv_id] = conversation
            return conversation
        
        return None
    
    def save_conversation(self, conv_id: str):
        """Save conversation to disk."""
        conversation = self.active_conversations.get(conv_id)
        if conversation:
            conv_file = self.storage_dir / f"{conv_id}.json"
            conversation.save_to_file(str(conv_file))
    
    def list_conversations(self, limit: int = 50) -> List[Dict]:
        """List all conversations (from disk)."""
        conversations = []
        for conv_file in sorted(self.storage_dir.glob("*.json"), 
                               key=lambda x: x.stat().st_mtime, 
                               reverse=True)[:limit]:
            try:
                with open(conv_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    conversations.append({
                        'id': data['id'],
                        'title': data['title'],
                        'created_at': data['created_at'],
                        'updated_at': data['updated_at'],
                        'message_count': len(data['messages'])
                    })
            except Exception:
                continue
        return conversations
    
    def delete_conversation(self, conv_id: str) -> bool:
        """Delete a conversation."""
        conv_file = self.storage_dir / f"{conv_id}.json"
        if conv_file.exists():
            conv_file.unlink()
        if conv_id in self.active_conversations:
            del self.active_conversations[conv_id]
        return True


class Conversation:
    """Represents a single conversation with message history."""
    
    def __init__(self, conv_id: str, title: str = "New Chat"):
        self.id = conv_id
        self.title = title
        self.messages: List[Dict] = []
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
    
    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None):
        """Add a message to the conversation.
        
        Args:
            role: 'user' or 'assistant'
            content: The message content
            metadata: Optional metadata (evidence, confidence, etc.)
        """
        message = {
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {}
        }
        self.messages.append(message)
        self.updated_at = datetime.now().isoformat()
        
        # Auto-update title from first user message
        if len(self.messages) == 1 and role == 'user':
            self.title = content[:50] + ('...' if len(content) > 50 else '')
    
    def get_context_messages(self, max_messages: int = 10) -> List[Dict]:
        """Get recent messages for context (excluding metadata)."""
        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        return [{'role': m['role'], 'content': m['content']} for m in recent]
    
    def get_full_history(self) -> List[Dict]:
        """Get all messages with metadata."""
        return self.messages.copy()
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'title': self.title,
            'messages': self.messages,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
    
    def save_to_file(self, filepath: str):
        """Save conversation to JSON file."""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load_from_file(cls, filepath: str) -> 'Conversation':
        """Load conversation from JSON file."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        conv = cls(data['id'], data['title'])
        conv.messages = data['messages']
        conv.created_at = data['created_at']
        conv.updated_at = data['updated_at']
        return conv
