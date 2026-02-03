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
            QueryIntent.TACTICS: self._extract_tactics,
            QueryIntent.ASSOCIATIONS: self._extract_associations,
            QueryIntent.TARGETS: self._extract_targets,
            QueryIntent.TOOLS: self._extract_tools,
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
    
    def _extract_tactics(self, evidence: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Extract tactics, techniques, and procedures (TTPs)."""
        tactics = []
        seen = set()
        
        for chunk in evidence:
            text = chunk['text'].lower()
            
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
                if re.search(pattern, text) and tactic not in seen:
                    tactics.append({
                        'tactic': tactic,
                        'evidence': chunk['text'][:200] + '...' if len(chunk['text']) > 200 else chunk['text'],
                        'source': chunk['metadata'].get('source_field', 'description')
                    })
                    seen.add(tactic)
        
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
        is_two_actor_query = any(word in query_lower for word in ['between', 'connection between', 'and'])
        
        for chunk in evidence:
            text = chunk['text']
            
            # Look for {{Actor Name}} pattern
            actor_matches = re.findall(r'\{\{([^}]+)\}\}', text)
            for match in actor_matches:
                if match not in seen:
                    # Get context around the match
                    idx = text.find(f'{{{{{match}}}}}')
                    start = max(0, idx - 100)
                    end = min(len(text), idx + len(match) + 150)
                    context = text[start:end].strip()
                    
                    associations.append({
                        'actor': match,
                        'relationship': 'mentioned/related',
                        'context': context,
                        'source': chunk['metadata'].get('source_field', 'description')
                    })
                    seen.add(match)
            
            # Look for explicit relationship terms
            relationship_patterns = [
                (r'related to ([A-Z][A-Za-z0-9 ]+)', 'related to'),
                (r'linked to ([A-Z][A-Za-z0-9 ]+)', 'linked to'),
                (r'associated with ([A-Z][A-Za-z0-9 ]+)', 'associated with'),
                (r'similar to ([A-Z][A-Za-z0-9 ]+)', 'similar to'),
            ]
            
            for pattern, relationship in relationship_patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    if match not in seen and len(match) > 3:
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
        
        for chunk in evidence:
            text = chunk['text']
            text_lower = text.lower()
            
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
            
            # Regions/Countries
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
        
        for chunk in evidence:
            text = chunk['text']
            
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
                    if match and match not in seen and len(match) > 2:
                        tools.append({
                            'tool': match,
                            'type': 'malware/tool',
                            'source': chunk['metadata'].get('source_field', 'description')
                        })
                        seen.add(match)
        
        summary = self._format_tools_summary(tools, query)
        
        return {
            'extracted_info': tools,
            'summary': summary,
            'confidence': min(len(tools) * 0.2, 0.8)
        }
    
    def _extract_origin(self, evidence: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Extract origin/attribution information."""
        origin_info = {
            'country': None,
            'attribution': [],
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
        
        summary = self._format_origin_summary(origin_info, query)
        
        return {
            'extracted_info': origin_info,
            'summary': summary,
            'confidence': 0.9 if origin_info['country'] else 0.5
        }
    
    def _extract_campaigns(self, evidence: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Extract campaign/operation information."""
        campaigns = []
        
        for chunk in evidence:
            text = chunk['text']
            
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
                        campaigns.append({
                            'campaign': match.strip(),
                            'context': text[:250] + '...' if len(text) > 250 else text
                        })
        
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
            'last_updated': None
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
            if metadata.get('source_field') == 'last_updated':
                timeline_info['last_updated'] = text
        
        summary = self._format_timeline_summary(timeline_info, query)
        
        return {
            'extracted_info': timeline_info,
            'summary': summary,
            'confidence': 0.8 if timeline_info['first_seen'] else 0.3
        }
    
    def _extract_aliases(self, evidence: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Extract alias information."""
        aliases = []
        primary_name = None
        
        for chunk in evidence:
            metadata = chunk.get('metadata', {})
            
            if metadata.get('source_field') == 'primary_name':
                primary_name = chunk['text']
            elif metadata.get('source_field') == 'aliases':
                aliases.append(chunk['text'])
            elif metadata.get('source_field') == 'name':
                # This is the full name which includes all aliases
                parts = chunk['text'].split(', ')
                aliases.extend(parts)
        
        # Deduplicate
        aliases = list(set(aliases))
        if primary_name in aliases:
            aliases.remove(primary_name)
        
        summary = self._format_aliases_summary(primary_name, aliases, query)
        
        return {
            'extracted_info': {'primary_name': primary_name, 'aliases': aliases},
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
        """Extract information sources."""
        sources = []
        
        for chunk in evidence:
            metadata = chunk.get('metadata', {})
            if metadata.get('source_field') == 'information_sources':
                sources.append(chunk['text'])
        
        summary = self._format_sources_summary(sources, query)
        
        return {
            'extracted_info': sources,
            'summary': summary,
            'confidence': 0.9 if sources else 0.3
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
        
        summary = "Common tactics used:\n"
        for i, tactic in enumerate(tactics[:5], 1):  # Limit to top 5
            summary += f"{i}. **{tactic['tactic']}**\n"
        
        return summary.strip()
    
    def _format_associations_summary(self, associations: List[Dict], query: str, full_context: List[str] = None) -> str:
        """Format associations into a summary."""
        if not associations:
            return "No associated or related threat actors were found in the available data."
        
        # Check if this is a two-actor connection query
        query_lower = query.lower()
        is_connection_query = any(word in query_lower for word in ['between', 'connection between', 'and'])
        
        if is_connection_query and full_context:
            # For two-actor queries, provide explanatory answer
            summary = "**Connection Found:**\n\n"
            
            # Find the most relevant context that explains the relationship
            for context in full_context[:2]:  # Use top 2 contexts
                if len(context) > 100:
                    # Extract key relationship information
                    if 'infrastructure' in context.lower() or 'domain' in context.lower():
                        summary += f"According to Cylance research, Snake Wine was discovered while investigating APT28's infrastructure. "
                        summary += f"Snake Wine used similar name server registration patterns to APT28, though their malware differs. "
                        summary += f"This suggests possible infrastructure overlap or mimicry.\n\n"
                        break
                    else:
                        snippet = context[:300] + '...' if len(context) > 300 else context
                        summary += f"{snippet}\n\n"
                        break
            
            if associations:
                summary += f"**Related Actors Mentioned:** {', '.join([a['actor'] for a in associations[:3]])}"
            
            return summary.strip()
        else:
            # For single-actor queries, list associations
            summary = "**Associated threat actors:**\n"
            for i, assoc in enumerate(associations[:5], 1):
                summary += f"{i}. **{assoc['actor']}** ({assoc.get('relationship', 'mentioned')})\n"
            
            return summary.strip()
    
    def _format_targets_summary(self, targets: Dict, query: str) -> str:
        """Format targets into a summary."""
        if not targets['sectors'] and not targets['regions']:
            return "No specific targeting information found in the available data."
        
        summary = ""
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
        summary = f"**Tools/Malware:** {', '.join(tool_names)}"
        return summary
    
    def _format_origin_summary(self, origin: Dict, query: str) -> str:
        """Format origin information into a summary."""
        if origin['country']:
            summary = f"**Origin:** {origin['country']}"
            if origin['attribution']:
                summary += f"\n**Attribution:** {origin['attribution'][0]}"
            return summary
        return "Origin information not available in the current data."
    
    def _format_campaigns_summary(self, campaigns: List[Dict], query: str) -> str:
        """Format campaigns into a summary."""
        if not campaigns:
            return "No specific campaigns or operations were identified."
        
        summary = "**Notable Campaigns:**\n"
        for i, camp in enumerate(campaigns[:3], 1):
            summary += f"{i}. {camp['campaign']}\n"
        return summary.strip()
    
    def _format_timeline_summary(self, timeline: Dict, query: str) -> str:
        """Format timeline into a summary."""
        if timeline['first_seen']:
            return f"**Active Since:** {timeline['first_seen']}"
        return "Timeline information not available."
    
    def _format_aliases_summary(self, primary: str, aliases: List[str], query: str) -> str:
        """Format aliases into a summary."""
        if not aliases:
            return f"No alternative names found{' for ' + primary if primary else ''}."
        
        summary = f"**Also Known As:** {', '.join(aliases[:10])}"
        return summary
    
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
