"""Alias normalization for threat actor names."""

import logging
import json
import re
from difflib import SequenceMatcher, get_close_matches
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
        self.primary_to_last_updated: Dict[str, str] = {}
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

            def add_alias_variants(alias_value: str, primary_name: str, actor_id: str):
                if not alias_value:
                    return
                base = alias_value.strip()
                if not base:
                    return
                pieces = [base]
                pieces.extend([p.strip() for p in re.split(r'[,;|]', base) if p and p.strip()])

                for piece in pieces:
                    spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', piece)
                    spaced = re.sub(r'([A-Za-z])([0-9])', r'\1 \2', spaced)
                    spaced = re.sub(r'([0-9])([A-Za-z])', r'\1 \2', spaced)
                    spaced = re.sub(r'[\-_\/]+', ' ', spaced)
                    spaced = re.sub(r'\s+', ' ', spaced).strip()

                    variants = {piece.lower()}
                    if spaced:
                        variants.add(spaced.lower())
                    no_space = re.sub(r'[\s\-_\/]+', '', piece.lower())
                    if no_space:
                        variants.add(no_space)

                    # Common actor naming pattern support: "X Group" -> "X"
                    for v in list(variants):
                        if v.endswith(' group') and len(v) > 10:
                            variants.add(v[:-6].strip())

                    for variant in variants:
                        if len(variant) < 4:
                            continue
                        self.alias_to_primary[variant] = primary_name
                        self.actor_id_map[variant] = actor_id
            
            for actor in actors:
                actor_id = actor.get('id', '')
                primary_name = actor.get('primary_name') or actor.get('name', '')
                name = actor.get('name', '')
                aliases = actor.get('aliases', [])
                information_sources = actor.get('information_sources', [])
                last_updated = (
                    actor.get('last_updated')
                    or actor.get('last_card_change')
                    or actor.get('last-card-change')
                )
                
                if not primary_name:
                    continue
                
                # Normalize to lowercase for case-insensitive matching
                primary_lower = primary_name.lower()
                
                # Map primary name to itself
                self.alias_to_primary[primary_lower] = primary_name
                self.actor_id_map[primary_lower] = actor_id
                add_alias_variants(primary_name, primary_name, actor_id)
                
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
                    add_alias_variants(name, primary_name, actor_id)
                    
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

                # Store last updated by primary name
                if last_updated and primary_name not in self.primary_to_last_updated:
                    self.primary_to_last_updated[primary_name] = str(last_updated)
                
                # Add all aliases
                for alias in aliases:
                    if alias:
                        alias_lower = alias.lower()
                        self.alias_to_primary[alias_lower] = primary_name
                        self.primary_to_aliases[primary_name].add(alias)
                        self.actor_id_map[alias_lower] = actor_id
                        add_alias_variants(alias, primary_name, actor_id)
                        
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
        
        normalized_name = name.lower().strip()

        # Ignore generic query words that should never map to an actor.
        if normalized_name in {
            "group", "actor", "actors", "threat", "campaign", "operation", "news",
            "latest", "recent", "attack", "attacks", "incident", "incidents",
        }:
            return None

        # Try direct lookup first
        result = self.alias_to_primary.get(normalized_name)
        if result:
            return result
        
        # Try with space normalization (APT28 → APT 28)
        normalized = re.sub(r'(APT)(\d+)', r'\1 \2', normalized_name)
        result = self.alias_to_primary.get(normalized)
        if result:
            return result

        # Typo-tolerant fallback for user-entered actor names (e.g., "alazarouse" -> "lazarus").
        # Keep threshold high to avoid accidental cross-actor matches.
        if len(normalized_name) >= 5:
            aliases = list(self.alias_to_primary.keys())
            if " " not in normalized_name:
                aliases = [a for a in aliases if " " not in a and "-" not in a and "/" not in a]
            candidates = get_close_matches(normalized_name, aliases, n=2, cutoff=0.78)
            if candidates:
                best = candidates[0]
                best_score = SequenceMatcher(None, normalized_name, best).ratio()
                second_score = 0.0
                if len(candidates) > 1:
                    second_score = SequenceMatcher(None, normalized_name, candidates[1]).ratio()

                # Accept only strong and non-ambiguous fuzzy matches.
                if best_score >= 0.82 and (best_score - second_score) >= 0.06:
                    return self.alias_to_primary.get(best)
        
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

    def get_last_updated(self, name: str) -> Optional[str]:
        """
        Get last updated date for an actor name or alias.
        
        Args:
            name: Actor name or alias
            
        Returns:
            Last updated date string, or None
        """
        if not name:
            return None
        primary = self.resolve(name) or name
        return self.primary_to_last_updated.get(primary)
    
    def extract_actors_from_query(self, query: str, allow_fuzzy: bool = True) -> List[Dict[str, str]]:
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
        matched_aliases = []
        
        # Sort aliases by length (longest first) to match "APT28" before "APT"
        sorted_aliases = sorted(self.alias_to_primary.keys(), key=len, reverse=True)
        
        # First pass: exact word boundary matching
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
                    # Skip aliases that are contained in an already matched alias
                    if any(alias in matched_alias for matched_alias in matched_aliases):
                        continue
                    primary = self.alias_to_primary[alias]
                    if primary not in seen_primaries:
                        seen_primaries.add(primary)
                        matched_actors.append({
                            'matched_text': alias,
                            'primary_name': primary,
                            'actor_id': self.actor_id_map.get(alias, '')
                        })
                        matched_aliases.append(alias)
        
        # Second pass: fuzzy matching for short comparison-like user queries only.
        # Do not run this on long unstructured text (e.g., feed article bodies), as it can over-tag actors.
        is_comparison_query = any(phrase in query_lower for phrase in [
            ' vs ', ' versus ', 'compare', 'comparison', 'difference', 'same as', 'identical', 'equivalent'
        ])

        if allow_fuzzy and len(query_lower) <= 180 and len(seen_primaries) < 2 and is_comparison_query:
            # Extract potential actor words (capitalized or common threat actor patterns)
            import re
            # Look for capitalized words or APT patterns
            potential_names = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b|\bAPT[\s-]?\d+\b|\b[A-Z]{3,}\b', query)
            
            for name in potential_names:
                name_lower = name.lower()
                if name_lower in seen_primaries or name_lower in [m['matched_text'] for m in matched_actors]:
                    continue
                
                # Try fuzzy matching with strict rules
                for alias, primary in self.alias_to_primary.items():
                    if primary in seen_primaries:
                        continue
                    
                    matched = False
                    
                    # Special handling for APT groups - require exact number match
                    apt_pattern = re.search(r'apt[\s-]?(\d+)', name_lower)
                    if apt_pattern:
                        # For APT groups, check if the alias has the same number
                        apt_alias_pattern = re.search(r'apt[\s-]?(\d+)', alias)
                        if apt_alias_pattern and apt_pattern.group(1) == apt_alias_pattern.group(1):
                            matched = True
                    else:
                        # For non-APT names, do word-based matching
                        name_words = set(name_lower.split())
                        alias_words = set(alias.split())
                        
                        # Check if at least one significant word (4+ chars) matches
                        significant_name_words = {w for w in name_words if len(w) >= 4}
                        significant_alias_words = {w for w in alias_words if len(w) >= 4}
                        
                        if significant_name_words and significant_alias_words:
                            # At least one significant word must match
                            if significant_name_words & significant_alias_words:
                                matched = True
                        elif len(name_lower) >= 6 and len(alias) >= 6:
                            # For longer names without clear words, check if one is contained in the other
                            # But only for reasonably long strings to avoid false positives
                            if name_lower in alias or alias in name_lower:
                                matched = True
                    
                    if matched:
                        seen_primaries.add(primary)
                        matched_actors.append({
                            'matched_text': name,
                            'primary_name': primary,
                            'actor_id': self.actor_id_map.get(alias, '')
                        })
                        break
        
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
