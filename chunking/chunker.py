"""Convert JSON threat actor profiles into semantic text chunks."""

import logging
import uuid
import re
from typing import Dict, Any, List
from .rules import ChunkingRules

logger = logging.getLogger(__name__)


class SemanticChunker:
    """Convert threat actor JSON into semantic chunks."""
    
    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 128, min_length: int = 50, entity_level: bool = True):
        """
        Initialize chunker.
        
        Args:
            chunk_size: Target size for text chunks
            chunk_overlap: Number of overlapping characters between chunks
            min_length: Minimum chunk length
            entity_level: If True, create one chunk per actor (recommended)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_length = min_length
        self.entity_level = entity_level
    
    def _extract_related_actors(self, description: str) -> List[str]:
        """
        Extract related actor references from description.
        Pattern: {{Actor Name, Alias1, Alias2}}
        
        Args:
            description: Actor description text
            
        Returns:
            List of related actor primary names
        """
        if not description:
            return []
        
        # Pattern to match {{Actor Name, Alias1, Alias2}}
        pattern = r'\{\{([^}]+)\}\}'
        matches = re.findall(pattern, description)
        
        related = []
        for match in matches:
            # Split by comma and take first element as primary name
            parts = [p.strip() for p in match.split(',')]
            if parts:
                related.append(parts[0])
        
        return list(set(related))  # Remove duplicates
    
    def chunk_actor(self, actor: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Convert a threat actor profile into semantic chunks.
        
        Args:
            actor: Threat actor profile
            
        Returns:
            List of semantic chunks with metadata
        """
        if self.entity_level:
            return self._chunk_actor_entity_level(actor)
        else:
            return self._chunk_actor_field_level(actor)
    
    def _chunk_actor_entity_level(self, actor: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Create one comprehensive chunk per actor with all metadata.
        Best for precise entity matching.
        """
        actor_id = actor.get('id', 'unknown')
        name = actor.get('name', 'Unknown')
        primary_name = actor.get('primary_name', name)
        aliases = actor.get('aliases', [])
        alias_givers = actor.get('alias_givers', [])
        countries = actor.get('countries', [])
        observed_sectors = actor.get('observed_sectors') or actor.get('observed-sectors') or []
        observed_countries = actor.get('observed_countries') or actor.get('observed-countries') or []
        tools = actor.get('tools') or []
        ttps = actor.get('ttps') or actor.get('tactics') or []
        targets = actor.get('targets') or []
        campaigns = actor.get('campaigns') or actor.get('operations') or []
        counter_operations = actor.get('counter_operations') or actor.get('counter-operations') or []
        description = actor.get('description', '')
        information_sources = actor.get('information_sources', [])
        sponsor = actor.get('sponsor') or actor.get('sponsorship')
        name_giver = actor.get('name_giver') or actor.get('name-giver')
        last_updated = (
            actor.get('last_updated')
            or actor.get('last_card_change')
            or actor.get('last-card-change')
        )
        
        # Extract related actors from description
        related_actors = self._extract_related_actors(description)
        
        # Build comprehensive text representation
        text_parts = []
        text_parts.append(f"Threat Actor: {name}")
        
        if primary_name and primary_name != name:
            text_parts.append(f"Primary Name: {primary_name}")
        
        if aliases:
            text_parts.append(f"Also known as: {', '.join(aliases)}")

        if name_giver:
            text_parts.append(f"Name Giver: {name_giver}")

        if alias_givers:
            text_parts.append(f"Alias Givers: {', '.join(alias_givers)}")
        
        if countries:
            text_parts.append(f"Origin: {', '.join(countries)}")

        if observed_sectors:
            text_parts.append(f"Observed Sectors: {', '.join(observed_sectors)}")

        if observed_countries:
            text_parts.append(f"Observed Countries: {', '.join(observed_countries)}")

        if targets:
            text_parts.append(f"Targets: {', '.join(str(t) for t in targets)}")

        if tools:
            text_parts.append(f"Tools: {', '.join(str(t) for t in tools)}")

        if ttps:
            text_parts.append(f"TTPs: {', '.join(str(t) for t in ttps)}")

        if campaigns:
            text_parts.append(f"Campaigns: {' | '.join(str(c) for c in campaigns)}")

        if counter_operations:
            text_parts.append(f"Counter Operations: {' | '.join(str(c) for c in counter_operations)}")

        if sponsor:
            text_parts.append(f"Sponsorship: {sponsor}")
        
        if description:
            text_parts.append(f"Description: {description}")

        if last_updated:
            text_parts.append(f"Last Known Activity: {last_updated}")
        
        # Add other important fields
        for field in ['first_seen', 'last_seen', 'motivations']:
            value = actor.get(field)
            if value:
                if isinstance(value, list):
                    text_parts.append(f"{field}: {', '.join(str(v) for v in value)}")
                else:
                    text_parts.append(f"{field}: {value}")
        
        full_text = '\n'.join(text_parts)
        
        # Create single comprehensive chunk
        chunk = {
            'chunk_id': str(uuid.uuid4()),
            'actor_id': actor_id,
            'text': full_text,
            'metadata': {
                'source_field': 'entity_profile',
                'chunk_type': 'entity_level',
                'chunk_index': 0,
                'actor_name': name,
                'primary_name': primary_name,
                'aliases': aliases,
                'countries': countries,
                'information_sources': information_sources
            }
        }
        if name_giver:
            chunk['metadata']['name_giver'] = name_giver
        if related_actors:
            chunk['metadata']['related_actors'] = related_actors
        chunks = [chunk]

        if last_updated:
            last_updated_chunk = {
                'chunk_id': str(uuid.uuid4()),
                'actor_id': actor_id,
                'text': str(last_updated),
                'metadata': {
                    'source_field': 'last_updated',
                    'chunk_type': 'atomic',
                    'chunk_index': 0,
                    'actor_name': name,
                    'primary_name': primary_name,
                    'aliases': aliases,
                    'countries': countries,
                }
            }
            if name_giver:
                last_updated_chunk['metadata']['name_giver'] = name_giver
            chunks.append(last_updated_chunk)

        if sponsor:
            sponsor_chunk = {
                'chunk_id': str(uuid.uuid4()),
                'actor_id': actor_id,
                'text': str(sponsor),
                'metadata': {
                    'source_field': 'sponsor',
                    'chunk_type': 'atomic',
                    'chunk_index': 0,
                    'actor_name': name,
                    'primary_name': primary_name,
                    'aliases': aliases,
                    'countries': countries,
                }
            }
            if name_giver:
                sponsor_chunk['metadata']['name_giver'] = name_giver
            chunks.append(sponsor_chunk)

        for field_name, values in [
            ('observed_sectors', observed_sectors),
            ('observed_countries', observed_countries),
            ('targets', targets),
            ('tools', tools),
            ('ttps', ttps),
            ('campaigns', campaigns),
            ('counter_operations', counter_operations),
            ('alias_givers', alias_givers),
        ]:
            if not values:
                continue
            if not isinstance(values, list):
                values = [values]
            joiner = ' | ' if field_name == 'campaigns' else ', '
            list_chunk = {
                'chunk_id': str(uuid.uuid4()),
                'actor_id': actor_id,
                'text': joiner.join(str(v) for v in values),
                'metadata': {
                    'source_field': field_name,
                    'chunk_type': 'list',
                    'chunk_index': 0,
                    'actor_name': name,
                    'primary_name': primary_name,
                    'aliases': aliases,
                    'countries': countries,
                }
            }
            if name_giver:
                list_chunk['metadata']['name_giver'] = name_giver
            chunks.append(list_chunk)

        return chunks
    
    def _chunk_actor_field_level(self, actor: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Legacy field-by-field chunking.
        """
        chunks = []
        actor_id = actor.get('id', 'unknown')
        actor_name = actor.get('name', 'Unknown')
        primary_name = actor.get('primary_name', actor_name)
        aliases = actor.get('aliases', [])
        name_giver = actor.get('name_giver') or actor.get('name-giver')
        
        for field_name, field_value in actor.items():
            field_type = ChunkingRules.get_field_type(field_name)
            
            if field_type == 'atomic':
                chunk = self._create_atomic_chunk(actor_id, field_name, field_value)
                chunk['metadata']['actor_name'] = actor_name
                chunk['metadata']['primary_name'] = primary_name
                chunk['metadata']['aliases'] = aliases
                if name_giver:
                    chunk['metadata']['name_giver'] = name_giver
                chunks.append(chunk)
            elif field_type == 'list':
                field_chunks = self._chunk_list_field(actor_id, field_name, field_value)
                for chunk in field_chunks:
                    chunk['metadata']['actor_name'] = actor_name
                    chunk['metadata']['primary_name'] = primary_name
                    chunk['metadata']['aliases'] = aliases
                    if name_giver:
                        chunk['metadata']['name_giver'] = name_giver
                chunks.extend(field_chunks)
            elif field_type == 'text':
                text_chunks = self._chunk_text_field(actor_id, field_name, field_value)
                for chunk in text_chunks:
                    chunk['metadata']['actor_name'] = actor_name
                    chunk['metadata']['primary_name'] = primary_name
                    chunk['metadata']['aliases'] = aliases
                    if name_giver:
                        chunk['metadata']['name_giver'] = name_giver
                chunks.extend(text_chunks)
        
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
