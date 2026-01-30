#!/usr/bin/env python
"""Threat-AI: Unified application with CLI and Web UI."""

import logging
import yaml
import sys
import argparse
import webbrowser
import time
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, jsonify

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


def load_config(config_path: str = "config/settings.yaml") -> dict:
    """Load configuration from YAML file."""
    global config
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config


def initialize_components():
    """Initialize all system components."""
    global vector_store, retriever, interpreter, audit, config
    
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
        
        # Initialize retriever
        retriever = EvidenceRetriever(vector_store, embedder)
        logger.info("✓ Retriever initialized")
        
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
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize components: {e}")
        return False


def process_query(query_text: str) -> dict:
    """Process a query and return results."""
    try:
        if not query_text.strip():
            return {'error': 'Query cannot be empty'}
        
        if not retriever or not interpreter:
            return {'error': 'System not initialized'}
        
        logger.info(f"Processing query: {query_text}")
        
        # Retrieve evidence
        ret_config = config.get('retrieval', {})
        evidence = retriever.retrieve(
            query_text,
            top_k=ret_config.get('top_k', 5),
            similarity_threshold=ret_config.get('similarity_threshold', 0.6)
        )
        
        if not evidence:
            return {
                'query': query_text,
                'answer': 'No relevant threat intelligence found for this query.',
                'evidence': [],
                'confidence': 0.0,
                'source_count': 0,
                'model': 'N/A',
                'timestamp': datetime.now().isoformat()
            }
        
        # Generate answer
        result = interpreter.explain(query_text, evidence)
        
        # Log to audit trail
        trace_id = audit.log_query(query_text, result.get('query_type', 'general'), evidence)
        audit.log_response(trace_id, result)
        
        # Format response
        response = {
            'query': query_text,
            'answer': result['answer'],
            'confidence': result['confidence'],
            'source_count': result['source_count'],
            'model': result.get('model', 'N/A'),
            'timestamp': datetime.now().isoformat(),
            'trace_id': trace_id,
            'evidence': [
                {
                    'text': e['text'],
                    'score': round(e.get('similarity_score', 0), 4),
                    'source': e['metadata'].get('source_field', 'unknown'),
                    'actor': e['metadata'].get('actor_name', 'unknown')
                }
                for e in evidence
            ]
        }
        
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
    """Main web interface."""
    return render_template('index.html')


@app.route('/api/query', methods=['POST'])
def web_query():
    """Web API endpoint for queries."""
    try:
        data = request.json
        user_query = data.get('query', '').strip()
        result = process_query(user_query)
        
        if 'error' in result:
            return jsonify(result), 400 if 'empty' in result.get('error', '') else 500
        
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