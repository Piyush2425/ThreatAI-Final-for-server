"""Normalization of threat actor data fields."""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def normalize_actor(actor: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize optional fields in threat actor profile.
    
    Args:
        actor: Threat actor profile to normalize
        
    Returns:
        Normalized threat actor profile
    """
    normalized = actor.copy()
    
    # Ensure list fields are lists
    for field in [
        'aliases',
        'alias_givers',
        'ttps',
        'tactics',
        'targets',
        'tools',
        'campaigns',
        'operations',
        'counter_operations',
        'counter-operations',
        'observed_sectors',
        'observed-sectors',
        'observed_countries',
        'observed-countries',
        'origins',
        'motivations',
        'information_sources',
    ]:
        if field in normalized:
            if isinstance(normalized[field], str):
                normalized[field] = [normalized[field]]
        else:
            normalized[field] = []
    
    # Normalize name field
    if 'name' in normalized and normalized['name']:
        normalized['name'] = normalized['name'].strip()
    
    # Normalize description
    if 'description' in normalized and normalized['description']:
        normalized['description'] = normalized['description'].strip()
    
    return normalized


def normalize_actors(actors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize a list of threat actor profiles.
    
    Args:
        actors: List of threat actor profiles
        
    Returns:
        List of normalized threat actor profiles
    """
    return [normalize_actor(actor) for actor in actors]


def normalize_mitre_groups(groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize MITRE ATT&CK group records into the actor schema."""
    normalized = []

    def _ensure_description(text: str, fallback: str) -> str:
        cleaned = (text or '').strip()
        return cleaned if cleaned else fallback

    for group in groups or []:
        group_id = group.get('group_id') or ''
        name = group.get('group_name') or ''
        description = group.get('description') or ''
        created = group.get('created') or ''
        modified = group.get('modified') or ''

        associated = [g for g in (group.get('associated_groups') or []) if g]
        software_used = [s.get('name') for s in (group.get('software_used') or []) if s.get('name')]
        software_details = []
        for software in group.get('software_used') or []:
            software_name = software.get('name') or ''
            software_id = software.get('id') or ''
            software_type = software.get('type') or ''
            software_desc = software.get('description') or ''
            if software_name:
                label = software_name
                if software_id:
                    label = f"{software_id}: {software_name}"
                details = [label]
                if software_type:
                    details.append(f"type={software_type}")
                details.append(_ensure_description(software_desc, "Description unavailable from MITRE source"))
                software_details.append(" | ".join(details))

        techniques = []
        technique_details = []
        for technique in group.get('techniques_used') or []:
            tech_id = technique.get('technique_id') or ''
            tech_name = technique.get('name') or ''
            if tech_id and tech_name:
                techniques.append(f"{tech_id}: {tech_name}")
            elif tech_name:
                techniques.append(tech_name)
            elif tech_id:
                techniques.append(tech_id)

            if tech_id or tech_name:
                details = []
                if tech_id and tech_name:
                    details.append(f"{tech_id}: {tech_name}")
                elif tech_name:
                    details.append(tech_name)
                else:
                    details.append(tech_id)
                tech_desc = technique.get('description') or ''
                details.append(_ensure_description(tech_desc, "Description unavailable from MITRE source"))
                subtechniques = technique.get('sub_techniques') or []
                subtechnique_labels = []
                for sub in subtechniques:
                    sub_id = sub.get('id') or ''
                    sub_name = sub.get('name') or ''
                    if sub_id and sub_name:
                        subtechnique_labels.append(f"{sub_id}: {sub_name}")
                    elif sub_name:
                        subtechnique_labels.append(sub_name)
                    elif sub_id:
                        subtechnique_labels.append(sub_id)
                if subtechnique_labels:
                    details.append("Sub-techniques: " + ", ".join(subtechnique_labels))
                technique_details.append(" | ".join(details))

        actor = {
            'id': group_id,
            'name': name,
            'primary_name': name,
            'aliases': associated,
            'countries': [],
            'description': description,
            'tools': software_used,
            'software_used': software_details,
            'ttps': techniques,
            'techniques_used': technique_details,
            'information_sources': ["MITRE ATT&CK"],
            'first_seen': created,
            'last_updated': modified,
            'source_system': 'mitre',
            'source_ids': [group_id] if group_id else [],
        }

        normalized.append(normalize_actor(actor))

    return normalized
