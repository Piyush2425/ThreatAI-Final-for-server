"""LLM-based question answering with evidence grounding."""

import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Tuple
import requests
from .query_classifier import QueryClassifier, QueryIntent
from .answer_extractor import AnswerExtractor

logger = logging.getLogger(__name__)


class OllamaClient:
    """Client for Ollama local LLM."""
    
    def __init__(self, model: str = "mistral", base_url: str = "http://localhost:11434"):
        """
        Initialize Ollama client.
        
        Args:
            model: Model name (mistral, neural-chat, dolphin, etc.)
            base_url: Ollama server URL
        """
        self.model = model
        self.base_url = base_url
        self.api_endpoint = f"{base_url}/api/generate"
        self._verify_connection()
    
    def _verify_connection(self):
        """Verify connection to Ollama server."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                logger.info(f"✓ Connected to Ollama server at {self.base_url}")
                models = response.json().get("models", [])
                available_models = [m["name"] for m in models]
                logger.info(f"  Available models: {available_models}")
            else:
                logger.warning(f"Ollama server returned status {response.status_code}")
        except requests.exceptions.ConnectionError:
            logger.error(f"✗ Cannot connect to Ollama at {self.base_url}")
            logger.error("  Install Ollama: https://ollama.ai")
            logger.error("  Start Ollama: ollama serve")
            raise
    
    def generate(self, prompt: str, temperature: float = 0.3, max_tokens: int = 512, timeout: int = 60) -> str:
        """
        Generate response from Ollama.
        
        Args:
            prompt: Input prompt
            temperature: Generation temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds (default 60)
            
        Returns:
            Generated text
        """
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "temperature": temperature,
                "num_predict": max_tokens,
                "stream": False
            }
            
            # Adjust timeout: 1 second per 5 tokens (faster estimate)
            adjusted_timeout = max(timeout, max_tokens // 5)
            
            response = requests.post(self.api_endpoint, json=payload, timeout=adjusted_timeout)
            
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "")
            else:
                logger.error(f"Ollama error: {response.status_code}")
                return ""
                
        except requests.exceptions.Timeout:
            logger.error(f"Ollama request timed out after {adjusted_timeout} seconds")
            return ""
        except Exception as e:
            logger.error(f"Error calling Ollama: {e}")
            return ""

    def generate_stream(self, prompt: str, temperature: float = 0.3, max_tokens: int = 512, timeout: int = 120):
        """
        Generate response from Ollama with streaming (yields tokens).
        
        Args:
            prompt: Input prompt
            temperature: Generation temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds (default 120)
            
        Yields:
            Generated tokens as they arrive
        """
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "temperature": temperature,
                "num_predict": max_tokens,
                "stream": True  # Enable streaming
            }
            
            # Adjust timeout based on max_tokens
            adjusted_timeout = max(timeout, max_tokens // 10)
            
            response = requests.post(self.api_endpoint, json=payload, timeout=adjusted_timeout, stream=True)
            
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        import json
                        try:
                            data = json.loads(line)
                            token = data.get("response", "")
                            if token:
                                yield token
                        except json.JSONDecodeError:
                            continue
            else:
                logger.error(f"Ollama streaming error: {response.status_code}")
                
        except requests.exceptions.Timeout:
            logger.error(f"Ollama streaming timed out after {adjusted_timeout} seconds")
        except Exception as e:
            logger.error(f"Error in Ollama streaming: {e}")


class EvidenceBasedInterpreter:
    """Generate answers grounded in retrieved evidence using Ollama."""
    
    def __init__(self, model: str = "mistral", base_url: str = "http://localhost:11434"):
        """
        Initialize interpreter with Ollama.
        
        Args:
            model: LLM model name
            base_url: Ollama server URL
        """
        try:
            self.llm = OllamaClient(model=model, base_url=base_url)
            self.use_ollama = True
        except Exception as e:
            logger.warning(f"Ollama not available, using fallback: {e}")
            self.llm = None
            self.use_ollama = False
        
        # Initialize query classifier and answer extractor
        self.query_classifier = QueryClassifier()
        self.answer_extractor = AnswerExtractor()
        logger.info("Initialized query classifier and answer extractor")
    
    def explain(self, query: str, evidence: List[Dict[str, Any]], response_mode: str = 'adaptive') -> Dict[str, Any]:
        """
        Generate explanation based on evidence using Ollama with adaptive response mode.
        
        Args:
            query: User query
            evidence: Retrieved evidence chunks
            response_mode: 'concise', 'report', 'comparison', or 'adaptive'
            
        Returns:
            Explanation response with metadata
        """
        
        if not evidence:
            return {
                'query': query,
                'answer': 'No threat intelligence found for this query. Please try a different search.',
                'evidence': [],
                'confidence': 0.0,
                'source_count': 0,
                'model': self.llm.model if self.use_ollama else 'fallback',
                'response_mode': response_mode,
            }
        
        # Classify query to understand user intent
        classification = self.query_classifier.classify(query)
        intent = classification['primary_intent']
        
        logger.info(f"Query intent: {intent.value}, confidence: {classification['confidence']:.2f}")
        
        evidence_for_answer = self._filter_evidence_by_intent(evidence, intent, response_mode, query)
        if not evidence_for_answer:
            evidence_for_answer = evidence

        # Extract targeted information based on intent
        extraction_result = self.answer_extractor.extract(evidence_for_answer, query, intent)
        
        # Determine response strategy
        evidence_text = self._format_evidence_for_llm(evidence_for_answer)
        
        strict_mode_used = False

        # For OVERVIEW intent (comprehensive reports), always use LLM if available
        if intent == QueryIntent.OVERVIEW:
            if response_mode == 'report':
                if self.use_ollama:
                    logger.info("Report mode requested, generating strict LLM report")
                    answer = self._generate_with_ollama(query, evidence_text, 'report', strict_evidence=True)
                    strict_mode_used = True
                    if not answer or len(answer.strip()) < 50:
                        logger.warning("LLM report failed or returned short response, using fallback summary")
                        answer = self._generate_summary(query, evidence_for_answer)
                else:
                    logger.info("Report mode requested, using evidence-only summary")
                    answer = self._generate_summary(query, evidence_for_answer)
            elif self.use_ollama:
                if self._is_sparse_evidence(evidence_for_answer):
                    logger.info("Sparse evidence detected, generating strict LLM answer")
                    answer = self._generate_with_ollama(query, evidence_text, 'report', strict_evidence=True)
                    strict_mode_used = True
                else:
                    logger.info("Generating comprehensive report with LLM")
                    answer = self._generate_with_ollama(query, evidence_text, 'report')
                
                # If LLM failed or timed out, use improved fallback
                if not answer or len(answer.strip()) < 50:
                    logger.warning("LLM generation failed or returned short response, using enhanced fallback")
                    answer = self._generate_summary(query, evidence_for_answer)
            else:
                logger.warning("Using fallback summary for sparse evidence")
                answer = self._generate_summary(query, evidence_for_answer)
        
        # For specific extraction intents with results
        elif extraction_result['summary'] and extraction_result['summary'] != "":
            # For ASSOCIATIONS and ALIASES, use extracted summary directly to prevent hallucination
            if intent in [QueryIntent.ASSOCIATIONS, QueryIntent.ALIASES]:
                logger.info(f"Using evidence-only extraction for {intent.value} to prevent hallucination")
                answer = extraction_result['summary']
            elif self.use_ollama and response_mode != 'report' and intent in [
                QueryIntent.TACTICS, QueryIntent.TARGETS,
                QueryIntent.TOOLS, QueryIntent.CAMPAIGNS, QueryIntent.MOTIVATION,
                QueryIntent.ORIGIN, QueryIntent.TIMELINE, QueryIntent.COUNTER_OPERATIONS
            ]:
                logger.info(f"Generating targeted LLM answer for {intent.value}")
                answer = self._generate_targeted_answer(query, evidence_text, intent, extraction_result)
                if not answer:
                    answer = extraction_result['summary']
            else:
                # Use extracted summary as base
                answer = extraction_result['summary']
        
        # Fallback: use LLM or summary
        else:
            if intent in [QueryIntent.TACTICS, QueryIntent.ASSOCIATIONS, QueryIntent.ALIASES,
                          QueryIntent.TARGETS, QueryIntent.TOOLS, QueryIntent.CAMPAIGNS,
                          QueryIntent.MOTIVATION, QueryIntent.ORIGIN, QueryIntent.TIMELINE,
                          QueryIntent.COUNTER_OPERATIONS]:
                logger.info("No extraction result, using evidence-based summary")
                answer = self._generate_summary(query, evidence_for_answer)
            elif self.use_ollama:
                logger.info("No extraction result, generating with LLM")
                answer = self._generate_with_ollama(query, evidence_text, response_mode, strict_evidence=True)
                strict_mode_used = True
            else:
                answer = self._generate_summary(query, evidence_for_answer)

        if strict_mode_used:
            unapproved_apt = self._detect_unapproved_apt_mentions(answer, evidence_for_answer)
            if unapproved_apt:
                logger.warning("Strict LLM answer contained unapproved actor mentions; using fallback summary")
                answer = self._generate_summary(query, evidence_for_answer)

        # Ensure last known activity is included when available
        last_activity = self._extract_last_activity(evidence_for_answer)
        if last_activity and answer:
            answer_lower = answer.lower()
            if all(term not in answer_lower for term in [
                "last known activity",
                "last card change",
                "last updated",
                "last seen",
            ]):
                answer = f"{answer}\n\n**Last Known Activity:** {last_activity}"

        if response_mode != 'report' and answer and "**Sources**" not in answer:
            answer = self._append_sources(answer, evidence_for_answer)

        contradictions = self._detect_contradictions(evidence_for_answer)
        recency_score, recency_note = self._recency_score(evidence_for_answer)
        confidence_tier, confidence_note = self._confidence_tier(
            extraction_result['confidence'],
            contradictions,
            recency_score,
            len(evidence_for_answer)
        )

        answer = self._prepend_confidence(answer, confidence_tier, confidence_note)

        return {
            'query': query,
            'answer': answer,
            'evidence': evidence_for_answer,
            'evidence_formatted': self._format_evidence_for_llm(evidence_for_answer),
            'confidence': extraction_result['confidence'],
            'confidence_tier': confidence_tier,
            'confidence_rationale': confidence_note,
            'contradictions': contradictions,
            'recency_note': recency_note,
            'source_count': len(evidence_for_answer),
            'model': self.llm.model if self.use_ollama else 'fallback',
            'response_mode': response_mode,
            'intent': intent.value,
            'extracted_info': extraction_result['extracted_info']
        }
    
    def _format_evidence_for_llm(self, evidence: List[Dict[str, Any]]) -> str:
        """Format evidence chunks for LLM input."""
        formatted = []
        max_chunks = 3
        max_chars = 500
        for i, chunk in enumerate(evidence[:max_chunks], 1):
            source = chunk['metadata'].get('source_field', 'unknown')
            score = chunk.get('similarity_score', 0.0)
            text = chunk['text']
            if source in ['last_updated', 'last_card_change', 'last-card-change']:
                text = f"Last Known Activity: {text}"
            if len(text) > max_chars:
                text = text[:max_chars].rstrip() + "..."
            formatted.append(f"[{i}] ({source}, score: {score:.2f}): {text}")
        
        return "\n".join(formatted)

    def _prepend_confidence(self, answer: str, tier: str, note: str) -> str:
        """Add confidence tier and rationale to the top of the answer."""
        if not answer:
            return answer
        header = f"**Confidence:** {tier}\n**Rationale:** {note}\n"
        if answer.lstrip().startswith("**Confidence:**"):
            return answer
        return f"{header}\n{answer}"

    def _confidence_tier(self, base_confidence: float, contradictions: List[str], recency_score: float, evidence_count: int) -> Tuple[str, str]:
        """Compute confidence tier with rationale."""
        score = base_confidence
        if contradictions:
            score -= 0.2
        if recency_score < 0.4:
            score -= 0.1
        if evidence_count >= 5:
            score += 0.05
        score = max(0.0, min(score, 1.0))

        if score >= 0.75:
            tier = "High"
        elif score >= 0.5:
            tier = "Medium"
        else:
            tier = "Low"

        notes = []
        notes.append(f"{evidence_count} sources")
        if contradictions:
            notes.append("conflicting sources detected")
        if recency_score < 0.4:
            notes.append("older intel")
        return tier, ", ".join(notes)

    def _detect_contradictions(self, evidence: List[Dict[str, Any]]) -> List[str]:
        """Detect simple contradictions across key fields."""
        fields = {
            'countries': set(),
            'sponsor': set(),
            'first_seen': set(),
            'last_seen': set(),
        }
        for chunk in evidence:
            source = chunk.get('metadata', {}).get('source_field')
            text = chunk.get('text', '')
            if source == 'countries':
                fields['countries'].update([t.strip() for t in text.split(',') if t.strip()])
            if source == 'sponsor':
                fields['sponsor'].add(text.strip())
            if source == 'first_seen':
                fields['first_seen'].add(text.strip())
            if source in ['last_seen', 'last_updated', 'last_card_change', 'last-card-change']:
                fields['last_seen'].add(text.strip())

        contradictions = []
        if len(fields['countries']) > 1:
            contradictions.append("origin differs across sources")
        if len(fields['sponsor']) > 1:
            contradictions.append("sponsorship differs across sources")
        if len(fields['first_seen']) > 1:
            contradictions.append("first seen date differs across sources")
        if len(fields['last_seen']) > 1:
            contradictions.append("last seen date differs across sources")
        return contradictions

    def _recency_score(self, evidence: List[Dict[str, Any]]) -> Tuple[float, str]:
        """Estimate recency score based on latest year found in evidence."""
        years = []
        for chunk in evidence:
            years.extend(self._extract_years(chunk.get('text', '')))
        if not years:
            return 0.5, "recency unknown"
        latest = max(years)
        current_year = datetime.utcnow().year
        age = max(0, current_year - latest)
        if age <= 1:
            return 1.0, f"recent ({latest})"
        if age <= 3:
            return 0.7, f"moderate ({latest})"
        if age <= 6:
            return 0.5, f"aged ({latest})"
        return 0.3, f"old ({latest})"

    def _extract_years(self, text: str) -> List[int]:
        """Extract year values from text."""
        return [int(y) for y in re.findall(r'\b(19\d{2}|20\d{2})\b', text)]

    def _build_source_index(self, evidence: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
        """Build a stable source index for inline citations."""
        index = {}
        order = []
        for chunk in evidence:
            metadata = chunk.get('metadata', {})
            sources = metadata.get('information_sources', []) or []
            if sources:
                for src in sources:
                    if not isinstance(src, str) or not src:
                        continue
                    key = src
                    if key in index:
                        continue
                    label = self._source_label(src, chunk.get('text', ''))
                    index[key] = {'label': label, 'url': src}
                    order.append(key)
            else:
                key = f"{metadata.get('actor_name', 'unknown')}::{metadata.get('source_field', 'unknown')}"
                if key not in index:
                    index[key] = {
                        'label': metadata.get('source_field', 'unknown'),
                        'url': ''
                    }
                    order.append(key)

        numbered = {}
        for idx, key in enumerate(order, 1):
            numbered[key] = {
                'id': f"S{idx}",
                'label': index[key]['label'],
                'url': index[key]['url']
            }
        return numbered

    def _source_label(self, url: str, text: str) -> str:
        """Create a concise source label using domain and year."""
        domain = re.sub(r'^https?://', '', url).split('/')[0]
        years = self._extract_years(text)
        year = max(years) if years else None
        return f"{domain}{f' ({year})' if year else ''}"

    def _citation_ids_for_chunks(self, chunks: List[Dict[str, Any]], source_index: Dict[str, Dict[str, str]]) -> List[str]:
        """Get citation ids for a list of evidence chunks."""
        ids = []
        for chunk in chunks:
            metadata = chunk.get('metadata', {})
            sources = metadata.get('information_sources', []) or []
            if sources:
                for src in sources:
                    entry = source_index.get(src)
                    if entry and entry['id'] not in ids:
                        ids.append(entry['id'])
            else:
                key = f"{metadata.get('actor_name', 'unknown')}::{metadata.get('source_field', 'unknown')}"
                entry = source_index.get(key)
                if entry and entry['id'] not in ids:
                    ids.append(entry['id'])
        return ids

    def _format_citations(self, ids: List[str]) -> str:
        if not ids:
            return ""
        return " " + "".join(f"[{cid}]" for cid in ids[:3])

    def _append_sources(self, answer: str, evidence: List[Dict[str, Any]]) -> str:
        """Append a compact sources list to non-report answers."""
        source_index = self._build_source_index(evidence)
        if not source_index:
            return answer
        lines = []
        for entry in list(source_index.values())[:6]:
            label = entry['label']
            url = entry['url']
            if url:
                lines.append(f"- [{entry['id']}] {label} - {url}")
            else:
                lines.append(f"- [{entry['id']}] {label}")
        if not lines:
            return answer
        return f"{answer}\n\n**Sources**\n" + "\n".join(lines)

    def _collect_allowed_actor_terms(self, evidence: List[Dict[str, Any]]) -> set:
        """Collect allowed actor terms from evidence metadata and text."""
        allowed = set()
        for chunk in evidence:
            metadata = chunk.get('metadata', {})
            for name in [metadata.get('primary_name'), metadata.get('actor_name')]:
                if name:
                    allowed.add(name.lower())
                    allowed.add(re.sub(r'\s+', '', name.lower()))
            for alias in metadata.get('aliases', []) or []:
                alias = alias.strip()
                if alias:
                    allowed.add(alias.lower())
                    allowed.add(re.sub(r'\s+', '', alias.lower()))

            text = chunk.get('text', '')
            for match in re.findall(r'\bAPT\s?\d+\b', text, re.IGNORECASE):
                normalized = re.sub(r'\s+', '', match.lower())
                allowed.add(normalized)

        return allowed

    def _detect_unapproved_apt_mentions(self, answer: str, evidence: List[Dict[str, Any]]) -> List[str]:
        """Detect APT mentions in the answer that are not present in evidence."""
        if not answer:
            return []
        allowed = self._collect_allowed_actor_terms(evidence)
        found = []
        for match in re.findall(r'\bAPT\s?\d+\b', answer, re.IGNORECASE):
            normalized = re.sub(r'\s+', '', match.lower())
            if normalized not in allowed:
                found.append(match)
        return found

    def _filter_evidence_by_intent(
        self,
        evidence: List[Dict[str, Any]],
        intent: QueryIntent,
        response_mode: str,
        query: str = ""
    ) -> List[Dict[str, Any]]:
        """Filter evidence to sections relevant for the intent and mode."""
        if not evidence:
            return evidence
        
        # For naming questions, don't filter - we need access to name_giver metadata on all chunks
        naming_patterns = [
            'who named', 'who gave name', 'who coined', 'name giver',
            'who attributed', 'named by', 'coined by', 'attribution vendor'
        ]
        if query and any(pattern in query.lower() for pattern in naming_patterns):
            logger.info("Naming question detected - skipping evidence filtering to preserve name_giver metadata")
            return evidence

        report_fields = {
            'entity_profile', 'description', 'aliases', 'countries', 'sponsor',
            'first_seen', 'last_seen', 'last_updated', 'last-card-change', 'last_card_change',
            'observed_sectors', 'observed-sectors', 'observed_countries', 'observed-countries',
            'targets', 'tools', 'ttps', 'campaigns', 'counter_operations', 'counter-operations',
            'motivation', 'motivations', 'information'
        }

        intent_fields = {
            QueryIntent.TACTICS: {'ttps', 'tactics', 'description', 'entity_profile'},
            QueryIntent.ASSOCIATIONS: {'description', 'entity_profile'},
            QueryIntent.TARGETS: {'targets', 'observed_sectors', 'observed-sectors', 'observed_countries', 'observed-countries'},
            QueryIntent.TOOLS: {'tools'},
            QueryIntent.ORIGIN: {'countries', 'sponsor'},
            QueryIntent.CAMPAIGNS: {'campaigns'},
            QueryIntent.TIMELINE: {'first_seen', 'last_seen', 'last_updated', 'last-card-change', 'last_card_change'},
            QueryIntent.ALIASES: {'aliases', 'primary_name', 'name', 'name_giver', 'entity_profile'},
            QueryIntent.CAPABILITIES: {'tools', 'ttps'},
            QueryIntent.MOTIVATION: {'motivation', 'motivations'},
            QueryIntent.COUNTER_OPERATIONS: {'counter_operations', 'counter-operations'},
            QueryIntent.SOURCES: {'information'},
            QueryIntent.OVERVIEW: {'entity_profile', 'description', 'aliases', 'countries', 'sponsor', 'first_seen', 'last_seen', 'last_updated',
                                   'observed_sectors', 'observed-sectors', 'observed_countries', 'observed-countries', 'targets', 'tools', 'ttps',
                                   'campaigns', 'counter_operations', 'counter-operations', 'motivation', 'motivations'}
        }

        allowed_fields = report_fields if response_mode == 'report' else intent_fields.get(intent, set())
        if not allowed_fields:
            return evidence

        filtered = []
        for chunk in evidence:
            source_field = chunk.get('metadata', {}).get('source_field')
            if not source_field:
                filtered.append(chunk)
                continue
            if source_field in allowed_fields:
                filtered.append(chunk)

        return filtered

    def _extract_last_activity(self, evidence: List[Dict[str, Any]]) -> str:
        """Extract last known activity date from evidence when available."""
        if not evidence:
            return ""

        last_seen = ""
        last_updated = ""

        for chunk in evidence:
            metadata = chunk.get('metadata', {})
            source = metadata.get('source_field')
            text = chunk.get('text', '')

            if source == 'last_seen' and not last_seen:
                last_seen = text.split(':', 1)[1].strip() if ':' in text else text.strip()
                continue

            if source in ['last_updated', 'last_card_change', 'last-card-change'] and not last_updated:
                last_updated = text.split(':', 1)[1].strip() if ':' in text else text.strip()

            if not last_seen:
                embedded_last_seen = re.search(r'(?:Last Seen)\s*:\s*([^\n]+)', text, re.IGNORECASE)
                if embedded_last_seen:
                    last_seen = embedded_last_seen.group(1).strip()

            if not last_updated:
                embedded_last_updated = re.search(r'(?:Last Known Activity|Last Updated|Last Card Change)\s*:\s*([^\n]+)', text, re.IGNORECASE)
                if embedded_last_updated:
                    last_updated = embedded_last_updated.group(1).strip()

        return last_seen or last_updated

    def _is_sparse_evidence(self, evidence: List[Dict[str, Any]]) -> bool:
        """Check if evidence is too sparse for LLM report generation."""
        if not evidence:
            return True

        allowed_fields = {
            'entity_profile',
            'bm25',
            'last_updated',
            'last_card_change',
            'last-card-change',
            'name_giver',
            'name-giver',
            'alias_givers',
            'aliases',
            'sponsor',
            'countries',
        }

        rich_fields = {
            'tools',
            'targets',
            'observed_sectors',
            'observed-sectors',
            'observed_countries',
            'observed-countries',
            'ttps',
            'campaigns',
            'operations',
            'counter_operations',
            'counter-operations',
            'counter_operations',
            'counter-operations',
            'motivations',
            'motivation',
        }

        has_rich_fields = False
        for chunk in evidence:
            source_field = chunk.get('metadata', {}).get('source_field')
            if source_field in rich_fields:
                has_rich_fields = True
                break

        for chunk in evidence:
            source_field = chunk.get('metadata', {}).get('source_field')
            if source_field and source_field not in allowed_fields:
                return False

        # If we only have minimal fields, check for sparse descriptions
        for chunk in evidence:
            text = chunk.get('text', '').lower()
            if any(
                phrase in text
                for phrase in [
                    'mentioned in a summary report only',
                    'not much is known',
                    "we don't know who they are",
                ]
            ) and not has_rich_fields:
                return True

        return len(evidence) <= 1

    def _split_campaigns(self, campaigns: List[str], recent_count: int, older_count: int) -> tuple:
        """Split campaigns into recent and older lists based on parsed dates."""
        parsed = [self._parse_campaign_item(item) for item in campaigns]
        dated = [item for item in parsed if item['sort_key'] != (0, 0, 0)]
        undated = [item for item in parsed if item['sort_key'] == (0, 0, 0)]
        dated.sort(key=lambda item: item['sort_key'], reverse=True)
        recent = dated[:recent_count]
        older = dated[recent_count:recent_count + older_count]
        if len(recent) < recent_count:
            remaining = recent_count - len(recent)
            recent.extend(undated[:remaining])
            undated = undated[remaining:]
        if len(older) < older_count:
            remaining = older_count - len(older)
            older.extend(undated[:remaining])
        return recent, older

    def _parse_campaign_item(self, item: str) -> Dict[str, Any]:
        """Parse a campaign item into date, activity, and sort key."""
        text = item.strip()
        date = "Unknown"
        activity = text

        match = re.match(r'\s*([0-9]{4}(?:[-/][0-9]{2}|\s*Early|/\d{4})?)\s*-\s*(.+)', text)
        if match:
            date = match.group(1).strip()
            activity = match.group(2).strip()

        activity_clean = re.sub(r'\s+', ' ', activity).strip()

        sort_key = self._date_sort_key(date)

        return {
            'date': date,
            'activity': activity_clean,
            'sort_key': sort_key,
        }

    def _date_sort_key(self, date_value: str) -> tuple:
        """Create a sortable key for date strings."""
        year_match = re.search(r'(\d{4})', date_value)
        if not year_match:
            return (0, 0, 0)
        year = int(year_match.group(1))
        month_match = re.search(r'\d{4}[-/](\d{2})', date_value)
        month = int(month_match.group(1)) if month_match else 0
        return (year, month, 0)

    def _format_campaign_summaries(self, items: List[Dict[str, Any]]) -> str:
        """Format recent campaign items into short summaries."""
        lines = []
        for item in items:
            summary = item['activity']
            if len(summary) > 180:
                summary = summary[:177].rstrip() + '...'
            lines.append(f"- {item['date']}: {summary}")
        return '\n'.join(lines) if lines else "- No recent campaigns listed."

    def _format_campaign_table(self, items: List[Dict[str, Any]], strip_links: bool = False) -> str:
        """Format campaign items into a markdown table."""
        lines = ["| Date | Activity |", "| --- | --- |"]
        for item in items:
            activity = item['activity']
            if strip_links:
                activity = self._strip_urls(activity)
            if len(activity) > 160:
                activity = activity[:157].rstrip() + '...'
            lines.append(f"| {item['date']} | {activity} |")
        return '\n'.join(lines)

    def _parse_counter_operation_entry(self, entry: str) -> Dict[str, str]:
        """Parse a counter operation entry into date/activity fields."""
        if not entry:
            return {'date': 'Unknown', 'activity': ''}

        activity = entry.strip()

        date = 'Unknown'
        date_match = re.search(r'\b(20\d{2}[-/]\d{2}(?:[-/]\d{2})?)\b', activity)
        if date_match:
            date = date_match.group(1)
            activity = activity.replace(date, '').strip(' -:;')
        else:
            year_match = re.search(r'\b(19\d{2}|20\d{2})\b', activity)
            if year_match:
                date = year_match.group(1)
                activity = activity.replace(date, '').strip(' -:;')

        return {
            'date': date,
            'activity': activity,
        }

    def _format_counter_operations_table(self, entries: List[str], strip_links: bool = False) -> str:
        """Format counter operations into a markdown table."""
        lines = ["| Sr | Date | Activity |", "| --- | --- | --- |"]
        for idx, entry in enumerate(entries, 1):
            parsed = self._parse_counter_operation_entry(entry)
            activity = parsed['activity']
            if strip_links:
                activity = self._strip_urls(activity)
            if len(activity) > 160:
                activity = activity[:157].rstrip() + '...'
            lines.append(f"| {idx} | {parsed['date']} | {activity} |")
        return '\n'.join(lines)

    def _strip_urls(self, text: str) -> str:
        """Remove URLs from text for report output."""
        if not text:
            return text
        cleaned = re.sub(r'https?://\S+', '', text)
        cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()
        return cleaned

    def _parse_entity_profile_text(self, text: str) -> Dict[str, Any]:
        """Parse entity profile chunk text into structured fields."""
        if not text:
            return {}

        fields = {}
        labels = [
            "Threat Actor",
            "Primary Name",
            "Also known as",
            "Origin",
            "Sponsorship",
            "Observed Sectors",
            "Observed Countries",
            "Targets",
            "Tools",
            "TTPs",
            "Campaigns",
            "Counter Operations",
            "Description",
            "Last Known Activity",
            "Last Updated",
            "Last Card Change",
            "first_seen",
            "last_seen",
            "motivations",
            "targets",
            "tools",
        ]

        pattern = r"(?:" + "|".join(re.escape(lbl) for lbl in labels) + r")\s*:\s*"
        matches = list(re.finditer(pattern, text, re.IGNORECASE))

        for idx, match in enumerate(matches):
            label = match.group(0).split(':', 1)[0].strip().lower()
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            value = text[start:end].strip()
            if not value:
                continue

            if label == 'threat actor':
                fields['name'] = value
            elif label == 'primary name':
                fields['primary_name'] = value
            elif label == 'also known as':
                fields['aliases'] = [v.strip() for v in value.split(',') if v.strip()]
            elif label == 'origin':
                fields['countries'] = [v.strip() for v in value.split(',') if v.strip()]
            elif label == 'sponsorship':
                fields['sponsor'] = value
            elif label == 'observed sectors':
                fields['observed_sectors'] = [v.strip() for v in value.split(',') if v.strip()]
            elif label == 'observed countries':
                fields['observed_countries'] = [v.strip() for v in value.split(',') if v.strip()]
            elif label == 'targets':
                fields['targets'] = [v.strip() for v in value.split(',') if v.strip()]
            elif label == 'tools':
                fields['tools'] = [v.strip() for v in value.split(',') if v.strip()]
            elif label == 'ttps':
                fields['ttps'] = [v.strip() for v in value.split(',') if v.strip()]
            elif label == 'campaigns':
                if ' | ' in value:
                    fields['campaigns'] = [v.strip() for v in value.split(' | ') if v.strip()]
                else:
                    fields['campaigns'] = [v.strip() for v in value.split(',') if v.strip()]
            elif label == 'counter operations':
                if ' | ' in value:
                    fields['counter_operations'] = [v.strip() for v in value.split(' | ') if v.strip()]
                else:
                    fields['counter_operations'] = [v.strip() for v in value.split(',') if v.strip()]
            elif label == 'description':
                fields['description'] = value
            elif label in ['last known activity', 'last updated', 'last card change']:
                fields['last_updated'] = value
            elif label == 'first_seen':
                fields['first_seen'] = value
            elif label == 'last_seen':
                fields['last_seen'] = value
            elif label == 'motivations':
                fields['motivations'] = [v.strip() for v in value.split(',') if v.strip()]
            elif label == 'targets':
                fields['targets'] = [v.strip() for v in value.split(',') if v.strip()]
        
        return fields
    
    def _generate_targeted_answer(self, query: str, evidence_text: str, intent: QueryIntent, extraction_result: Dict) -> str:
        """Generate a targeted answer based on query intent and extracted information."""
        
        # Load system prompt
        try:
            with open('agent/system_prompt.txt', 'r') as f:
                system_prompt = f.read()
        except:
            system_prompt = "You are a threat intelligence analyst."
        
        # Build intent-specific instructions
        intent_instructions = {
            QueryIntent.TACTICS: "Answer specifically about tactics, techniques, and procedures (TTPs). Provide detailed explanation with examples from the evidence. Use bullet points for clarity.",
            QueryIntent.ASSOCIATIONS: "Answer specifically about associated or related threat actors. Explain the connections and relationships clearly with supporting context.",
            QueryIntent.TARGETS: "Answer specifically about targets, victims, sectors, and regions. Provide detailed information about who they target and why.",
            QueryIntent.TOOLS: "Answer specifically about tools, malware, and infrastructure used. Describe the technical capabilities in detail.",
            QueryIntent.CAMPAIGNS: "Answer specifically about campaigns and operations. Describe the notable incidents with context and impact.",
            QueryIntent.ORIGIN: "Answer specifically about origin, attribution, and sponsorship. Be direct about where they're from with supporting details.",
            QueryIntent.TIMELINE: "Answer specifically about timeline and activity periods. State when they were first seen and include the last known activity date if provided (last updated / last card change).",
        }
        
        instruction = intent_instructions.get(intent, "Answer the specific question asked with appropriate detail.")
        
        prompt = f"""{system_prompt}

INSTRUCTION: {instruction}

EVIDENCE PROVIDED:
{evidence_text}

USER QUERY: {query}

RESPONSE (provide detailed, well-formatted answer):
"""
        
        try:
            response = self.llm.generate(prompt, temperature=0.3, max_tokens=200)
            return response.strip() if response else extraction_result['summary']
        except Exception as e:
            logger.error(f"Targeted answer generation error: {e}")
            return extraction_result['summary']
    
    def _generate_with_ollama(
        self,
        query: str,
        evidence_text: str,
        response_mode: str = 'adaptive',
        strict_evidence: bool = False
    ) -> str:
        """Generate response using Ollama LLM with mode-specific prompt."""
        
        # Load system prompt
        try:
            with open('agent/system_prompt.txt', 'r') as f:
                system_prompt = f.read()
        except:
            system_prompt = "You are a threat intelligence analyst."
        
        # Build mode-specific instruction
        mode_instruction = self._get_mode_instruction(response_mode)
        if strict_evidence:
            mode_instruction = (
                "Use ONLY the provided evidence. If a detail is missing, say 'Not found in evidence.' "
                "Do not add URLs in the answer body; keep links in the evidence section only. "
                + mode_instruction
            )
        
        prompt = f"""{system_prompt}

{mode_instruction}

EVIDENCE PROVIDED:
{evidence_text}

USER QUERY: {query}

RESPONSE:
"""
        
        try:
            # Adjust parameters based on mode
            max_tokens = self._get_max_tokens_for_mode(response_mode)
            temperature = self._get_temperature_for_mode(response_mode)
            
            response = self.llm.generate(prompt, temperature=temperature, max_tokens=max_tokens)
            return response.strip() if response else self._generate_summary(query, [])
        except Exception as e:
            logger.error(f"Ollama generation error: {e}")
            return "Error generating response from local LLM."
    
    def _get_mode_instruction(self, response_mode: str) -> str:
        """Get instruction text based on response mode."""
        instructions = {
            'concise': 'Respond CONCISELY in 1-2 sentences. Get straight to the point. Be direct and clear.',
            'report': 'Provide a COMPREHENSIVE threat intelligence report with detailed information, multiple paragraphs, and structured sections. Be thorough and informative. Aim for 200-400 words with clear formatting.',
            'comparison': 'Provide a detailed COMPARISON between the threat actors mentioned. Highlight similarities and differences with supporting details.',
            'adaptive': 'Provide a helpful, detailed response. Match the depth to the query - if asking for comprehensive information, provide multiple paragraphs with clear structure. Be conversational yet thorough.'
        }
        return instructions.get(response_mode, instructions['adaptive'])
    
    def _get_max_tokens_for_mode(self, response_mode: str) -> int:
        """Get max token limit based on response mode."""
        tokens = {
            'concise': 100,      # Short, direct answer
            'report': 350,       # Report - reduced to avoid timeouts
            'comparison': 300,   # Comparison - reduced
            'adaptive': 250      # Default - reduced for speed
        }
        return tokens.get(response_mode, tokens['adaptive'])
    
    def _get_temperature_for_mode(self, response_mode: str) -> float:
        """Get temperature based on response mode."""
        temps = {
            'concise': 0.2,      # Very factual
            'report': 0.3,       # Factual with good structure
            'comparison': 0.4,   # Slightly more creative for analysis
            'adaptive': 0.3      # Default
        }
        return temps.get(response_mode, temps['adaptive'])
    
    def _generate_summary(self, query: str, evidence: List[Dict[str, Any]]) -> str:
        """Generate a comprehensive summary from evidence (fallback when LLM unavailable)."""
        if not evidence:
            return "No relevant information found."
        
        # Check if this is a comprehensive query (report, overview, etc.)
        query_lower = query.lower()
        is_comprehensive = any(word in query_lower for word in 
                              ['report', 'tell me about', 'write', 'overview', 'explain', 'describe'])
        
        if is_comprehensive:
            is_report_request = 'report' in query_lower
            # Generate detailed multi-paragraph summary
            summary_parts = []
            
            # Group evidence by source field
            by_field = {}
            by_field_chunks = {}
            for chunk in evidence:
                field = chunk['metadata'].get('source_field', 'description')
                if field not in by_field:
                    by_field[field] = []
                    by_field_chunks[field] = []
                by_field[field].append(chunk['text'])
                by_field_chunks[field].append(chunk)

            source_index = self._build_source_index(evidence)
            entity_profile_chunks = by_field_chunks.get('entity_profile', [])
            entity_profile_chunk = entity_profile_chunks[0] if entity_profile_chunks else None

            # If we only have entity-level chunks, parse them into fields
            if 'entity_profile' in by_field:
                parsed = self._parse_entity_profile_text(by_field['entity_profile'][0])
                if parsed.get('name') and 'name' not in by_field:
                    by_field['name'] = [parsed['name']]
                    if entity_profile_chunk:
                        by_field_chunks['name'] = [entity_profile_chunk]
                if parsed.get('primary_name') and 'primary_name' not in by_field:
                    by_field['primary_name'] = [parsed['primary_name']]
                    if entity_profile_chunk:
                        by_field_chunks['primary_name'] = [entity_profile_chunk]
                if parsed.get('aliases') and 'aliases' not in by_field:
                    by_field['aliases'] = parsed['aliases']
                    if entity_profile_chunk:
                        by_field_chunks['aliases'] = [entity_profile_chunk]
                if parsed.get('countries') and 'countries' not in by_field:
                    by_field['countries'] = parsed['countries']
                    if entity_profile_chunk:
                        by_field_chunks['countries'] = [entity_profile_chunk]
                if parsed.get('description') and 'description' not in by_field:
                    by_field['description'] = [parsed['description']]
                    if entity_profile_chunk:
                        by_field_chunks['description'] = [entity_profile_chunk]
                if parsed.get('sponsor') and 'sponsor' not in by_field:
                    by_field['sponsor'] = [parsed['sponsor']]
                    if entity_profile_chunk:
                        by_field_chunks['sponsor'] = [entity_profile_chunk]
                if parsed.get('observed_sectors') and 'observed_sectors' not in by_field:
                    by_field['observed_sectors'] = parsed['observed_sectors']
                    if entity_profile_chunk:
                        by_field_chunks['observed_sectors'] = [entity_profile_chunk]
                if parsed.get('observed_countries') and 'observed_countries' not in by_field:
                    by_field['observed_countries'] = parsed['observed_countries']
                    if entity_profile_chunk:
                        by_field_chunks['observed_countries'] = [entity_profile_chunk]
                if parsed.get('tools') and 'tools' not in by_field:
                    by_field['tools'] = parsed['tools']
                    if entity_profile_chunk:
                        by_field_chunks['tools'] = [entity_profile_chunk]
                if parsed.get('ttps') and 'ttps' not in by_field:
                    by_field['ttps'] = parsed['ttps']
                    if entity_profile_chunk:
                        by_field_chunks['ttps'] = [entity_profile_chunk]
                if parsed.get('campaigns') and 'campaigns' not in by_field:
                    by_field['campaigns'] = parsed['campaigns']
                if parsed.get('counter_operations') and 'counter_operations' not in by_field:
                    by_field['counter_operations'] = parsed['counter_operations']
                    if entity_profile_chunk:
                        by_field_chunks['campaigns'] = [entity_profile_chunk]
                if parsed.get('first_seen') and 'first_seen' not in by_field:
                    by_field['first_seen'] = [parsed['first_seen']]
                    if entity_profile_chunk:
                        by_field_chunks['first_seen'] = [entity_profile_chunk]
                if parsed.get('last_seen') and 'last_seen' not in by_field:
                    by_field['last_seen'] = [parsed['last_seen']]
                    if entity_profile_chunk:
                        by_field_chunks['last_seen'] = [entity_profile_chunk]
                if parsed.get('last_updated') and 'last_updated' not in by_field:
                    by_field['last_updated'] = [parsed['last_updated']]
                    if entity_profile_chunk:
                        by_field_chunks['last_updated'] = [entity_profile_chunk]
                if parsed.get('motivations') and 'motivation' not in by_field:
                    by_field['motivation'] = parsed['motivations']
                    if entity_profile_chunk:
                        by_field_chunks['motivation'] = [entity_profile_chunk]
                if parsed.get('targets') and 'targets' not in by_field:
                    by_field['targets'] = parsed['targets']
                    if entity_profile_chunk:
                        by_field_chunks['targets'] = [entity_profile_chunk]
            
            # Overview section
            name = by_field.get('primary_name', by_field.get('name', ['Unknown']))[0]
            if is_report_request:
                summary_parts.append("**Key Attributes**\n")
                summary_parts.append(f"- **Threat Actor:** {name}\n")
                if 'aliases' in by_field and len(by_field['aliases']) > 0:
                    aliases = ', '.join(by_field['aliases'][:12])
                    cites = self._format_citations(self._citation_ids_for_chunks(by_field_chunks.get('aliases', []), source_index))
                    summary_parts.append(f"- **Also Known As:** {aliases}{cites}\n")
                if 'countries' in by_field:
                    origin = by_field['countries'][0]
                    cites = self._format_citations(self._citation_ids_for_chunks(by_field_chunks.get('countries', []), source_index))
                    summary_parts.append(f"- **Origin:** {origin}{cites}\n")
                if 'sponsor' in by_field:
                    sponsor = by_field['sponsor'][0]
                    cites = self._format_citations(self._citation_ids_for_chunks(by_field_chunks.get('sponsor', []), source_index))
                    summary_parts.append(f"- **Sponsorship:** {sponsor}{cites}\n")
                if 'first_seen' in by_field or 'first-seen' in by_field:
                    first_seen = by_field.get('first_seen', by_field.get('first-seen', ['Unknown']))[0]
                    cites = self._format_citations(self._citation_ids_for_chunks(by_field_chunks.get('first_seen', []), source_index))
                    summary_parts.append(f"- **First Seen:** {first_seen}{cites}\n")
                last_activity_list = (
                    by_field.get(
                        'last_seen',
                        by_field.get(
                            'last_updated',
                            by_field.get('last-card-change', by_field.get('last_card_change', ['Unknown']))
                        )
                    )
                )
                last_activity = last_activity_list[0] if last_activity_list else 'Unknown'
                cites = self._format_citations(self._citation_ids_for_chunks(by_field_chunks.get('last_seen', []) + by_field_chunks.get('last_updated', []), source_index))
                summary_parts.append(f"- **Last Known Activity:** {last_activity}{cites}\n")
            else:
                summary_parts.append(f"**Threat Actor:** {name}\n")
                if 'aliases' in by_field and len(by_field['aliases']) > 0:
                    aliases = ', '.join(by_field['aliases'][:12])
                    cites = self._format_citations(self._citation_ids_for_chunks(by_field_chunks.get('aliases', []), source_index))
                    summary_parts.append(f"**Also Known As:** {aliases}{cites}\n")
                if 'countries' in by_field:
                    origin = by_field['countries'][0]
                    cites = self._format_citations(self._citation_ids_for_chunks(by_field_chunks.get('countries', []), source_index))
                    summary_parts.append(f"**Origin:** {origin}{cites}\n")
                if 'sponsor' in by_field:
                    sponsor = by_field['sponsor'][0]
                    cites = self._format_citations(self._citation_ids_for_chunks(by_field_chunks.get('sponsor', []), source_index))
                    summary_parts.append(f"**Sponsorship:** {sponsor}{cites}\n")
                if 'first_seen' in by_field or 'first-seen' in by_field:
                    first_seen = by_field.get('first_seen', by_field.get('first-seen', ['Unknown']))[0]
                    cites = self._format_citations(self._citation_ids_for_chunks(by_field_chunks.get('first_seen', []), source_index))
                    summary_parts.append(f"**First Seen:** {first_seen}{cites}\n")
                if 'last_seen' in by_field or 'last_updated' in by_field or 'last-card-change' in by_field or 'last_card_change' in by_field:
                    last_activity_list = (
                        by_field.get(
                            'last_seen',
                            by_field.get(
                                'last_updated',
                                by_field.get('last-card-change', by_field.get('last_card_change', ['Unknown']))
                            )
                        )
                    )
                    last_activity = last_activity_list[0] if last_activity_list else 'Unknown'
                    cites = self._format_citations(self._citation_ids_for_chunks(by_field_chunks.get('last_seen', []) + by_field_chunks.get('last_updated', []), source_index))
                    summary_parts.append(f"**Last Known Activity:** {last_activity}{cites}\n")

            if is_report_request:
                highlights = []
                if 'countries' in by_field:
                    highlights.append(f"Origin: {by_field['countries'][0]}")
                if 'sponsor' in by_field:
                    highlights.append(f"Sponsorship: {by_field['sponsor'][0]}")
                if 'last_seen' in by_field or 'last_updated' in by_field:
                    last_activity_list = (
                        by_field.get(
                            'last_seen',
                            by_field.get('last_updated', ['Unknown'])
                        )
                    )
                    last_activity = last_activity_list[0] if last_activity_list else 'Unknown'
                    highlights.append(f"Last Known Activity: {last_activity}")
                if 'tools' in by_field:
                    top_tools = ', '.join([t for t in by_field['tools'] if t][:3])
                    if top_tools:
                        highlights.append(f"Top Tools: {top_tools}")
                if highlights:
                    summary_parts.append("\n**Key Highlights**\n" + "\n".join(f"- {h}" for h in highlights) + "\n")
            else:
                # Background / Profile
                if 'description' in by_field:
                    summary_parts.append("\n**Background & History**\n")
                    description = by_field['description'][0]
                    if len(description) > 200:
                        paragraphs = description.split('\n\n')
                        for para in paragraphs[:4]:
                            if para.strip():
                                summary_parts.append(f"{para.strip()}\n")
                    else:
                        summary_parts.append(f"{description}\n")

            # Motivation
            if 'motivation' in by_field:
                motivations = ', '.join(by_field['motivation'][:8])
                cites = self._format_citations(self._citation_ids_for_chunks(by_field_chunks.get('motivation', []), source_index))
                summary_parts.append(f"\n**Motivation**\n{motivations}{cites}\n")

            # Targets / Regions / Sectors
            sectors = by_field.get('observed_sectors', by_field.get('observed-sectors', []))
            countries = by_field.get('observed_countries', by_field.get('observed-countries', []))
            targets = by_field.get('targets', [])
            if sectors or countries or targets:
                summary_parts.append("\n**Targets & Regions**\n")
                if sectors:
                    cites = self._format_citations(self._citation_ids_for_chunks(by_field_chunks.get('observed_sectors', []), source_index))
                    summary_parts.append("- **Observed Sectors:** " + ', '.join(sectors[:12]) + f"{cites}\n")
                if countries:
                    cites = self._format_citations(self._citation_ids_for_chunks(by_field_chunks.get('observed_countries', []), source_index))
                    summary_parts.append("- **Observed Regions:** " + ', '.join(countries[:15]) + f"{cites}\n")
                if targets:
                    cites = self._format_citations(self._citation_ids_for_chunks(by_field_chunks.get('targets', []), source_index))
                    summary_parts.append("- **Targets:** " + ', '.join(targets[:12]) + f"{cites}\n")

            # Capabilities
            tools = [t for t in by_field.get('tools', []) if t]
            ttps_items = [
                t for t in by_field.get('ttps', [])
                if t and not re.match(r'^(https?://|//)', t.strip())
            ]
            if tools or ttps_items:
                summary_parts.append("\n**Capabilities**\n")
                if tools:
                    cites = self._format_citations(self._citation_ids_for_chunks(by_field_chunks.get('tools', []), source_index))
                    summary_parts.append("- **Tools & Malware:** " + ', '.join(tools[:12]) + f"{cites}\n")
                if ttps_items:
                    cites = self._format_citations(self._citation_ids_for_chunks(by_field_chunks.get('ttps', []), source_index))
                    summary_parts.append("- **TTPs:** " + ', '.join(ttps_items[:12]) + f"{cites}\n")

            # Campaigns / Operations (only if present in dataset)
            if 'campaigns' in by_field:
                campaigns = []
                for c in by_field['campaigns']:
                    if not c:
                        continue
                    if ' | ' in c:
                        campaigns.extend([item.strip() for item in c.split(' | ') if item.strip()])
                    else:
                        campaigns.append(c)
                if campaigns:
                    recent, older = self._split_campaigns(campaigns, recent_count=5, older_count=15)
                    summary_parts.append("\n**Campaigns & Operations**\n")
                    cites = self._format_citations(self._citation_ids_for_chunks(by_field_chunks.get('campaigns', []), source_index))
                    summary_parts.append(self._format_campaign_table(recent + older, strip_links=is_report_request) + f"{cites}\n")

            if 'counter_operations' in by_field:
                counter_ops = []
                for entry in by_field['counter_operations']:
                    if not entry:
                        continue
                    if ' | ' in entry:
                        counter_ops.extend([item.strip() for item in entry.split(' | ') if item.strip()])
                    else:
                        counter_ops.append(entry)
                if counter_ops:
                    summary_parts.append("\n**Counter Operations**\n")
                    summary_parts.append(self._format_counter_operations_table(counter_ops, strip_links=is_report_request) + "\n")

            if not is_report_request:
                # Sources
                if 'information' in by_field:
                    sources = by_field['information'][:5]
                    if sources:
                        summary_parts.append("\n**Key Sources**\n" + "\n".join(f"- {s}" for s in sources) + "\n")

                if source_index:
                    source_lines = []
                    for entry in list(source_index.values())[:8]:
                        label = entry['label']
                        url = entry['url']
                        if url:
                            source_lines.append(f"- [{entry['id']}] {label} - {url}")
                        else:
                            source_lines.append(f"- [{entry['id']}] {label}")
                    summary_parts.append("\n**Sources**\n" + "\n".join(source_lines) + "\n")
            
            # Supporting evidence note
            if len(evidence) > 1:
                summary_parts.append(f"\n*(Supporting evidence from {len(evidence)-1} additional sources)*")
            
            return '\n'.join(summary_parts)
        
        else:
            # Simple query - provide brief summary
            top_evidence = evidence[0]
            field = top_evidence['metadata'].get('source_field', 'information')

            if field == 'entity_profile' or 'Threat Actor:' in top_evidence.get('text', ''):
                parsed = self._parse_entity_profile_text(top_evidence.get('text', ''))
                if parsed:
                    summary = self._build_concise_entity_summary(parsed)
                else:
                    summary = f"Based on {field} data: {top_evidence['text']}"
            else:
                summary = f"Based on {field} data: {top_evidence['text']}"
            
            if len(evidence) > 1:
                summary += f" (Supporting evidence from {len(evidence)-1} additional sources)"
            
            return summary

    def _build_concise_entity_summary(self, profile: Dict[str, Any]) -> str:
        """Build a concise, focused summary for simple identity questions."""
        name = profile.get('primary_name') or profile.get('name') or 'Unknown'
        aliases = profile.get('aliases', [])
        origin = (profile.get('countries') or [''])[0]
        sponsor = profile.get('sponsor', '')
        first_seen = profile.get('first_seen', '')
        last_seen = profile.get('last_seen') or profile.get('last_updated') or ''
        sectors = profile.get('observed_sectors', [])
        motivations = profile.get('motivations', [])
        tools = profile.get('tools', [])
        ttps = profile.get('ttps', [])

        lines = [f"**Who is {name}?**"]
        if aliases:
            lines.append(f"Also known as: {', '.join(aliases[:8])}.")

        lines.append("\n**Core Profile**")
        threat_type = "Nation-state aligned threat actor" if sponsor or origin else "Threat actor"
        lines.append(f"- Type: {threat_type}")
        if origin:
            lines.append(f"- Origin: {origin}")
        if sponsor:
            lines.append(f"- Sponsorship: {sponsor}")
        if motivations:
            lines.append(f"- Primary motive: {', '.join(motivations[:3])}")
        if first_seen:
            lines.append(f"- Active since: {first_seen}")
        if last_seen:
            lines.append(f"- Last known activity: {last_seen}")

        if sectors:
            lines.append("\n**Common Targets**")
            lines.append("- " + "\n- ".join(sectors[:6]))

        if ttps or tools:
            lines.append("\n**Known Characteristics**")
            if ttps:
                lines.append("- Techniques: " + ", ".join(ttps[:6]))
            if tools:
                lines.append("- Tooling: " + ", ".join(tools[:6]))

        lines.append("\nImportant: Attribution in cyber threat intel is probabilistic; vendors may disagree.")

        return "\n".join(lines)
    
    def _calculate_confidence(self, evidence: List[Dict[str, Any]]) -> float:
        """Calculate overall confidence based on evidence quality."""
        if not evidence:
            return 0.0
        
        avg_similarity = sum(
            chunk.get('similarity_score', 0.5) for chunk in evidence
        ) / len(evidence)
        
        source_penalty = 1.0 if len(evidence) >= 3 else 0.7
        
        confidence = avg_similarity * source_penalty
        return min(confidence, 1.0)
