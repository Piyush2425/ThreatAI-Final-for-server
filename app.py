#!/usr/bin/env python
"""Threat-AI: Unified application with CLI and Web UI."""

import logging
import yaml
import sys
import argparse
import webbrowser
import time
import io
import json
import re
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file
from functools import lru_cache
import hashlib

from training_lab import TrainingLabManager

# Import intent detection from dedicated module
from agent.intent_detector import (
    is_report_request,
    contains_threat_context_terms,
    is_short_report_followup,
    is_simple_confirmation,
    get_latest_substantive_user_query,
    last_assistant_message_had_report_suggestion,
    should_offer_report_suggestion,
)

# Import follow-up question suggester
from agent.follow_up_suggester import generate_followup_questions

# Import response streaming for token-by-token progressive reveal
from agent.response_streamer import ResponseStreamer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global components
vector_store = None
retriever = None
interpreter = None
audit = None
config = None
conversation_manager = None
training_lab_manager = None

# Simple query cache (for development - consider Redis for production)
query_cache = {}


def _extract_focus_actor(query_text: str, result: dict) -> str:
    """Extract a best-effort primary actor for report CTA wording."""
    if result:
        primary_actors = result.get('primary_actors') or []
        if isinstance(primary_actors, list) and primary_actors:
            actor = primary_actors[0]
            if isinstance(actor, str) and actor.strip():
                return actor.strip()

        for item in result.get('evidence', []) or []:
            actor = (item.get('actor') or '').strip() if isinstance(item, dict) else ''
            if actor and actor.lower() != 'unknown':
                return actor

    query = query_text or ''
    apt_match = re.search(r'\bapt\s*-?\s*(\d+)\b', query, flags=re.IGNORECASE)
    if apt_match:
        return f"APT{apt_match.group(1)}"

    return ''


def build_report_suggestion_text(query_text: str, result: dict) -> str:
    """Build contextual report suggestion text anchored to the detected actor."""
    focus_actor = _extract_focus_actor(query_text, result)
    if focus_actor:
        return (
            f"Can I generate a full profile report on {focus_actor}? "
            "Reply with: yes generate report."
        )
    return (
        'Would you like me to generate a downloadable report from this answer? '
        'Reply with: yes generate report.'
    )


def load_config(config_path: str = "config/settings.yaml") -> dict:
    """Load configuration from YAML file."""
    global config
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config


def initialize_components():
    """Initialize all system components."""
    global vector_store, retriever, interpreter, audit, config, conversation_manager, training_lab_manager
    
    logger.info("Initializing components...")
    
    try:
        load_config()
        
        from embeddings.vector_store import VectorStore
        from embeddings.embedder import LocalEmbedder
        from retrieval.retrieve import EvidenceRetriever
        from agent.interpreter import EvidenceBasedInterpreter
        from evaluation.audit import AuditTrail
        
        # Initialize vector store
        vs_config = config.get('vector_store', {})
        vector_store = VectorStore(
            dimension=config.get('embeddings', {}).get('embedding_dim', 384),
            persist_directory=vs_config.get('persist_directory', 'data/chroma_db')
        )
        logger.info("✓ Vector store initialized")
        
        # Initialize embedder
        emb_config = config.get('embeddings', {})
        embedder = LocalEmbedder(
            model_name=emb_config.get('model', 'sentence-transformers/all-MiniLM-L6-v2'),
            batch_size=emb_config.get('batch_size', 32)
        )
        logger.info("✓ Embedder initialized")
        
        # Initialize retriever with hybrid search weights
        retrieval_config = config.get('retrieval', {})
        retriever = EvidenceRetriever(
            vector_store, 
            embedder,
            bm25_weight=retrieval_config.get('bm25_weight', 0.3),
            vector_weight=retrieval_config.get('vector_weight', 0.7)
        )
        logger.info("✓ Retriever initialized (hybrid mode)")
        
        # Initialize interpreter
        ollama_config = config.get('ollama', {})
        interpreter = EvidenceBasedInterpreter(
            model=ollama_config.get('model', 'llama3:8b'),
            base_url=ollama_config.get('host', 'http://localhost:11434')
        )
        logger.info(f"✓ Interpreter initialized: {'Ollama' if interpreter.use_ollama else 'Fallback'}")
        
        # Initialize audit trail
        audit = AuditTrail()
        logger.info("✓ Audit trail initialized")
        
        # Initialize conversation manager
        from conversation import ConversationManager
        conversation_manager = ConversationManager()
        logger.info("✓ Conversation manager initialized")

        # Initialize training lab manager (resumable local-LLM evaluator)
        training_lab_manager = TrainingLabManager(
            root_dir=Path('training_lab'),
            actors_path=Path('data/canonical/actors.json'),
            ollama_base_url=ollama_config.get('host', 'http://localhost:11434'),
            default_model=None,
            project_answer_fn=lambda q: process_query(q, use_cache=False),
        )
        logger.info("✓ Training lab manager initialized")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize components: {e}")
        return False


def process_query(query_text: str, use_cache: bool = True) -> dict:
    """Process a query and return results."""
    import time
    start_time = time.time()
    
    try:
        if not query_text.strip():
            return {'error': 'Query cannot be empty'}
        
        if not retriever or not interpreter:
            return {'error': 'System not initialized'}
        
        # Check cache first
        cache_key = hashlib.md5(query_text.lower().strip().encode()).hexdigest()
        if use_cache and cache_key in query_cache:
            cached_result = query_cache[cache_key]
            # Check if cache is fresh (less than 1 hour old)
            cache_age = time.time() - cached_result.get('cached_at', 0)
            if cache_age < 3600:  # 1 hour
                logger.info(f"⚡ Cache hit! Returning cached result (age: {cache_age:.0f}s)")
                cached_result['from_cache'] = True
                cached_result['processing_time'] = time.time() - start_time
                return cached_result
        
        logger.info(f"Processing query: {query_text}")
        
        # Retrieve evidence (returns dict with evidence, response_mode, parsed_query)
        retrieval_start = time.time()
        ret_config = config.get('retrieval', {})
        retrieval_result = retriever.retrieve(
            query_text,
            top_k=ret_config.get('top_k', 5),
            similarity_threshold=ret_config.get('similarity_threshold', 0.3)
        )
        retrieval_time = time.time() - retrieval_start
        logger.info(f"⏱️ Retrieval completed in {retrieval_time:.2f}s")
        
        evidence = retrieval_result.get('evidence', [])
        response_mode = retrieval_result.get('response_mode', 'adaptive')
        parsed_query = retrieval_result.get('parsed_query') or {}
        primary_actors = [
            actor.get('primary_name')
            for actor in parsed_query.get('actors', [])
            if actor.get('primary_name')
        ]
        if not primary_actors and evidence:
            seen = set()
            ordered = []
            for chunk in evidence:
                primary = chunk.get('metadata', {}).get('primary_name')
                if primary and primary not in seen:
                    seen.add(primary)
                    ordered.append(primary)
            primary_actors = ordered
        
        if not evidence:
            result = {
                'query': query_text,
                'answer': 'No relevant threat intelligence found for this query.',
                'evidence': [],
                'confidence': 0.0,
                'source_count': 0,
                'model': 'N/A',
                'timestamp': datetime.now().isoformat(),
                'response_mode': response_mode,
                'primary_actors': primary_actors,
                'processing_time': time.time() - start_time,
                'from_cache': False
            }
            return result
        
        # Generate answer with adaptive response mode
        generation_start = time.time()
        result = interpreter.explain(query_text, evidence, response_mode=response_mode)
        generation_time = time.time() - generation_start
        logger.info(f"⏱️ Answer generation completed in {generation_time:.2f}s")
        
        # Log to audit trail (do this asynchronously to not block response)
        audit_start = time.time()
        trace_id = audit.log_query(query_text, result.get('query_type', 'general'), evidence)
        audit.log_response(trace_id, result)
        audit_time = time.time() - audit_start
        logger.info(f"⏱️ Audit logging completed in {audit_time:.2f}s")
        
        total_time = time.time() - start_time
        logger.info(f"⏱️ Total query processing time: {total_time:.2f}s")
        
        # Format response
        response = {
            'query': query_text,
            'answer': result['answer'],
            'confidence': result['confidence'],
            'source_count': result['source_count'],
            'model': result.get('model', 'N/A'),
            'timestamp': datetime.now().isoformat(),
            'trace_id': trace_id,
            'response_mode': response_mode,
            'primary_actors': primary_actors,
            'processing_time': total_time,
            'from_cache': False,
            'timings': {
                'retrieval': retrieval_time,
                'generation': generation_time,
                'audit': audit_time,
                'total': total_time
            },
            'evidence': [
                {
                    'text': e['text'],
                    'score': round(e.get('similarity_score', 0), 4),
                    'source': e['metadata'].get('source_field', 'unknown'),
                    'actor': e['metadata'].get('actor_name', 'unknown'),
                    'links': e['metadata'].get('information_sources', [])
                }
                for e in evidence
            ]
        }
        
        # Cache the result (limit cache size to prevent memory issues)
        if use_cache:
            response['cached_at'] = time.time()
            query_cache[cache_key] = response.copy()
            
            # Keep cache size reasonable (max 100 queries)
            if len(query_cache) > 100:
                # Remove oldest entry
                oldest_key = min(query_cache.keys(), 
                               key=lambda k: query_cache[k].get('cached_at', 0))
                del query_cache[oldest_key]
                logger.info("🗑️ Cache cleaned - removed oldest entry")
        
        logger.info("✓ Query processed successfully")
        return response
        
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        return {'error': str(e)}


# ==================== WEB UI ROUTES ====================

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['JSON_SORT_KEYS'] = False


@app.route('/')
def index():
    """Main chat interface."""
    return render_template('chat.html')


@app.route('/old')
def old_interface():
    """Old Q&A interface."""
    return render_template('index.html')


@app.route('/training-lab')
def training_lab_dashboard():
    """Training lab dashboard UI."""
    dashboard_path = Path('training_lab') / 'dashboard.html'
    return send_file(dashboard_path)


@app.route('/api/training/models', methods=['GET'])
def training_models():
    """List available local models and recommended default for laptop-friendly runs."""
    try:
        if training_lab_manager is None:
            return jsonify({'error': 'Training lab is not initialized'}), 500

        return jsonify({
            'available_models': training_lab_manager.available_models(),
            'recommended_model': training_lab_manager.recommend_model(),
            'answer_sources': training_lab_manager.available_answer_sources(),
            'recommended_answer_source': 'main_project',
            'note': 'Recommended order favors lightweight local models for laptop usage.'
        })
    except Exception as e:
        logger.error(f"Error getting training models: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/training/start', methods=['POST'])
def training_start():
    """Start a new resumable training run."""
    try:
        if training_lab_manager is None:
            return jsonify({'error': 'Training lab is not initialized'}), 500

        data = request.json or {}
        result = training_lab_manager.start_run(
            model=data.get('model'),
            min_questions_per_actor=int(data.get('min_questions_per_actor', 3)),
            max_questions_per_actor=int(data.get('max_questions_per_actor', 10)),
            answer_source=data.get('answer_source', 'main_project'),
        )
        if 'error' in result:
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error starting training run: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/training/stop', methods=['POST'])
def training_stop():
    """Pause active training run. Resume continues from saved endpoint."""
    try:
        if training_lab_manager is None:
            return jsonify({'error': 'Training lab is not initialized'}), 500

        result = training_lab_manager.stop_run()
        if 'error' in result:
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error stopping training run: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/training/resume', methods=['POST'])
def training_resume():
    """Resume an existing paused run from saved actor/question position."""
    try:
        if training_lab_manager is None:
            return jsonify({'error': 'Training lab is not initialized'}), 500

        data = request.json or {}
        run_id = (data.get('run_id') or '').strip()
        if not run_id:
            return jsonify({'error': 'run_id is required'}), 400

        result = training_lab_manager.resume_run(run_id)
        if 'error' in result:
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error resuming training run: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/training/status', methods=['GET'])
def training_status():
    """Get active or latest training run status."""
    try:
        if training_lab_manager is None:
            return jsonify({'error': 'Training lab is not initialized'}), 500

        run_id = request.args.get('run_id')
        result = training_lab_manager.get_state(run_id=run_id)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting training status: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/training/runs', methods=['GET'])
def training_runs():
    """List recent training runs."""
    try:
        if training_lab_manager is None:
            return jsonify({'error': 'Training lab is not initialized'}), 500

        limit = int(request.args.get('limit', 20))
        return jsonify({'runs': training_lab_manager.list_runs(limit=limit)})
    except Exception as e:
        logger.error(f"Error listing training runs: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/training/records', methods=['GET'])
def training_records():
    """Get stored question/answer/evaluation records for a run."""
    try:
        if training_lab_manager is None:
            return jsonify({'error': 'Training lab is not initialized'}), 500

        run_id = (request.args.get('run_id') or '').strip()
        if not run_id:
            return jsonify({'error': 'run_id is required'}), 400

        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        return jsonify(training_lab_manager.get_records(run_id=run_id, limit=limit, offset=offset))
    except Exception as e:
        logger.error(f"Error getting training records: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/query', methods=['POST'])
def web_query():
    """Web API endpoint for queries."""
    try:
        data = request.json
        user_query = data.get('query', '').strip()
        result = process_query(user_query)
        
        if 'error' in result:
            return jsonify(result), 400 if 'empty' in result.get('error', '') else 500
        
        # Save to query history
        from history import QueryHistory
        history = QueryHistory()
        history.save_query(user_query, result)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in web_query: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/status')
def status():
    """Get system status."""
    try:
        status_info = {
            'llm_mode': 'Ollama' if interpreter and interpreter.use_ollama else 'Fallback/Unavailable',
            'model': config.get('ollama', {}).get('model', 'N/A') if config else 'N/A',
            'host': config.get('ollama', {}).get('host', 'N/A') if config else 'N/A',
            'initialized': vector_store is not None and retriever is not None and interpreter is not None
        }
        return jsonify(status_info)
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/samples')
def samples():
    """Get sample queries."""
    samples_list = [
        "What are common tactics used by APT28?",
        "Describe REvil ransomware variants",
        "What vulnerabilities does Lazarus Group exploit?",
        "How does Emotet propagate?",
        "What infrastructure does Turla use?"
    ]
    return jsonify({'samples': samples_list})


@app.route('/api/feedback', methods=['POST'])
def submit_feedback():
    """Submit feedback for a query response."""
    try:
        data = request.json
        
        from feedback.store import FeedbackStore
        
        feedback_data = {
            'query': data.get('query'),
            'answer': data.get('answer'),
            'trace_id': data.get('trace_id'),
            'model': data.get('model'),
            'source_count': data.get('source_count'),
            'confidence': data.get('confidence'),
            'response_id': data.get('response_id'),
            'rating': data.get('rating', 0),
            'relevance': data.get('relevance'),
            'accuracy': data.get('accuracy'),
            'completeness': data.get('completeness'),
            'comments': data.get('comments'),
            'corrections': data.get('corrections')
        }
        
        feedback_store = FeedbackStore()
        feedback_id = feedback_store.store_feedback(feedback_data)
        
        logger.info(f"Feedback submitted: {feedback_id}")
        return jsonify({
            'success': True,
            'feedback_id': feedback_id,
            'message': 'Thank you for your feedback!'
        })
        
    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/export/pdf', methods=['POST'])
def export_pdf():
    """Export query result as PDF."""
    try:
        from export.report_generator import ReportGenerator
        
        data = request.json
        result = data.get('result', {})
        
        if not result:
            return jsonify({'error': 'No result data provided'}), 400
        
        pdf_bytes = ReportGenerator.generate_pdf(result)
        
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"threat-intelligence-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"
        )
        
    except Exception as e:
        logger.error(f"Error exporting PDF: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/export/csv', methods=['POST'])
def export_csv():
    """Export query result as CSV."""
    try:
        from export.report_generator import ReportGenerator
        
        data = request.json
        result = data.get('result', {})
        
        if not result:
            return jsonify({'error': 'No result data provided'}), 400
        
        csv_data = ReportGenerator.generate_csv(result)
        
        return send_file(
            io.BytesIO(csv_data.encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f"threat-intelligence-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
        )
        
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== QUERY HISTORY ROUTES ====================

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get query history."""
    try:
        from history import QueryHistory
        
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        history = QueryHistory()
        queries = history.get_all_queries(limit=limit, offset=offset)
        stats = history.get_stats()
        
        return jsonify({
            'queries': queries,
            'stats': stats
        })
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/history/search', methods=['GET'])
def search_history():
    """Search query history."""
    try:
        from history import QueryHistory
        
        search_term = request.args.get('q', '').strip()
        if not search_term:
            return jsonify({'error': 'Search term required'}), 400
        
        history = QueryHistory()
        queries = history.search_queries(search_term)
        
        return jsonify({'queries': queries})
    except Exception as e:
        logger.error(f"Error searching history: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/history/<query_id>', methods=['GET'])
def get_query_detail(query_id):
    """Get specific query from history."""
    try:
        from history import QueryHistory
        
        history = QueryHistory()
        query = history.get_query(query_id)
        
        if not query:
            return jsonify({'error': 'Query not found'}), 404
        
        return jsonify(query)
    except Exception as e:
        logger.error(f"Error fetching query: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/history/<query_id>', methods=['DELETE'])
def delete_query_history(query_id):
    """Delete query from history."""
    try:
        from history import QueryHistory
        
        history = QueryHistory()
        deleted = history.delete_query(query_id)
        
        if not deleted:
            return jsonify({'error': 'Query not found'}), 404
        
        return jsonify({'success': True, 'message': 'Query deleted'})
    except Exception as e:
        logger.error(f"Error deleting query: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/history/clear', methods=['POST'])
def clear_history():
    """Clear all query history."""
    try:
        from history import QueryHistory
        
        history = QueryHistory()
        history.clear_all()
        
        return jsonify({'success': True, 'message': 'History cleared'})
    except Exception as e:
        logger.error(f"Error clearing history: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== CONVERSATION API ROUTES ====================

@app.route('/api/conversations', methods=['POST'])
def create_conversation():
    """Create a new conversation."""
    try:
        data = request.json or {}
        title = data.get('title', 'New Chat')
        
        conv_id = conversation_manager.create_conversation(title)
        return jsonify({'conversation_id': conv_id, 'title': title})
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/conversations', methods=['GET'])
def list_conversations():
    """List all conversations."""
    try:
        limit = int(request.args.get('limit', 50))
        conversations = conversation_manager.list_conversations(limit)
        return jsonify({'conversations': conversations})
    except Exception as e:
        logger.error(f"Error listing conversations: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/conversations/<conv_id>', methods=['GET'])
def get_conversation(conv_id):
    """Get a specific conversation with full history."""
    try:
        conversation = conversation_manager.get_conversation(conv_id)
        if not conversation:
            return jsonify({'error': 'Conversation not found'}), 404
        
        return jsonify(conversation.to_dict())
    except Exception as e:
        logger.error(f"Error getting conversation: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/conversations/<conv_id>', methods=['DELETE'])
def delete_conversation(conv_id):
    """Delete a conversation."""
    try:
        success = conversation_manager.delete_conversation(conv_id)
        if success:
            return jsonify({'success': True, 'message': 'Conversation deleted'})
        return jsonify({'error': 'Conversation not found'}), 404
    except Exception as e:
        logger.error(f"Error deleting conversation: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/conversations/<conv_id>/message', methods=['POST'])
def send_message(conv_id):
    """Send a message in a conversation and get AI response."""
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        report_requested = is_report_request(user_message)
        
        if not user_message:
            return jsonify({'error': 'Message cannot be empty'}), 400
        
        # Get or create conversation
        conversation = conversation_manager.get_conversation(conv_id)
        if not conversation:
            return jsonify({'error': 'Conversation not found'}), 404
        
        # Add user message to conversation
        conversation.add_message('user', user_message)
        
        # For short report confirmations, reuse the previous substantive query.
        fallback_query = get_latest_substantive_user_query(conversation, user_message)
        
        # Check if this is a report request (explicit or via simple confirmation after suggestion)
        last_had_suggestion = last_assistant_message_had_report_suggestion(conversation)
        is_simple_confirm = is_simple_confirmation(user_message)
        implicit_report_request = is_simple_confirm and last_had_suggestion
        
        use_context_query_for_report = (
            (report_requested or implicit_report_request)
            and (is_short_report_followup(user_message) or is_simple_confirm or not contains_threat_context_terms(user_message))
            and bool(fallback_query)
        )
        effective_query = fallback_query if use_context_query_for_report else user_message
        
        # Elevate implicit report to explicit for consistent processing downstream
        if implicit_report_request and not report_requested:
            report_requested = True
        
        # Process query with context
        result = process_query(effective_query)
        
        if 'error' in result:
            return jsonify(result), 400 if 'empty' in result.get('error', '') else 500
        
        assistant_message = result['answer']
        if report_requested and use_context_query_for_report:
            focus_actor = _extract_focus_actor(effective_query, result)
            if focus_actor:
                assistant_message = (
                    f"Understood. I prepared this report context for {focus_actor}.\n\n{result['answer']}"
                )
            else:
                assistant_message = (
                    f"Understood. I used your previous request to prepare this report context.\n\n{result['answer']}"
                )

        report_suggestion_text = build_report_suggestion_text(effective_query, result)
        focus_actor = _extract_focus_actor(effective_query, result)
        report_suggestion = (
            (not report_requested and bool(focus_actor))
            or should_offer_report_suggestion(result, report_requested)
        )

        asked_user_messages = [
            (msg.get('content') or '')
            for msg in getattr(conversation, 'messages', [])
            if msg.get('role') == 'user'
        ]
        
        # Generate follow-up questions based ONLY on retrieved evidence
        followup_questions = generate_followup_questions(
            user_query=effective_query,
            evidence=result.get('evidence', []),
            answer=assistant_message,
            max_questions=3,
            asked_user_messages=asked_user_messages,
        )

        # Add assistant response to conversation with metadata
        conversation.add_message('assistant', assistant_message, {
            'confidence': result.get('confidence'),
            'evidence': result.get('evidence', []),
            'trace_id': result.get('trace_id'),
            'model': result.get('model'),
            'source_count': result.get('source_count'),
            'report_requested': report_requested,
            'report_suggestion': report_suggestion,
            'report_suggestion_text': report_suggestion_text,
            'effective_query': effective_query,
            'used_context_query': use_context_query_for_report,
            'followup_questions': followup_questions,
        })
        
        # Save conversation
        conversation_manager.save_conversation(conv_id)
        
        # Return the full response
        return jsonify({
            'conversation_id': conv_id,
            'user_message': user_message,
            'assistant_message': assistant_message,
            'metadata': {
                'confidence': result.get('confidence'),
                'evidence': result.get('evidence', []),
                'trace_id': result.get('trace_id'),
                'model': result.get('model'),
                'source_count': result.get('source_count'),
                'report_requested': report_requested,
                'report_suggestion': report_suggestion,
                'report_suggestion_text': report_suggestion_text,
                'effective_query': effective_query,
                'used_context_query': use_context_query_for_report,
                'followup_questions': followup_questions,
                'timestamp': result.get('timestamp')
            }
        })
        
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/conversations/<conv_id>/message/stream', methods=['POST'])
def stream_message(conv_id):
    """Stream a message response token-by-token with progressive reveal.
    
    Returns: Server-Sent Events (SSE) stream with:
    - 'token' events: Individual tokens with configurable delay
    - 'complete' event: Full metadata and follow-up questions when done
    """
    from flask import Response
    
    # Extract request data BEFORE generator (while request context is active)
    data = request.json or {}
    user_message = data.get('message', '').strip()
    
    def generate_stream():
        try:
            report_requested = is_report_request(user_message)
            
            if not user_message:
                yield f"data: {json.dumps({'error': 'Message cannot be empty'})}\n\n"
                return
            
            # Get or create conversation
            conversation = conversation_manager.get_conversation(conv_id)
            if not conversation:
                yield f"data: {json.dumps({'error': 'Conversation not found'})}\n\n"
                return
            
            # Add user message to conversation
            conversation.add_message('user', user_message)
            
            # For short report confirmations, reuse the previous substantive query
            fallback_query = get_latest_substantive_user_query(conversation, user_message)
            last_had_suggestion = last_assistant_message_had_report_suggestion(conversation)
            is_simple_confirm = is_simple_confirmation(user_message)
            implicit_report_request = is_simple_confirm and last_had_suggestion
            
            use_context_query_for_report = (
                (report_requested or implicit_report_request)
                and (is_short_report_followup(user_message) or is_simple_confirm or not contains_threat_context_terms(user_message))
                and bool(fallback_query)
            )
            effective_query = fallback_query if use_context_query_for_report else user_message
            
            if implicit_report_request and not report_requested:
                report_requested = True
            
            # Process query once (complete answer)
            result = process_query(effective_query)
            
            if 'error' in result:
                yield f"data: {json.dumps(result)}\n\n"
                return
            
            assistant_message = result['answer']
            if report_requested and use_context_query_for_report:
                focus_actor = _extract_focus_actor(effective_query, result)
                if focus_actor:
                    assistant_message = (
                        f"Understood. I prepared this report context for {focus_actor}.\n\n{result['answer']}"
                    )
                else:
                    assistant_message = (
                        f"Understood. I used your previous request to prepare this report context.\n\n{result['answer']}"
                    )
            
            report_suggestion_text = build_report_suggestion_text(effective_query, result)
            focus_actor = _extract_focus_actor(effective_query, result)
            report_suggestion = (
                (not report_requested and bool(focus_actor))
                or should_offer_report_suggestion(result, report_requested)
            )

            asked_user_messages = [
                (msg.get('content') or '')
                for msg in getattr(conversation, 'messages', [])
                if msg.get('role') == 'user'
            ]
            
            # Generate follow-up questions
            followup_questions = generate_followup_questions(
                user_query=effective_query,
                evidence=result.get('evidence', []),
                answer=assistant_message,
                max_questions=3,
                asked_user_messages=asked_user_messages,
            )
            
            # Prepare metadata
            metadata = {
                'conversation_id': conv_id,
                'user_message': user_message,
                'confidence': result.get('confidence'),
                'evidence': result.get('evidence', []),
                'trace_id': result.get('trace_id'),
                'model': result.get('model'),
                'source_count': result.get('source_count'),
                'report_requested': report_requested,
                'report_suggestion': report_suggestion,
                'report_suggestion_text': report_suggestion_text,
                'effective_query': effective_query,
                'used_context_query': use_context_query_for_report,
                'timestamp': result.get('timestamp')
            }
            
            # Create streaming chunks and yield them
            for chunk in ResponseStreamer.create_stream_chunks(
                answer_text=assistant_message,
                followup_questions=followup_questions,
                metadata=metadata
            ):
                stream_data = ResponseStreamer.serialize_stream_chunk(chunk)
                yield f"data: {stream_data}\n\n"
            
            # Add to conversation after streaming completes
            conversation.add_message('assistant', assistant_message, {
                'confidence': result.get('confidence'),
                'evidence': result.get('evidence', []),
                'trace_id': result.get('trace_id'),
                'model': result.get('model'),
                'source_count': result.get('source_count'),
                'report_requested': report_requested,
                'report_suggestion': report_suggestion,
                'report_suggestion_text': report_suggestion_text,
                'effective_query': effective_query,
                'used_context_query': use_context_query_for_report,
                'followup_questions': followup_questions,
            })
            
            conversation_manager.save_conversation(conv_id)
            
        except Exception as e:
            logger.error(f"Error in stream_message: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return Response(generate_stream(), mimetype='text/event-stream')


# ==================== CLI INTERFACE ====================

def run_cli():
    """Run CLI interface."""
    logger.info("\n" + "="*50)
    logger.info("THREAT-AI CLI MODE")
    logger.info("="*50)
    logger.info("Enter queries (type 'quit' to exit):\n")
    
    while True:
        try:
            query = input("\n> Query: ").strip()
            
            if query.lower() in ['quit', 'exit', 'q']:
                logger.info("Exiting...")
                break
            
            if not query:
                continue
            
            result = process_query(query)
            
            # Display results
            print("\n" + "="*50)
            print("RESPONSE")
            print("="*50)
            print(f"Query: {result.get('query', 'N/A')}")
            print(f"Answer: {result.get('answer', 'N/A')}")
            
            if 'error' not in result:
                confidence = result.get('confidence', 0.0)
                print(f"Confidence: {confidence:.0%}")
                print(f"Evidence sources: {result.get('source_count', 0)}")
                print(f"Trace ID: {result.get('trace_id', 'N/A')}")
                
                # Show evidence
                evidence = result.get('evidence', [])
                if evidence:
                    print("\nEvidence:")
                    for i, chunk in enumerate(evidence, 1):
                        score = chunk.get('score', 0.0)
                        source = chunk['source']
                        actor = chunk.get('actor', 'unknown')
                        print(f"  [{i}] ({actor} - {source}, score: {score:.2f})")
                        print(f"      {chunk['text'][:100]}...")
            else:
                print(f"Error: {result.get('error', 'Unknown error')}")
            
        except KeyboardInterrupt:
            logger.info("\n\nInterrupted by user.")
            break
        except Exception as e:
            logger.error(f"Error: {e}")


def run_web_ui(port=5000, open_browser=True):
    """Run web UI."""
    logger.info("\n" + "="*50)
    logger.info("THREAT-AI WEB UI MODE")
    logger.info("="*50)
    logger.info(f"Starting web server on http://localhost:{port}")
    logger.info("Press Ctrl+C to stop\n")
    
    # Open browser if requested
    if open_browser:
        time.sleep(1.5)
        try:
            webbrowser.open(f'http://localhost:{port}')
            logger.info(f"✓ Browser opened\n")
        except:
            logger.warning(f"⚠ Could not open browser - navigate to http://localhost:{port} manually\n")
    
    try:
        app.run(debug=False, host='127.0.0.1', port=port, use_reloader=False)
    except KeyboardInterrupt:
        logger.info("\n✓ Server stopped")


def main():
    """Main entrypoint."""
    parser = argparse.ArgumentParser(
        description='Threat-AI: Evidence-Based Threat Intelligence System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python app.py --web                    Run web UI (default, opens browser)
  python app.py --web --port 8000        Run web UI on custom port
  python app.py --web --no-browser       Run web UI without opening browser
  python app.py --cli                    Run CLI interface
        """
    )
    
    parser.add_argument(
        '--web',
        action='store_true',
        help='Run web UI (default mode)'
    )
    parser.add_argument(
        '--cli',
        action='store_true',
        help='Run CLI interface'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=5000,
        help='Port for web UI (default: 5000)'
    )
    parser.add_argument(
        '--no-browser',
        action='store_true',
        help='Do not open browser automatically'
    )
    
    args = parser.parse_args()
    
    # Default to web UI if no mode specified
    if not args.web and not args.cli:
        args.web = True
    
    logger.info("Starting Threat-AI MVP...")
    
    try:
        # Initialize components
        if not initialize_components():
            logger.error("Failed to initialize system components.")
            sys.exit(1)
        
        logger.info("\n" + "="*50)
        logger.info("SYSTEM READY FOR QUERIES")
        logger.info("="*50)
        
        # Run selected mode
        if args.cli:
            run_cli()
        else:  # web UI
            run_web_ui(port=args.port, open_browser=not args.no_browser)
    
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()