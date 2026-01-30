"""LLM-based question answering with evidence grounding."""

import logging
from typing import Dict, Any, List
import requests

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
    
    def generate(self, prompt: str, temperature: float = 0.3, max_tokens: int = 512) -> str:
        """
        Generate response from Ollama.
        
        Args:
            prompt: Input prompt
            temperature: Generation temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            
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
            
            response = requests.post(self.api_endpoint, json=payload, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "")
            else:
                logger.error(f"Ollama error: {response.status_code}")
                return ""
                
        except Exception as e:
            logger.error(f"Error calling Ollama: {e}")
            return ""


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
    
    def explain(self, query: str, evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate explanation based on evidence using Ollama.
        
        Args:
            query: User query
            evidence: Retrieved evidence chunks
            
        Returns:
            Explanation response with metadata
        """
        
        if not evidence:
            return {
                'query': query,
                'answer': 'Insufficient evidence to answer this question.',
                'evidence': [],
                'confidence': 0.0,
                'source_count': 0,
                'model': self.llm.model if self.use_ollama else 'fallback',
            }
        
        # Format evidence for LLM
        evidence_text = self._format_evidence_for_llm(evidence)
        
        if self.use_ollama:
            # Use Ollama for generation
            answer = self._generate_with_ollama(query, evidence_text)
        else:
            # Fallback to summary
            answer = self._generate_summary(query, evidence)
        
        return {
            'query': query,
            'answer': answer,
            'evidence': evidence,
            'evidence_formatted': evidence_text,
            'confidence': self._calculate_confidence(evidence),
            'source_count': len(evidence),
            'model': self.llm.model if self.use_ollama else 'fallback',
        }
    
    def _format_evidence_for_llm(self, evidence: List[Dict[str, Any]]) -> str:
        """Format evidence chunks for LLM input."""
        formatted = []
        for i, chunk in enumerate(evidence, 1):
            source = chunk['metadata'].get('source_field', 'unknown')
            score = chunk.get('similarity_score', 0.0)
            text = chunk['text']
            formatted.append(f"[{i}] ({source}, score: {score:.2f}): {text}")
        
        return "\n".join(formatted)
    
    def _generate_with_ollama(self, query: str, evidence_text: str) -> str:
        """Generate response using Ollama LLM."""
        prompt = f"""You are a threat intelligence analyst. Based on the following evidence, answer the user's question concisely and accurately.

EVIDENCE:
{evidence_text}

USER QUESTION: {query}

ANSWER (2-3 sentences):"""
        
        try:
            response = self.llm.generate(prompt, temperature=0.3, max_tokens=300)
            return response.strip() if response else self._generate_summary(query, [])
        except Exception as e:
            logger.error(f"Ollama generation error: {e}")
            return "Error generating response from local LLM."
    
    def _generate_summary(self, query: str, evidence: List[Dict[str, Any]]) -> str:
        """Generate a summary answer from evidence (fallback)."""
        if not evidence:
            return "No relevant information found."
        
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
