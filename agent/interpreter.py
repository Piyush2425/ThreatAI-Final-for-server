"""LLM-based question answering with evidence grounding."""

import logging
from typing import Dict, Any, List
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
        
        # Extract targeted information based on intent
        extraction_result = self.answer_extractor.extract(evidence, query, intent)
        
        # Determine response strategy
        evidence_text = self._format_evidence_for_llm(evidence)
        
        # For OVERVIEW intent (comprehensive reports), always use LLM if available
        if intent == QueryIntent.OVERVIEW:
            if self.use_ollama:
                logger.info("Generating comprehensive report with LLM")
                answer = self._generate_with_ollama(query, evidence_text, 'report')
                
                # If LLM failed or timed out, use improved fallback
                if not answer or len(answer.strip()) < 50:
                    logger.warning("LLM generation failed or returned short response, using enhanced fallback")
                    answer = self._generate_summary(query, evidence)
            else:
                logger.warning("LLM not available, using fallback summary")
                answer = self._generate_summary(query, evidence)
        
        # For specific extraction intents with results
        elif extraction_result['summary'] and extraction_result['summary'] != "":
            # Use extracted summary as base
            answer = extraction_result['summary']
            
            # Enhance with LLM for certain intents if available
            if self.use_ollama and intent in [QueryIntent.TACTICS, QueryIntent.ASSOCIATIONS, 
                                              QueryIntent.TARGETS, QueryIntent.TOOLS, 
                                              QueryIntent.CAMPAIGNS, QueryIntent.MOTIVATION]:
                logger.info(f"Enhancing {intent.value} answer with LLM")
                llm_answer = self._generate_targeted_answer(query, evidence_text, intent, extraction_result)
                answer = llm_answer if llm_answer and len(llm_answer) > 50 else answer
        
        # Fallback: use LLM or summary
        else:
            if self.use_ollama:
                logger.info("No extraction result, generating with LLM")
                answer = self._generate_with_ollama(query, evidence_text, response_mode)
            else:
                answer = self._generate_summary(query, evidence)
        
        return {
            'query': query,
            'answer': answer,
            'evidence': evidence,
            'evidence_formatted': self._format_evidence_for_llm(evidence),
            'confidence': extraction_result['confidence'],
            'source_count': len(evidence),
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
            if len(text) > max_chars:
                text = text[:max_chars].rstrip() + "..."
            formatted.append(f"[{i}] ({source}, score: {score:.2f}): {text}")
        
        return "\n".join(formatted)
    
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
            QueryIntent.TIMELINE: "Answer specifically about timeline and activity periods. State when they were first seen and their activity history.",
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
    
    def _generate_with_ollama(self, query: str, evidence_text: str, response_mode: str = 'adaptive') -> str:
        """Generate response using Ollama LLM with mode-specific prompt."""
        
        # Load system prompt
        try:
            with open('agent/system_prompt.txt', 'r') as f:
                system_prompt = f.read()
        except:
            system_prompt = "You are a threat intelligence analyst."
        
        # Build mode-specific instruction
        mode_instruction = self._get_mode_instruction(response_mode)
        
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
            # Generate detailed multi-paragraph summary
            summary_parts = []
            
            # Group evidence by source field
            by_field = {}
            for chunk in evidence:
                field = chunk['metadata'].get('source_field', 'description')
                if field not in by_field:
                    by_field[field] = []
                by_field[field].append(chunk['text'])
            
            # Header section
            if 'primary_name' in by_field or 'name' in by_field:
                name = by_field.get('primary_name', by_field.get('name', ['Unknown']))[0]
                summary_parts.append(f"**Threat Actor: {name}**\n")
            
            if 'countries' in by_field:
                origin = by_field['countries'][0]
                summary_parts.append(f"**Origin:** {origin}\n")
            
            if 'sponsor' in by_field:
                sponsor = by_field['sponsor'][0]
                summary_parts.append(f"**Sponsorship:** {sponsor}\n")
            
            if 'first_seen' in by_field or 'first-seen' in by_field:
                first_seen = by_field.get('first_seen', by_field.get('first-seen', ['Unknown']))[0]
                summary_parts.append(f"**First Seen:** {first_seen}\n")
            
            if 'aliases' in by_field and len(by_field['aliases']) > 0:
                aliases = ', '.join(by_field['aliases'][:12])
                summary_parts.append(f"**Also Known As:** {aliases}\n")
            
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
                summary_parts.append(f"\n**Motivation**\n{motivations}\n")
            
            # Targets / Sectors
            if 'observed_sectors' in by_field or 'observed-sectors' in by_field:
                sectors = by_field.get('observed_sectors', by_field.get('observed-sectors', []))
                if sectors:
                    summary_parts.append("\n**Observed Sectors**\n" + ', '.join(sectors[:12]) + "\n")
            
            if 'observed_countries' in by_field or 'observed-countries' in by_field:
                countries = by_field.get('observed_countries', by_field.get('observed-countries', []))
                if countries:
                    summary_parts.append("\n**Observed Countries**\n" + ', '.join(countries[:15]) + "\n")
            
            # Tools / Malware
            if 'tools' in by_field:
                tools = ', '.join(by_field['tools'][:12])
                summary_parts.append(f"\n**Known Tools & Malware**\n{tools}\n")
            
            # Sources
            if 'information' in by_field:
                sources = by_field['information'][:5]
                if sources:
                    summary_parts.append("\n**Key Sources**\n" + "\n".join(f"- {s}" for s in sources) + "\n")
            
            # Supporting evidence note
            if len(evidence) > 1:
                summary_parts.append(f"\n*(Supporting evidence from {len(evidence)-1} additional sources)*")
            
            return '\n'.join(summary_parts)
        
        else:
            # Simple query - provide brief summary
            top_evidence = evidence[0]
            field = top_evidence['metadata'].get('source_field', 'information')
            
            summary = f"Based on {field} data: {top_evidence['text']}"
            
            if len(evidence) > 1:
                summary += f" (Supporting evidence from {len(evidence)-1} additional sources)"
            
            return summary
    
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
