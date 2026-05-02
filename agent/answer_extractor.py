"""Extract targeted information from evidence based on query intent."""

import re
import logging
from typing import Dict, Any, List, Optional
from .query_classifier import QueryIntent

logger = logging.getLogger(__name__)


class AnswerExtractor:
    """Extract specific information from evidence based on query intent."""
    
    def __init__(self):
        """Initialize the answer extractor."""
        pass
    
    def extract(self, evidence: List[Dict[str, Any]], query: str, intent: QueryIntent) -> Dict[str, Any]:
        """
        Extract targeted information from evidence based on intent.
        
        Args:
            evidence: List of evidence chunks
            query: Original user query
            intent: Classified query intent
            
        Returns:
            Dict with 'extracted_info', 'summary', and 'confidence'
        """
        if not evidence:
            return {
                'extracted_info': [],
                'summary': 'No information found.',
                'confidence': 0.0
            }
        
        # Route to specific extraction method based on intent
        extraction_methods = {
            QueryIntent.COUNTER_OPERATIONS: self._extract_counter_operations,
            QueryIntent.TACTICS: self._extract_tactics,
            QueryIntent.ASSOCIATIONS: self._extract_associations,
            QueryIntent.TARGETS: self._extract_targets,
            QueryIntent.TOOLS: self._extract_tools,
            QueryIntent.VULNERABILITIES: self._extract_vulnerabilities,
            QueryIntent.ORIGIN: self._extract_origin,
            QueryIntent.CAMPAIGNS: self._extract_campaigns,
            QueryIntent.TIMELINE: self._extract_timeline,
            QueryIntent.ALIASES: self._extract_aliases,
            QueryIntent.CAPABILITIES: self._extract_capabilities,
            QueryIntent.MOTIVATION: self._extract_motivation,
            QueryIntent.SOURCES: self._extract_sources,
        }
        
        extractor = extraction_methods.get(intent, self._extract_overview)
        return extractor(evidence, query)

    def _extract_counter_operations(self, evidence: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Extract counter operations or defensive actions."""
        operations = []
        seen = set()

        def add_entry(value: str, source: str, evidence_text: str):
            cleaned = value.strip()
            if not cleaned:
                return
            key = cleaned.lower()
            if key in seen:
                return
            operations.append({
                'operation': cleaned,
                'source': source,
                'evidence': evidence_text[:220] + '...' if len(evidence_text) > 220 else evidence_text
            })
            seen.add(key)

        for chunk in evidence:
            text = chunk.get('text', '')
            metadata = chunk.get('metadata', {})
            source_field = metadata.get('source_field')

            if source_field in ['counter_operations', 'counter-operations']:
                for item in re.split(r'\s*\|\s*|\s*,\s*', text):
                    add_entry(item, source_field, text)

            embedded = re.search(r'Counter Operations\s*:\s*([^\n]+)', text, re.IGNORECASE)
            if embedded:
                for item in re.split(r'\s*\|\s*|\s*,\s*', embedded.group(1)):
                    add_entry(item, 'entity_profile', text)

        summary = self._format_counter_operations_summary(operations)

        return {
            'extracted_info': operations,
            'summary': summary,
            'confidence': min(len(operations) * 0.2, 1.0)
        }
    
    def _extract_tactics(self, evidence: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Extract tactics, techniques, and procedures (TTPs)."""
        tactics = []
        seen = set()

        def split_items(text: str) -> List[str]:
            if not text:
                return []
            parts = re.split(r'\s*[;,]\s*|\s*\|\s*', text)
            return [part.strip() for part in parts if part.strip()]

        def is_noise_tactic(value: str) -> bool:
            cleaned = value.strip()
            if not cleaned:
                return True
            lowered = cleaned.lower()
            if lowered.startswith('//') or 'http://' in lowered or 'https://' in lowered:
                return True
            if len(cleaned) > 80:
                return True
            if re.search(r'\b20\d{2}\b', cleaned) and ' - ' in cleaned:
                return True
            if re.match(r'^[^a-zA-Z0-9]+$', cleaned):
                return True
            return False

        def add_tactic(value: str, source: str, evidence_text: str):
            cleaned = value.strip()
            if is_noise_tactic(cleaned):
                return
            if cleaned and cleaned.lower() not in seen:
                tactics.append({
                    'tactic': cleaned,
                    'evidence': evidence_text[:200] + '...' if len(evidence_text) > 200 else evidence_text,
                    'source': source
                })
                seen.add(cleaned.lower())
        
        for chunk in evidence:
            text = chunk['text'].lower()
            metadata = chunk.get('metadata', {})

            if metadata.get('source_field') in ['ttps', 'tactics']:
                for item in split_items(chunk['text']):
                    add_tactic(item, metadata.get('source_field', 'description'), chunk['text'])

            embedded_ttps = re.search(r'TTPs\s*:\s*([^\n]+)', chunk['text'], re.IGNORECASE)
            if embedded_ttps:
                for item in split_items(embedded_ttps.group(1)):
                    add_tactic(item, 'entity_profile', chunk['text'])
            
            # Look for common TTP patterns
            patterns = [
                (r'phishing', 'Phishing attacks'),
                (r'spear.?phishing', 'Spear-phishing campaigns'),
                (r'watering.?hole', 'Watering hole attacks'),
                (r'credential.*(harvest|theft|stealing)', 'Credential harvesting'),
                (r'lateral.?movement', 'Lateral movement'),
                (r'0.?day|zero.?day', 'Zero-day exploits'),
                (r'supply.?chain', 'Supply chain compromise'),
                (r'social.?engineering', 'Social engineering'),
                (r'malware', 'Malware deployment'),
                (r'backdoor', 'Backdoor installation'),
                (r'persistence', 'Persistence mechanisms'),
                (r'exfiltrat', 'Data exfiltration'),
                (r'reconnaissance', 'Reconnaissance activities'),
            ]
            
            for pattern, tactic in patterns:
                if re.search(pattern, text) and tactic.lower() not in seen:
                    add_tactic(tactic, metadata.get('source_field', 'description'), chunk['text'])
        
        summary = self._format_tactics_summary(tactics, query)
        
        return {
            'extracted_info': tactics,
            'summary': summary,
            'confidence': min(len(tactics) * 0.2, 1.0)
        }
    
    def _extract_associations(self, evidence: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Extract related/associated threat actors."""
        associations = []
        seen = set()
        full_context = []
        
        # Check if query asks about connection between two specific actors
        query_lower = query.lower()
        is_two_actor_query = any(word in query_lower for word in ['between', 'connection between', 'relationship between', 'and'])
        
        for chunk in evidence:
            text = chunk['text']
            metadata = chunk.get('metadata', {})
            
            # First, check for pre-extracted related_actors from metadata (faster and more reliable)
            related_actors = metadata.get('related_actors', [])
            if related_actors:
                for actor in related_actors:
                    if actor and actor not in seen:
                        # Find context from description
                        idx = text.find(actor)
                        if idx >= 0:
                            start = max(0, idx - 100)
                            end = min(len(text), idx + len(actor) + 150)
                            context = text[start:end].strip()
                        else:
                            context = ""
                        
                        associations.append({
                            'actor': actor,
                            'relationship': 'related/mentioned',
                            'context': context,
                            'source': metadata.get('source_field', 'description')
                        })
                        seen.add(actor)
            
            # Also look for {{Actor Name}} pattern for fallback (if not in metadata)
            actor_matches = re.findall(r'\{\{([^}]+)\}\}', text)
            for match in actor_matches:
                # Extract primary name (first part before comma)
                primary = match.split(',')[0].strip()
                if primary not in seen:
                    # Get context around the match
                    idx = text.find(f'{{{{{match}}}}}')
                    start = max(0, idx - 100)
                    end = min(len(text), idx + len(match) + 150)
                    context = text[start:end].strip()
                    
                    associations.append({
                        'actor': primary,
                        'relationship': 'mentioned/related',
                        'context': context,
                        'source': metadata.get('source_field', 'description')
                    })
                    seen.add(primary)
            
            # Look for explicit relationship terms
            # Use very restrictive patterns - only proper nouns (consecutive capitalized words)
            relationship_patterns = [
                (r'related to (?:the )?([A-Z][A-Za-z0-9]*(?:[ -][A-Z][A-Za-z0-9]*)*?)(?:,|\.|;| and | or | group| threat| actor| the | by | in | that | which | whose |$)', 'related to'),
                (r'linked to (?:the )?([A-Z][A-Za-z0-9]*(?:[ -][A-Z][A-Za-z0-9]*)*?)(?:,|\.|;| and | or | group| threat| actor| the | by | in | that | which | whose |$)', 'linked to'),
                (r'associated with (?:the )?([A-Z][A-Za-z0-9]*(?:[ -][A-Z][A-Za-z0-9]*)*?)(?:,|\.|;| and | or | group| threat| actor| the | by | in | that | which | whose |$)', 'associated with'),
                (r'similar to (?:the )?([A-Z][A-Za-z0-9]*(?:[ -][A-Z][A-Za-z0-9]*)*?)(?:,|\.|;| and | or | group| threat| actor| the | by | in | that | which | whose |$)', 'similar to'),
            ]
            
            # Common false positives to filter out
            false_positives = {
                'Chinese', 'Chinese government', 'Russian', 'Russian government', 
                'Iranian', 'Iranian government', 'North Korean', 'Korean',
                'Government', 'Ministry', 'Intelligence', 'Military', 'Agency',
                'Unknown', 'Various', 'Multiple', 'Several'
            }
            
            for pattern, relationship in relationship_patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    match = match.strip()
                    # Filter criteria:
                    # 1. Not a known false positive
                    # 2. Contains at least one word that's 3+ characters
                    # 3. Not too long (< 50 chars)
                    # 4. Has 1-6 words
                    word_count = len(match.split())
                    longest_word = max(match.split(), key=len) if match.split() else ''
                    
                    is_valid = (
                        match not in seen and
                        match not in false_positives and
                        len(longest_word) >= 3 and
                        3 < len(match) < 50 and
                        1 <= word_count <= 6 and
                        not any(char.islower() for char in match[0:1])  # Starts with capital
                    )
                    
                    if is_valid:
                        associations.append({
                            'actor': match,
                            'relationship': relationship,
                            'source': chunk['metadata'].get('source_field', 'description')
                        })
                        seen.add(match)
            
            # Collect full contexts for two-actor queries
            if is_two_actor_query and len(text) > 50:
                full_context.append(text)
        
        summary = self._format_associations_summary(associations, query, full_context if is_two_actor_query else None)
        
        return {
            'extracted_info': associations,
            'summary': summary,
            'confidence': min(len(associations) * 0.25, 1.0),
            'full_context': full_context if is_two_actor_query else []
        }
    
    def _extract_targets(self, evidence: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Extract targeting information."""
        targets = {
            'sectors': set(),
            'regions': set(),
            'organizations': set(),
            'context': []
        }

        def split_items(text: str) -> List[str]:
            return [item.strip() for item in text.split(',') if item.strip()]
        
        for chunk in evidence:
            text = chunk['text']
            text_lower = text.lower()
            metadata = chunk.get('metadata', {})

            source_field = metadata.get('source_field')
            if source_field in ['observed_sectors', 'observed-sectors']:
                targets['sectors'].update(split_items(text))
            elif source_field in ['observed_countries', 'observed-countries']:
                targets['regions'].update(split_items(text))
            elif source_field == 'targets':
                targets['sectors'].update(split_items(text))
            elif source_field in ['countries']:
                # Avoid treating origin as target regions
                continue

            embedded_sectors = re.search(r'Observed Sectors\s*:\s*([^\n]+)', text, re.IGNORECASE)
            if embedded_sectors:
                targets['sectors'].update(split_items(embedded_sectors.group(1)))

            embedded_countries = re.search(r'Observed Countries\s*:\s*([^\n]+)', text, re.IGNORECASE)
            if embedded_countries:
                targets['regions'].update(split_items(embedded_countries.group(1)))

            embedded_targets = re.search(r'Targets\s*:\s*([^\n]+)', text, re.IGNORECASE)
            if embedded_targets:
                targets['sectors'].update(split_items(embedded_targets.group(1)))
            
            # Sectors/Industries
            sector_keywords = {
                'government': ['government', 'ministry', 'department'],
                'military': ['military', 'defense', 'armed forces'],
                'financial': ['financial', 'bank', 'finance'],
                'energy': ['energy', 'oil', 'gas', 'power'],
                'healthcare': ['healthcare', 'hospital', 'medical'],
                'technology': ['technology', 'tech', 'IT'],
                'telecommunications': ['telecom', 'telecommunications'],
                'aerospace': ['aerospace', 'aviation', 'space'],
                'diplomatic': ['embassy', 'diplomatic', 'consulate'],
            }
            
            for sector, keywords in sector_keywords.items():
                if any(kw in text_lower for kw in keywords):
                    targets['sectors'].add(sector)
            
            # Regions/Countries (only when targeting context is present)
            if re.search(r'target|victim|attack', text_lower) and 'origin:' not in text_lower:
                region_matches = re.findall(
                    r'\b(Russia|China|Iran|North Korea|United States|Europe|Asia|Middle East|'
                    r'Eastern Europe|NATO|Ukraine|Georgia|Syria|Afghanistan|Taiwan|'
                    r'South Korea|Japan|India|Pakistan|Israel|Saudi Arabia|UAE)\b',
                    text
                )
                targets['regions'].update(region_matches)
            
            # Extract targeting context
            if re.search(r'target|victim|attack', text_lower):
                snippet = text[:300] + '...' if len(text) > 300 else text
                targets['context'].append(snippet)
        
        summary = self._format_targets_summary(targets, query)
        
        return {
            'extracted_info': targets,
            'summary': summary,
            'confidence': 0.7 if targets['sectors'] or targets['regions'] else 0.3
        }
    
    def _extract_tools(self, evidence: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Extract malware, tools, and infrastructure information."""
        tools = []
        seen = set()

        def add_tool(value: str, source: str):
            cleaned = value.strip()
            if cleaned and cleaned.lower() not in seen:
                tools.append({
                    'tool': cleaned,
                    'type': 'malware/tool',
                    'source': source
                })
                seen.add(cleaned.lower())
        
        for chunk in evidence:
            text = chunk['text']
            metadata = chunk.get('metadata', {})

            if metadata.get('source_field') == 'tools':
                for item in [t.strip() for t in text.split(',') if t.strip()]:
                    add_tool(item, metadata.get('source_field', 'tools'))

            embedded_tools = re.search(r'Tools\s*:\s*([^\n]+)', text, re.IGNORECASE)
            if embedded_tools:
                for item in [t.strip() for t in embedded_tools.group(1).split(',') if t.strip()]:
                    add_tool(item, 'entity_profile')
            
            # Look for malware names (typically capitalized unique terms)
            malware_patterns = [
                r'\b([A-Z][a-z]+(?:RAT|Trojan|Backdoor|Malware|Worm|Downloader))\b',
                r'\b(X-Agent|Sofacy|Sednit|CHOPSTICK|EVILTOSS|Cannon)\b',
                r'\bmalware called ([A-Z][a-z]+)\b',
                r'\btool[s]? (?:called |named )?([A-Z][a-z]+)\b',
            ]
            
            for pattern in malware_patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0] if match[0] else match[1]
                    if match and len(match) > 2:
                        add_tool(match, metadata.get('source_field', 'description'))
        
        summary = self._format_tools_summary(tools, query)
        
        return {
            'extracted_info': tools,
            'summary': summary,
            'confidence': min(len(tools) * 0.2, 0.8)
        }

    def _extract_vulnerabilities(self, evidence: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Extract vulnerabilities, CVEs, and exploit context from evidence."""
        vulnerabilities = []
        seen = set()

        sentence_splitter = re.compile(r'(?<=[.!?])\s+')
        cve_pattern = re.compile(r'\bCVE-\d{4}-\d+\b', re.IGNORECASE)
        vuln_keywords = re.compile(r'\b(vulnerabilit(?:y|ies)|zero[- ]?day|0[- ]?day|n[- ]?day|exploit(?:ed|ing|s)?|patched)\b', re.IGNORECASE)

        def add_finding(name: str, context: str, source: str):
            cleaned = name.strip()
            if not cleaned:
                return
            key = cleaned.lower()
            if key in seen:
                return
            vulnerabilities.append({
                'vulnerability': cleaned,
                'context': context[:260] + '...' if len(context) > 260 else context,
                'source': source,
            })
            seen.add(key)

        for chunk in evidence:
            text = chunk.get('text', '')
            metadata = chunk.get('metadata', {})
            source = metadata.get('source_field', 'description')

            for cve in cve_pattern.findall(text):
                add_finding(cve.upper(), text, source)

            lowered = text.lower()
            if vuln_keywords.search(text):
                for sentence in sentence_splitter.split(text):
                    if vuln_keywords.search(sentence):
                        sentence_text = sentence.strip()
                        if len(sentence_text) < 20:
                            continue
                        match = cve_pattern.search(sentence_text)
                        if match:
                            add_finding(match.group(0).upper(), sentence_text, source)
                            continue

                        exploit_match = re.search(
                            r'((?:[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,4}|[A-Z][A-Za-z0-9-]+\d{0,4}(?:[A-Z][A-Za-z0-9-]+)*)\s+(?:vulnerability|exploit(?:ed|ing|s)?|zero[- ]?day|0[- ]?day))',
                            sentence_text,
                        )
                        if exploit_match:
                            add_finding(exploit_match.group(1).strip(), sentence_text, source)
                        else:
                            snippet = sentence_text[:140]
                            add_finding(snippet, sentence_text, source)

        summary_lines = ["**Exploited Vulnerabilities**"]
        if vulnerabilities:
            for finding in vulnerabilities[:8]:
                summary_lines.append(f"- {finding['vulnerability']}")
                if finding.get('context'):
                    clean_context = re.sub(r'\s+', ' ', finding['context']).strip()
                    summary_lines.append(f"  Context: {clean_context[:220]}")
        else:
            summary_lines.append("No specific CVEs or named vulnerabilities were identified in the available evidence.")
            summary_lines.append("The evidence instead points to a pattern of phishing, zero-days, and exploitation of exposed services.")

        return {
            'extracted_info': vulnerabilities,
            'summary': "\n".join(summary_lines).strip(),
            'confidence': min(max(len(vulnerabilities) * 0.2, 0.25), 1.0),
        }
    
    def _extract_origin(self, evidence: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Extract origin/attribution information."""
        origin_info = {
            'country': None,
            'attribution': [],
            'sponsor': [],
            'confidence_level': 'unknown'
        }
        
        for chunk in evidence:
            text = chunk['text']
            metadata = chunk.get('metadata', {})
            
            # Check if this is from the 'countries' field
            if metadata.get('source_field') == 'countries':
                origin_info['country'] = text
                origin_info['confidence_level'] = 'high'
                continue

            if metadata.get('source_field') == 'sponsor':
                if text and text not in origin_info['sponsor']:
                    origin_info['sponsor'].append(text)
            
            # Look for attribution statements
            attribution_patterns = [
                r'attributed to ([^.]+)',
                r'associated with ([^.]+(?:government|GRU|PLA|Ministry))',
                r'linked to ([^.]+(?:Russia|China|Iran|North Korea))',
                r'believed to be ([^.]+)',
            ]
            
            for pattern in attribution_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    origin_info['attribution'].append(match.strip())

            # Look for explicit origin or sponsorship markers in entity text
            if not origin_info['country']:
                origin_match = re.search(r'Origin\s*:\s*([^\n]+)', text, re.IGNORECASE)
                if origin_match:
                    origin_info['country'] = origin_match.group(1).strip()

            sponsor_patterns = [
                r'sponsored by ([^,.]+)',
                r'run by (?:the )?([^,.]+)',
                r'backed by ([^,.]+)',
                r'state-sponsored(?:,| by)?\s*([^,.]+)?',
            ]
            for pattern in sponsor_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    if isinstance(match, tuple):
                        match = next((m for m in match if m), '')
                    sponsor_value = (match or 'State-sponsored').strip()
                    if sponsor_value and sponsor_value not in origin_info['sponsor']:
                        origin_info['sponsor'].append(sponsor_value)
        
        summary = self._format_origin_summary(origin_info, query)
        
        return {
            'extracted_info': origin_info,
            'summary': summary,
            'confidence': 0.9 if origin_info['country'] else 0.5
        }
    
    def _extract_campaigns(self, evidence: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Extract campaign/operation information."""
        campaigns = []

        def add_campaign(value: str, context: str):
            cleaned = value.strip()
            if cleaned:
                campaigns.append({
                    'campaign': cleaned,
                    'context': context[:250] + '...' if len(context) > 250 else context
                })
        
        for chunk in evidence:
            text = chunk['text']
            metadata = chunk.get('metadata', {})

            if metadata.get('source_field') in ['campaigns', 'operations']:
                for item in [c.strip() for c in text.split(',') if c.strip()]:
                    add_campaign(item, text)

            embedded_campaigns = re.search(r'Campaigns\s*:\s*([^\n]+)', text, re.IGNORECASE)
            if embedded_campaigns:
                for item in [c.strip() for c in embedded_campaigns.group(1).split(',') if c.strip()]:
                    add_campaign(item, text)
            
            # Look for operation/campaign names
            patterns = [
                r'Operation ([A-Z][a-zA-Z ]+)',
                r'campaign[s]? (?:called |named )?([A-Z][a-zA-Z ]+)',
                r'attack on ([^.]+)',
                r'compromised ([^.]+(?:campaign|committee|organization))',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    if len(match) > 3:
                        add_campaign(match, text)
        
        summary = self._format_campaigns_summary(campaigns, query)
        
        return {
            'extracted_info': campaigns,
            'summary': summary,
            'confidence': min(len(campaigns) * 0.25, 0.8)
        }
    
    def _extract_timeline(self, evidence: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Extract timeline/activity period information."""
        timeline_info = {
            'first_seen': None,
            'activity_periods': [],
            'last_updated': None,
            'last_seen': None
        }
        
        for chunk in evidence:
            text = chunk['text']
            metadata = chunk.get('metadata', {})
            
            # Look for timeline mentions
            patterns = [
                r'(?:active since|since at least) (\w+ \d{4}|\d{4})',
                r'first (?:seen|identified|discovered) (?:in )?(\w+ \d{4}|\d{4})',
                r'began (?:in )?(\d{4})',
                r'started (?:in )?(\d{4})',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    if not timeline_info['first_seen']:
                        timeline_info['first_seen'] = match
                    timeline_info['activity_periods'].append(match)
            
            # Check last_updated from metadata
            source_field = metadata.get('source_field')
            if source_field in ['last_updated', 'last_card_change', 'last-card-change']:
                cleaned = text
                if ':' in cleaned:
                    cleaned = cleaned.split(':', 1)[1].strip()
                timeline_info['last_updated'] = cleaned

            if source_field == 'last_seen':
                cleaned = text
                if ':' in cleaned:
                    cleaned = cleaned.split(':', 1)[1].strip()
                timeline_info['last_seen'] = cleaned

            # Check embedded last-updated markers in entity profile text
            if not timeline_info['last_updated']:
                embedded_match = re.search(r'(?:Last Updated|Last Card Change|Last Known Activity)\s*:\s*([^\n]+)', text, re.IGNORECASE)
                if embedded_match:
                    timeline_info['last_updated'] = embedded_match.group(1).strip()

            if not timeline_info['last_seen']:
                embedded_last_seen = re.search(r'(?:Last Seen)\s*:\s*([^\n]+)', text, re.IGNORECASE)
                if embedded_last_seen:
                    timeline_info['last_seen'] = embedded_last_seen.group(1).strip()
        
        summary = self._format_timeline_summary(timeline_info, query)
        
        return {
            'extracted_info': timeline_info,
            'summary': summary,
            'confidence': 0.8 if timeline_info['first_seen'] else 0.3
        }
    
    def _extract_aliases(self, evidence: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Extract alias information with name givers."""
        # Group evidence by primary_name to avoid mixing actors
        actors_data = {}
        
        for chunk in evidence:
            metadata = chunk.get('metadata', {})
            text = chunk.get('text', '')
            
            pname = metadata.get('primary_name')
            if not pname:
                continue
            
            if pname not in actors_data:
                actors_data[pname] = {
                    'aliases': set(),
                    'name_giver': None,
                    'profiles': []
                }
            
            # Collect data for this actor
            if not actors_data[pname]['name_giver'] and metadata.get('name_giver'):
                actors_data[pname]['name_giver'] = metadata.get('name_giver')
            
            # Aliases are stored as list in metadata
            chunk_aliases = metadata.get('aliases', [])
            if isinstance(chunk_aliases, list):
                actors_data[pname]['aliases'].update(chunk_aliases)
            elif isinstance(chunk_aliases, str):
                actors_data[pname]['aliases'].update([a.strip() for a in chunk_aliases.split(',') if a.strip()])
            
            # Collect entity_profile text for alias giver parsing
            if metadata.get('source_field') == 'entity_profile':
                actors_data[pname]['profiles'].append(text)
        
        # If multiple actors found, pick the most relevant one (most chunks)
        if not actors_data:
            return {
                'extracted_info': {
                    'primary_name': None,
                    'name_giver': None,
                    'aliases': [],
                    'alias_givers': {}
                },
                'summary': "No name information found.",
                'confidence': 0.0
            }
        
        # Get actor with most evidence
        primary_name = max(actors_data.keys(), key=lambda k: len(actors_data[k]['aliases']))
        actor_data = actors_data[primary_name]
        
        # Convert set to sorted list
        aliases = sorted(list(actor_data['aliases']))
        
        # Remove primary name from aliases if present
        if primary_name in aliases:
            aliases.remove(primary_name)
        
        # Parse alias givers from entity profiles
        alias_givers = {}
        for profile in actor_data['profiles']:
            # Look for alias attribution patterns in the profile text
            alias_pattern = re.findall(r'([A-Z][A-Za-z0-9 -]+)\s*\(([^)]+)\)', profile)
            for alias_name, vendor in alias_pattern:
                alias_name = alias_name.strip()
                if alias_name in aliases or alias_name == primary_name:
                    alias_givers[alias_name] = vendor.strip()
        
        summary = self._format_aliases_summary(primary_name, aliases, actor_data['name_giver'], alias_givers, query)
        
        return {
            'extracted_info': {
                'primary_name': primary_name,
                'name_giver': actor_data['name_giver'],
                'aliases': aliases,
                'alias_givers': alias_givers
            },
            'summary': summary,
            'confidence': 0.9 if aliases else 0.5
        }
    
    def _extract_capabilities(self, evidence: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Extract capability/sophistication information."""
        capabilities = []
        
        for chunk in evidence:
            text = chunk['text']
            text_lower = text.lower()
            
            # Look for sophistication indicators
            if any(word in text_lower for word in ['advanced', 'sophisticated', 'capable', 'skilled', 'complex']):
                snippet = text[:300] + '...' if len(text) > 300 else text
                capabilities.append(snippet)
        
        summary = self._format_capabilities_summary(capabilities, query)
        
        return {
            'extracted_info': capabilities,
            'summary': summary,
            'confidence': 0.6 if capabilities else 0.3
        }
    
    def _extract_motivation(self, evidence: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Extract motivation/goals information."""
        motivations = []
        
        for chunk in evidence:
            text = chunk['text']
            text_lower = text.lower()
            
            # Look for motivation keywords
            if any(word in text_lower for word in ['seek', 'goal', 'objective', 'purpose', 'intent', 'espionage', 'financial']):
                snippet = text[:300] + '...' if len(text) > 300 else text
                motivations.append(snippet)
        
        summary = self._format_motivation_summary(motivations, query)
        
        return {
            'extracted_info': motivations,
            'summary': summary,
            'confidence': 0.7 if motivations else 0.3
        }
    
    def _extract_sources(self, evidence: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Extract information sources and attribution (who named the actor)."""
        sources = []
        name_giver = None
        actor_name = None
        queried_name = None
        
        # Check if this is a naming/attribution question
        naming_question = any(pattern in query.lower() for pattern in [
            'who named', 'who gave name', 'who coined', 'name giver',
            'who attributed', 'named by', 'coined by', 'attribution vendor'
        ])
        
        logger.info(f"_extract_sources: naming_question={naming_question}, evidence_count={len(evidence)}")
        
        # Try to extract the specific name being asked about from the query
        if naming_question:
            # Look for capitalized actor names in the query
            import re
            potential_names = re.findall(r'\b[A-Z][A-Za-z0-9 -]*\b', query)
            for name in potential_names:
                name_lower = name.lower().strip()
                if name_lower and len(name_lower) >= 3 and name_lower not in ['who', 'gave', 'name', 'named']:
                    queried_name = name.strip()
                    break
        
        # Collect all aliases from evidence to find the right name_giver
        all_aliases = set()
        primary_name = None
        
        for chunk in evidence:
            metadata = chunk.get('metadata', {})
            
            if not primary_name:
                primary_name = metadata.get('primary_name', metadata.get('actor_name'))
            
            # Collect all aliases from this chunk
            chunk_aliases = metadata.get('aliases', [])
            if isinstance(chunk_aliases, list):
                all_aliases.update(chunk_aliases)
        
        # If this is a naming question, look for the name_giver
        if naming_question:
            # First, try to find metadata that matches the queried name
            best_match_name_giver = None
            alias_givers_map = {}  # Map of alias -> giver
            
            for chunk in evidence:
                metadata = chunk.get('metadata', {})
                text = chunk.get('text', '')
                
                # Check if this chunk has name_giver
                if 'name_giver' in metadata:
                    ng = metadata.get('name_giver')
                    pn = metadata.get('primary_name', metadata.get('actor_name'))
                    
                    # If queried_name matches this actor's name in any form, use this name_giver
                    if queried_name:
                        # Check if queried name matches primary or is in aliases
                        chunk_aliases = set(metadata.get('aliases', []))
                        if (queried_name.lower() == pn.lower() if pn else False) or \
                           any(queried_name.lower() == alias.lower() for alias in chunk_aliases):
                            name_giver = ng
                            actor_name = queried_name
                            break
                    
                    # Fallback: if no specific match, use the first name_giver we find
                    if not best_match_name_giver:
                        best_match_name_giver = (ng, pn)
                
                # Collect alias_givers map from alias_givers chunks
                if metadata.get('source_field') == 'alias_givers':
                    # Parse "Alias (Vendor), Alias2 (Vendor2)" format
                    vendor_pattern = re.findall(r'([A-Z][A-Za-z0-9 -]+)\s*\(([^)]+)\)', text)
                    for alias_name, vendor in vendor_pattern:
                        alias_givers_map[alias_name.strip()] = vendor.strip()
                
                # Collect regular source information
                if metadata.get('source_field') == 'information_sources':
                    sources.append(chunk['text'])
            
            # Try to find name_giver from alias_givers_map
            if alias_givers_map and queried_name:
                # Try exact match
                for alias, giver in alias_givers_map.items():
                    if alias.lower() == queried_name.lower():
                        name_giver = giver
                        actor_name = queried_name
                        break
                
                # Try partial match if no exact match
                if not name_giver:
                    queried_words = set(queried_name.lower().split())
                    for alias, giver in alias_givers_map.items():
                        alias_words = set(alias.lower().split())
                        if queried_words & alias_words:
                            name_giver = giver
                            actor_name = queried_name
                            break
            
            # Use fallback if no specific match found
            if not name_giver and best_match_name_giver:
                name_giver = best_match_name_giver[0]
                actor_name = queried_name or best_match_name_giver[1]
            
            logger.info(f"Naming question: queried_name={queried_name}, actor_name={actor_name}, name_giver={name_giver}, alias_givers={alias_givers_map}")
        
        # Format summary
        if naming_question and name_giver and actor_name:
            summary = f"{actor_name} was named by {name_giver}."
        else:
            summary = self._format_sources_summary(sources, query)
        
        return {
            'extracted_info': sources,
            'summary': summary,
            'name_giver': name_giver,
            'actor_name': actor_name,
            'confidence': 0.9 if (sources or name_giver) else 0.3
        }
    
    def _extract_overview(self, evidence: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Extract general overview - return full description."""
        # For overview, return the full evidence
        return {
            'extracted_info': evidence,
            'summary': None,  # Will use default LLM response
            'confidence': 0.8
        }
    
    # Summary formatting methods
    
    def _format_tactics_summary(self, tactics: List[Dict], query: str) -> str:
        """Format tactics into a summary."""
        if not tactics:
            return "No specific tactics or techniques were found in the available data."
        
        summary_lines = ["**Tactics & Techniques**", "Evidence-based summary:"]
        for tactic in tactics[:8]:
            summary_lines.append(f"- {tactic['tactic']}")
        return "\n".join(summary_lines).strip()
    
    def _format_associations_summary(self, associations: List[Dict], query: str, full_context: List[str] = None) -> str:
        """Format associations into evidence-based summary."""
        if not associations:
            return "No associated or related threat actors were found in the available data."
        
        # Check if this is a two-actor connection query
        query_lower = query.lower()
        is_connection_query = any(word in query_lower for word in ['between', 'relationship between', 'connection between'])
        
        if is_connection_query and full_context:
            # For two-actor queries, extract and show the actual relationship statements
            summary = "**Relationship Evidence:**\n\n"
            
            # Look for contexts that contain explicit relationship statements
            relationship_keywords = [
                'related to', 'closely related', 'associated with', 'linked to',
                'overlap', 'subgroup', 'connection', 'ties', 'similar to',
                'same as', 'also known as', 'part of', 'branch of'
            ]
            
            relevant_contexts = []
            for context in full_context:
                context_lower = context.lower()
                # Find contexts that mention relationships
                has_relationship = any(keyword in context_lower for keyword in relationship_keywords)
                if has_relationship:
                    relevant_contexts.append((context, 100))  # High priority
                elif len(context) > 150:
                    relevant_contexts.append((context, 50))  # Lower priority
            
            # Sort by priority and show top contexts
            relevant_contexts.sort(key=lambda x: x[1], reverse=True)
            
            shown = 0
            for context, _ in relevant_contexts[:3]:
                if len(context) > 50:
                    # Clean up {{actor}} tags for readability
                    clean_context = re.sub(r'\{\{([^}]+)\}\}', r'\1', context)
                    
                    # For contexts with relationship keywords, try to extract the key sentence
                    for keyword in relationship_keywords:
                        if keyword in clean_context.lower():
                            # Find sentence containing the keyword
                            sentences = clean_context.split('.')
                            for sent in sentences:
                                if keyword in sent.lower() and len(sent.strip()) > 10:
                                    summary += f"• {sent.strip()}.\n\n"
                                    shown += 1
                                    break
                            break
                    else:
                        # No specific relationship keyword, show snippet
                        snippet = clean_context[:300] + '...' if len(clean_context) > 300 else clean_context
                        summary += f"{snippet}\n\n"
                        shown += 1
            
            if shown == 0:
                # No relationship statements found, show general context
                for context in full_context[:2]:
                    if len(context) > 100:
                        clean_context = re.sub(r'\{\{([^}]+)\}\}', r'\1', context)
                        snippet = clean_context[:300] + '...' if len(clean_context) > 300 else clean_context
                        summary += f"{snippet}\n\n"
            
            if associations:
                unique_actors = list(set([a['actor'] for a in associations]))
                summary += f"\n**Related Actors Mentioned:** {', '.join(unique_actors[:5])}"
            
            return summary.strip()
        else:
            # For single-actor queries, list associations with context
            summary = "**Related Threat Actors:**\n\n"
            for i, assoc in enumerate(associations[:8], 1):
                actor = assoc['actor']
                rel = assoc.get('relationship', 'mentioned')
                context = assoc.get('context', '')
                
                summary += f"{i}. **{actor}** ({rel})\n"
                if context:
                    # Clean context
                    clean_ctx = re.sub(r'\{\{([^}]+)\}\}', r'\1', context)
                    snippet = clean_ctx[:200] + '...' if len(clean_ctx) > 200 else clean_ctx
                    summary += f"   Context: {snippet}\n"
                summary += "\n"
            
            return summary.strip()
    
    def _format_targets_summary(self, targets: Dict, query: str) -> str:
        """Format targets into a summary."""
        if not targets['sectors'] and not targets['regions']:
            return "No specific targeting information found in the available data."
        
        summary = "**Targeting Summary**\n"
        if targets['sectors']:
            summary += f"**Target Sectors:** {', '.join(sorted(targets['sectors']))}\n"
        if targets['regions']:
            summary += f"**Target Regions:** {', '.join(sorted(targets['regions']))}\n"
        
        return summary.strip()
    
    def _format_tools_summary(self, tools: List[Dict], query: str) -> str:
        """Format tools into a summary."""
        if not tools:
            return "No specific tools or malware were identified in the available data."
        
        tool_names = [t['tool'] for t in tools[:8]]
        summary = "**Tools & Malware**\n"
        summary += ", ".join(tool_names)
        return summary

    def _format_vulnerabilities_summary(self, vulnerabilities: List[Dict], query: str) -> str:
        """Format vulnerability findings into a summary."""
        if not vulnerabilities:
            return (
                "No specific CVEs or named vulnerabilities were identified in the available data.\n"
                "The evidence instead points to a pattern of phishing, zero-days, and exploitation of exposed services."
            )

        summary = "**Exploited Vulnerabilities**\n"
        for finding in vulnerabilities[:8]:
            summary += f"- {finding['vulnerability']}\n"
        return summary.strip()
    
    def _format_origin_summary(self, origin: Dict, query: str) -> str:
        """Format origin information into a summary."""
        if origin['country']:
            summary = f"**Origin:** {origin['country']}"
            if origin['attribution']:
                summary += f"\n**Attribution:** {origin['attribution'][0]}"
            if origin['sponsor']:
                summary += f"\n**Sponsorship:** {origin['sponsor'][0]}"
            return summary
        if origin['sponsor']:
            return f"**Sponsorship:** {origin['sponsor'][0]}"
        return "Origin information not available in the current data."
    
    def _format_campaigns_summary(self, campaigns: List[Dict], query: str) -> str:
        """Format campaigns into a summary."""
        if not campaigns:
            return "No specific campaigns or operations were identified."
        
        summary = "**Notable Campaigns**\n"
        for i, camp in enumerate(campaigns[:3], 1):
            summary += f"{i}. {camp['campaign']}\n"
        return summary.strip()

    def _format_counter_operations_summary(self, operations: List[Dict]) -> str:
        if not operations:
            return "No counter operations were identified in the available data."
        summary = "**Counter Operations**\n"
        for idx, entry in enumerate(operations[:8], 1):
            summary += f"{idx}. {entry['operation']}\n"
        return summary.strip()
    
    def _format_timeline_summary(self, timeline: Dict, query: str) -> str:
        """Format timeline into a summary."""
        parts = []

        if timeline.get('first_seen'):
            parts.append(f"**Active Since:** {timeline['first_seen']}")

        last_activity = timeline.get('last_seen') or timeline.get('last_updated')
        if last_activity:
            parts.append(f"**Last Known Activity:** {last_activity}")

        if parts:
            return "\n".join(parts)

        return "Timeline information not available."
    
    def _format_aliases_summary(self, primary: str, aliases: List[str], name_giver: str, alias_givers: Dict[str, str], query: str) -> str:
        """Format aliases into a comprehensive summary."""
        query_lower = query.lower()
        
        # Check if this is a "is X same as Y" query
        is_same_query = any(phrase in query_lower for phrase in ['same as', 'same group', 'identical to', 'equivalent to'])
        
        if is_same_query:
            # Extract actor names from query - try to find which names were mentioned
            mentioned_names = []
            all_names = ([primary] if primary else []) + aliases
            
            for name in all_names:
                if name:
                    # Check if the name (or significant part of it) appears in query
                    name_words = name.lower().split()
                    # Match if any significant word from the name appears in query
                    significant_words = [w for w in name_words if len(w) >= 4]  # Words with 4+ chars
                    if any(word in query_lower for word in significant_words):
                        mentioned_names.append(name)
                    # Also check exact match
                    elif name.lower() in query_lower:
                        mentioned_names.append(name)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_mentioned = []
            for name in mentioned_names:
                if name not in seen:
                    seen.add(name)
                    unique_mentioned.append(name)
            
            if len(unique_mentioned) >= 2:
                summary = f"**Yes, {unique_mentioned[0]} and {unique_mentioned[1]} are the same threat actor.**\n\n"
            elif len(unique_mentioned) == 1:
                summary = f"**{unique_mentioned[0]} was found in the query.**\n\n"
            else:
                summary = f"**Name Resolution:**\n\n"
        else:
            summary = "**Name Resolution:**\n\n"
        
        if not primary and not aliases:
            return summary + "No name information found."
        
        # Show primary name with attribution
        if primary:
            if name_giver:
                summary += f"**Primary Name:** {primary} (named by {name_giver})\n\n"
            else:
                summary += f"**Primary Name:** {primary}\n\n"
        
        # Show all aliases
        if aliases:
            summary += f"**Total Aliases:** {len(aliases)}\n\n"
            summary += "**Also Known As:**\n"
            for i, alias in enumerate(sorted(aliases)[:15], 1):
                if alias in alias_givers:
                    summary += f"{i}. {alias} (named by {alias_givers[alias]})\n"
                else:
                    summary += f"{i}. {alias}\n"
            
            if len(aliases) > 15:
                summary += f"\n...and {len(aliases) - 15} more\n"
        
        return summary.strip()
    
    def _format_capabilities_summary(self, capabilities: List[str], query: str) -> str:
        """Format capabilities into a summary."""
        if not capabilities:
            return "No specific capability information found."
        return "Capability information available in the evidence."
    
    def _format_motivation_summary(self, motivations: List[str], query: str) -> str:
        """Format motivations into a summary."""
        if not motivations:
            return "No specific motivation information found."
        return "Motivation information available in the evidence."
    
    def _format_sources_summary(self, sources: List[str], query: str) -> str:
        """Format sources into a summary."""
        if not sources:
            return "No source references available."
        
        summary = f"**{len(sources)} Information Sources Available**"
        return summary
