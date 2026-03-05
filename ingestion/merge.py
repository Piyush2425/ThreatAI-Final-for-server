"""Merge raw threat actor profiles into canonical data."""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def _normalize_list_items(items: Optional[List[Any]]) -> List[Any]:
    normalized = []
    for item in items or []:
        if isinstance(item, dict):
            activity = item.get('activity')
            date = item.get('date')
            value = activity
            if date and activity:
                value = f"{date} - {activity}"
            if not value:
                value = (
                    item.get('name')
                    or item.get('title')
                    or item.get('campaign')
                    or item.get('operation')
                )
            if value:
                normalized.append(value)
            continue
        if isinstance(item, list):
            normalized.extend(_normalize_list_items(item))
            continue
        if item is not None:
            normalized.append(item)
    return normalized


def _merge_list(existing: Optional[List[Any]], incoming: Optional[List[Any]]) -> List[Any]:
    existing_list = [v for v in (existing or []) if v]
    incoming_list = [v for v in _normalize_list_items(incoming) if v]
    merged = list(existing_list)
    seen = {str(v).strip().lower() for v in existing_list}
    for value in incoming_list:
        key = str(value).strip().lower()
        if key and key not in seen:
            merged.append(value)
            seen.add(key)
    return merged


def _raw_name_giver(raw_actor: Dict[str, Any], primary_name: str, name_fallback: str) -> str:
    names = raw_actor.get('names') or []
    for entry in names:
        if entry.get('name') == primary_name or entry.get('name') == name_fallback:
            return entry.get('name-giver') or ''
    if names:
        return names[0].get('name-giver') or ''
    return ''


def _raw_alias_givers(raw_actor: Dict[str, Any], primary_name: str, name_fallback: str) -> List[str]:
    alias_givers = []
    for entry in raw_actor.get('names') or []:
        name = entry.get('name')
        giver = entry.get('name-giver')
        if not name or name in [primary_name, name_fallback]:
            continue
        if giver:
            alias_givers.append(f"{name} ({giver})")
        else:
            alias_givers.append(name)
    return alias_givers


def merge_canonical_with_raw(canonical: List[Dict[str, Any]], raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge raw fields (tools, observed, sponsor, motivation, etc.) into canonical actors."""
    raw_by_id = {actor.get('uuid'): actor for actor in raw if actor.get('uuid')}
    raw_by_name = {actor.get('actor', '').lower(): actor for actor in raw if actor.get('actor')}

    merged_actors = []
    for actor in canonical:
        actor_id = actor.get('id')
        primary_name = actor.get('primary_name') or actor.get('name', '')
        name = actor.get('name', primary_name)
        raw_actor = raw_by_id.get(actor_id) or raw_by_name.get(name.lower()) or raw_by_name.get(primary_name.lower())

        if not raw_actor:
            merged_actors.append(actor)
            continue

        merged = dict(actor)

        raw_names = raw_actor.get('names') or []
        raw_aliases = [entry.get('name') for entry in raw_names if entry.get('name')]
        merged['aliases'] = _merge_list(merged.get('aliases'), raw_aliases)

        if not merged.get('name_giver'):
            name_giver = _raw_name_giver(raw_actor, primary_name, name)
            if name_giver:
                merged['name_giver'] = name_giver

        alias_givers = _raw_alias_givers(raw_actor, primary_name, name)
        if alias_givers:
            merged['alias_givers'] = _merge_list(merged.get('alias_givers'), alias_givers)

        if not merged.get('countries'):
            merged['countries'] = raw_actor.get('country') or []

        if not merged.get('information_sources'):
            merged['information_sources'] = raw_actor.get('information') or []

        if not merged.get('last_updated'):
            merged['last_updated'] = raw_actor.get('last-card-change')

        if not merged.get('first_seen'):
            merged['first_seen'] = raw_actor.get('first-seen')

        if not merged.get('last_seen'):
            merged['last_seen'] = raw_actor.get('last-seen')

        if not merged.get('sponsor'):
            merged['sponsor'] = raw_actor.get('sponsor')

        merged['motivations'] = _merge_list(merged.get('motivations'), raw_actor.get('motivation'))
        merged['observed_sectors'] = _merge_list(
            merged.get('observed_sectors'),
            raw_actor.get('observed-sectors')
        )
        merged['observed_countries'] = _merge_list(
            merged.get('observed_countries'),
            raw_actor.get('observed-countries')
        )
        merged['tools'] = _merge_list(merged.get('tools'), raw_actor.get('tools'))
        merged['ttps'] = _merge_list(merged.get('ttps'), raw_actor.get('ttps'))
        merged['targets'] = _merge_list(merged.get('targets'), raw_actor.get('targets'))
        merged['campaigns'] = _merge_list(merged.get('campaigns'), raw_actor.get('campaigns'))
        merged['operations'] = _merge_list(merged.get('operations'), raw_actor.get('operations'))
        merged['counter_operations'] = _merge_list(
            merged.get('counter_operations'),
            raw_actor.get('counter-operations')
        )

        merged_actors.append(merged)

    logger.info("Merged raw fields into canonical actors")
    return merged_actors
