"""Follow-up Question Suggester for Threat Intelligence Queries.

Generates contextual follow-up questions ONLY from retrieved evidence data.
No hallucination - all suggestions are grounded in fetched vector search results.
"""

import re
from typing import List, Dict, Optional


def _normalize_question_like(text: str) -> str:
    """Normalize text for question-level deduplication."""
    if not text:
        return ""
    normalized = re.sub(r'\s+', ' ', text.strip().lower())
    normalized = re.sub(r'[?.!]+$', '', normalized)
    return normalized


def _question_template_key(text: str) -> str:
    """Map a question to a semantic template key for robust dedupe."""
    normalized = _normalize_question_like(text)
    if not normalized:
        return ''

    templates = [
        (r'^what infrastructure does .+ use$', 'actor_infrastructure'),
        (r'^what malware campaigns has .+ conducted$', 'actor_malware_campaigns'),
        (r'^what vulnerabilities does .+ typically exploit$', 'actor_vulnerabilities'),
        (r'^how does .+ propagate and infect systems$', 'malware_propagation'),
        (r'^what are the detection signatures for .+$', 'malware_signatures'),
        (r'^what defenses work against .+$', 'technique_defenses'),
        (r'^which threat actors use .+$', 'technique_actors'),
        (r'^what exploits target .+$', 'vuln_exploits'),
    ]

    for pattern, key in templates:
        if re.match(pattern, normalized):
            return key

    return ''


def _format_actor_name(name: str) -> str:
    """Format actor names consistently (e.g., apt 28 -> APT28)."""
    value = re.sub(r'\s+', ' ', (name or '').strip())
    if not value:
        return ''

    apt_match = re.match(r'(?i)^apt\s*-?\s*(\d+)$', value)
    if apt_match:
        return f"APT{apt_match.group(1)}"

    return value


def _normalize_actor_label(actor_label: str) -> str:
    """Reduce alias-heavy actor labels to a single readable name.

    Example:
    - "Sofacy, APT 28, Fancy Bear, Sednit" -> "Sofacy"
    """
    if not actor_label:
        return ''

    cleaned = actor_label.strip()
    if not cleaned or cleaned.lower() == 'unknown':
        return ''

    parts = [
        p.strip()
        for p in re.split(r'\s*(?:,|/|\||;|aka)\s*', cleaned, flags=re.IGNORECASE)
        if p and p.strip()
    ]
    if not parts:
        return ''

    # Prefer the first clean alias from metadata for user-facing wording.
    return _format_actor_name(parts[0])


def extract_entities_from_evidence(evidence: List[Dict]) -> Dict[str, set]:
    """Extract threat intelligence entities ONLY from retrieved evidence.
    
    Parses evidence text to identify:
    - Threat actors
    - Malware/tools
    - Techniques (TTPs)
    - Infrastructure elements
    - Vulnerabilities
    
    Args:
        evidence: List of evidence dicts from vector search (each has 'text', 'actor', 'source')
        
    Returns:
        Dict with keys: actors, malware, ttps, infrastructure, vulnerabilities, techniques
        Each key contains a set of unique extracted terms (only from evidence)
    """
    if not evidence:
        return {
            'actors': set(),
            'malware': set(),
            'ttps': set(),
            'infrastructure': set(),
            'vulnerabilities': set(),
            'techniques': set(),
        }
    
    entities = {
        'actors': set(),
        'malware': set(),
        'ttps': set(),
        'infrastructure': set(),
        'vulnerabilities': set(),
        'techniques': set(),
    }
    
    # Extract from actor metadata and text
    for item in evidence:
        # Actor from metadata
        actor = item.get('actor') or item.get('actor_name')
        actor_name = _normalize_actor_label(actor)
        if actor_name:
            entities['actors'].add(actor_name)
        
        # Extract from evidence text
        text = (item.get('text') or '').lower()
        if not text:
            continue
        
        # Malware patterns (common malware names, file hashes)
        malware_patterns = [
            r'\b(?:emotet|trickbot|wanna|dridex|dnloader|cerber|cryptolocker|conflicker|zeus|poison ivy|plugx|keylogger)\b',
            r'\b[a-f0-9]{32}\b',  # MD5 hashes
            r'\b[a-f0-9]{40}\b',  # SHA1 hashes
        ]
        for pattern in malware_patterns:
            matches = re.findall(pattern, text)
            entities['malware'].update(matches)
        
        # Infrastructure (IPs, domains mentioned)
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        ips = re.findall(ip_pattern, text)
        entities['infrastructure'].update(ips)
        
        domain_pattern = r'\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b'
        domains = re.findall(domain_pattern, text)
        entities['infrastructure'].update(domains)
        
        # Vulnerabilities (CVE pattern)
        cve_pattern = r'\bcve-\d{4}-\d+\b'
        cves = re.findall(cve_pattern, text)
        entities['vulnerabilities'].update(cves)
        
        # Techniques (look for common TTP keywords)
        technique_keywords = [
            'lateral movement', 'privilege escalation', 'persistence',
            'credential theft', 'data exfiltration', 'reconnaissance',
            'command and control', 'c2', 'exploitation', 'injection',
            'phishing', 'spear phishing', 'trojan', 'backdoor',
            'worm', 'rootkit', 'ransomware', 'keylogging',
        ]
        for keyword in technique_keywords:
            if keyword in text:
                entities['techniques'].add(keyword)
        
        # TTPs (from MITRE ATT&CK style references)
        ttp_pattern = r'\b(?:T\d{4}|technique|tactic|mitre)\b'
        ttps = re.findall(ttp_pattern, text)
        entities['ttps'].update(ttps)
    
    # Clean up empty strings and convert sets to sorted lists for consistency
    return {
        k: {item.strip() for item in v if item and item.strip()}
        for k, v in entities.items()
    }


def generate_followup_questions(
    user_query: str,
    evidence: List[Dict],
    answer: str = "",
    max_questions: int = 3,
    asked_user_messages: Optional[List[str]] = None,
) -> List[str]:
    """Generate follow-up questions ONLY based on retrieved evidence.
    
    Extracts entities from evidence and creates contextual follow-up questions.
    All questions are answerable from the vector store because they reference
    data that was already retrieved.
    
    Args:
        user_query: Original user question
        evidence: List of evidence dicts from vector search retrieval
        answer: Assistant's answer (optional, for context)
        max_questions: Maximum number of follow-up questions to generate
        
    Returns:
        List of 2-4 follow-up question strings, grounded in evidence
    """
    if not evidence:
        return []
    
    entities = extract_entities_from_evidence(evidence)
    questions = []
    
    # Question 1: About actors (if found in evidence)
    actors = sorted(entities['actors'])[:2]
    if actors:
        for actor in actors:
            if len(questions) < max_questions:
                questions.append(f"What infrastructure does {actor} use?")
            if len(questions) < max_questions:
                questions.append(f"What malware campaigns has {actor} conducted?")
            if len(questions) < max_questions:
                questions.append(f"What vulnerabilities does {actor} typically exploit?")
    
    # Question 2: About malware (if found in evidence)
    malware = list(entities['malware'])[:2]
    if malware:
        for mal in malware:
            if len(questions) < max_questions:
                questions.append(f"How does {mal} propagate and infect systems?")
            if len(questions) < max_questions:
                questions.append(f"What are the detection signatures for {mal}?")
    
    # Question 3: About techniques (if found in evidence)
    techniques = list(entities['techniques'])[:2]
    if techniques:
        for tech in techniques:
            if len(questions) < max_questions:
                questions.append(f"What defenses work against {tech}?")
            if len(questions) < max_questions:
                questions.append(f"Which threat actors use {tech}?")
    
    # Question 4: About vulnerabilities (if found in evidence)
    vulns = list(entities['vulnerabilities'])[:1]
    if vulns:
        for vuln in vulns:
            if len(questions) < max_questions:
                questions.append(f"What exploits target {vuln}?")
    
    # Fallback: Generic follow-ups if not enough specific questions generated
    if len(questions) < 2:
        questions.append("What are the latest campaigns from the threat actors mentioned?")
        questions.append("What industries are most targeted by this threat?")
    
    # Remove duplicates and return up to max_questions
    unique_questions = []
    seen = set()
    asked_set = {
        _normalize_question_like(msg)
        for msg in (asked_user_messages or [])
        if isinstance(msg, str) and msg.strip()
    }
    asked_template_keys = {
        _question_template_key(msg)
        for msg in (asked_user_messages or [])
        if isinstance(msg, str) and msg.strip()
    }
    asked_template_keys.discard('')
    for q in questions:
        q_normalized = _normalize_question_like(q)
        q_template_key = _question_template_key(q)
        if (
            q_normalized
            and q_normalized not in seen
            and q_normalized not in asked_set
            and (not q_template_key or q_template_key not in asked_template_keys)
            and len(unique_questions) < max_questions
        ):
            unique_questions.append(q)
            seen.add(q_normalized)
            if q_template_key:
                asked_template_keys.add(q_template_key)
    
    return unique_questions
