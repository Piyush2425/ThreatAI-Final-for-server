"""Alias normalization for threat actor names."""

import logging
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class AliasResolver:
    """Resolve threat actor aliases to canonical names."""
    
    def __init__(self, actors_data_path: str = "data/canonical/actors.json"):
        """
        Initialize alias resolver with actor data.
        
        Args:
            actors_data_path: Path to canonical actors JSON
        """
        self.actors_data_path = actors_data_path
        self.alias_to_primary: Dict[str, str] = {}
        self.primary_to_aliases: Dict[str, Set[str]] = {}
        self.actor_id_map: Dict[str, str] = {}
        self.primary_to_sources: Dict[str, List[str]] = {}
        self._build_alias_mappings()
    
    def _build_alias_mappings(self):
        """Build bidirectional alias mappings from actor data."""
        try:
            path = Path(self.actors_data_path)
            if not path.exists():
                logger.warning(f"Actors data not found: {self.actors_data_path}")
                return
            
            with open(path, 'r', encoding='utf-8') as f:
                actors = json.load(f)
            
            for actor in actors:
                actor_id = actor.get('id', '')
                primary_name = actor.get('primary_name') or actor.get('name', '')
                name = actor.get('name', '')
                aliases = actor.get('aliases', [])
                information_sources = actor.get('information_sources', [])
                
                if not primary_name:
                    continue
                
                # Normalize to lowercase for case-insensitive matching
                primary_lower = primary_name.lower()
                
                # Map primary name to itself
                self.alias_to_primary[primary_lower] = primary_name
                self.actor_id_map[primary_lower] = actor_id
                
                # Add space normalization for primary name (APT 28 <-> APT28)
                if 'apt' in primary_lower and any(c.isdigit() for c in primary_lower):
                    space_variant = re.sub(r'(apt)(\s*)(\d+)', r'\1 \3', primary_lower)
                    if space_variant != primary_lower:
                        self.alias_to_primary[space_variant] = primary_name
                        self.actor_id_map[space_variant] = actor_id
                    no_space_variant = primary_lower.replace(' ', '')
                    if no_space_variant != primary_lower:
                        self.alias_to_primary[no_space_variant] = primary_name
                        self.actor_id_map[no_space_variant] = actor_id
                
                # Map regular name to primary
                if name and name.lower() != primary_lower:
                    self.alias_to_primary[name.lower()] = primary_name
                    self.actor_id_map[name.lower()] = actor_id
                    
                    # Add space normalization for regular name
                    name_lower = name.lower()
                    if 'apt' in name_lower and any(c.isdigit() for c in name_lower):
                        space_variant = re.sub(r'(apt)(\s*)(\d+)', r'\1 \3', name_lower)
                        if space_variant != name_lower:
                            self.alias_to_primary[space_variant] = primary_name
                            self.actor_id_map[space_variant] = actor_id
                        no_space_variant = name_lower.replace(' ', '')
                        if no_space_variant != name_lower:
                            self.alias_to_primary[no_space_variant] = primary_name
                            self.actor_id_map[no_space_variant] = actor_id
                
                # Initialize primary to aliases set
                if primary_name not in self.primary_to_aliases:
                    self.primary_to_aliases[primary_name] = set()

                # Store information sources by primary name
                if primary_name not in self.primary_to_sources:
                    self.primary_to_sources[primary_name] = list(information_sources) if information_sources else []
                
                # Add all aliases
                for alias in aliases:
                    if alias:
                        alias_lower = alias.lower()
                        self.alias_to_primary[alias_lower] = primary_name
                        self.primary_to_aliases[primary_name].add(alias)
                        self.actor_id_map[alias_lower] = actor_id
                        
                        # Add space normalization variants (APT 28 <-> APT28)
                        if 'apt' in alias_lower and any(c.isdigit() for c in alias_lower):
                            # Try both with and without space
                            space_variant = re.sub(r'(apt)(\s*)(\d+)', r'\1 \3', alias_lower)
                            if space_variant != alias_lower:
                                self.alias_to_primary[space_variant] = primary_name
                                self.actor_id_map[space_variant] = actor_id
                            
                            # Also try removing space
                            no_space_variant = alias_lower.replace(' ', '')
                            if no_space_variant != alias_lower:
                                self.alias_to_primary[no_space_variant] = primary_name
                                self.actor_id_map[no_space_variant] = actor_id
                
                # Add name and primary name to aliases set
                if name:
                    self.primary_to_aliases[primary_name].add(name)
                self.primary_to_aliases[primary_name].add(primary_name)
            
            logger.info(f"Built alias mappings for {len(self.primary_to_aliases)} actors with {len(self.alias_to_primary)} total aliases")
            
        except Exception as e:
            logger.error(f"Error building alias mappings: {e}")
            raise
    
    def resolve(self, name: str) -> Optional[str]:
        """
        Resolve an actor name or alias to canonical primary name.
        
        Args:
            name: Actor name or alias
            
        Returns:
            Canonical primary name, or None if not found
        """
        if not name:
            return None
        
        # Try direct lookup first
        result = self.alias_to_primary.get(name.lower())
        if result:
            return result
        
        # Try with space normalization (APT28 → APT 28)
        normalized = re.sub(r'(APT)(\d+)', r'\1 \2', name.lower())
        result = self.alias_to_primary.get(normalized)
        if result:
            return result
        
        return None
    
    def get_aliases(self, primary_name: str) -> Set[str]:
        """
        Get all aliases for a primary actor name.
        
        Args:
            primary_name: Canonical actor name
            
        Returns:
            Set of all known aliases
        """
        return self.primary_to_aliases.get(primary_name, set())
    
    def get_actor_id(self, name: str) -> Optional[str]:
        """
        Get actor ID from any name or alias.
        
        Args:
            name: Actor name or alias
            
        Returns:
            Actor UUID, or None if not found
        """
        if not name:
            return None
        return self.actor_id_map.get(name.lower())

    def get_information_sources(self, name: str) -> List[str]:
        """
        Get information source URLs for an actor name or alias.
        
        Args:
            name: Actor name or alias
            
        Returns:
            List of source URLs (may be empty)
        """
        if not name:
            return []
        primary = self.resolve(name) or name
        return self.primary_to_sources.get(primary, [])
    
    def extract_actors_from_query(self, query: str) -> List[Dict[str, str]]:
        """
        Extract known threat actor references from query text.
        
        Args:
            query: User query string
            
        Returns:
            List of dicts with 'matched_text', 'primary_name', 'actor_id'
        """
        query_lower = query.lower()
        matched_actors = []
        seen_primaries = set()
        
        # Sort aliases by length (longest first) to match "APT28" before "APT"
        sorted_aliases = sorted(self.alias_to_primary.keys(), key=len, reverse=True)
        
        for alias in sorted_aliases:
            # Check if alias appears as whole word (not substring)
            # Use simple word boundary check
            if alias in query_lower:
                # Verify it's a word boundary match
                idx = query_lower.find(alias)
                before_ok = idx == 0 or not query_lower[idx-1].isalnum()
                after_idx = idx + len(alias)
                after_ok = after_idx >= len(query_lower) or not query_lower[after_idx].isalnum()
                
                if before_ok and after_ok:
                    primary = self.alias_to_primary[alias]
                    if primary not in seen_primaries:
                        seen_primaries.add(primary)
                        matched_actors.append({
                            'matched_text': alias,
                            'primary_name': primary,
                            'actor_id': self.actor_id_map.get(alias, '')
                        })
        
        return matched_actors
    
    def is_known_actor(self, name: str) -> bool:
        """
        Check if a name is a known threat actor.
        
        Args:
            name: Potential actor name
            
        Returns:
            True if known actor
        """
        return name.lower() in self.alias_to_primary
