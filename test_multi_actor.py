#!/usr/bin/env python
"""Test multi-actor conversation flows with comparison support."""

import logging
import time
import json
from pathlib import Path
from app import initialize_components, process_query
from conversation import ConversationManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_multi_turn_conversation():
    """Test multi-turn conversation with actor context caching."""
    print("=" * 80)
    print("TEST 1: Multi-Turn Conversation with Actor Caching")
    print("=" * 80)
    
    # Initialize components
    if not initialize_components():
        logger.error("Failed to initialize components")
        return
    
    # Create conversation
    conversation_id = f"test_conv_{int(time.time())}"
    conversation_manager = ConversationManager()
    
    # Query 1: APT28 information
    print("\n📝 Query 1: What are APT28's common attack tactics?")
    start = time.time()
    result1 = process_query(
        "What are APT28's common attack tactics?",
        conversation_id=conversation_id
    )
    elapsed = time.time() - start
    
    print(f"✓ Completed in {elapsed:.2f}s")
    print(f"  Actors: {result1.get('primary_actors', [])}")
    print(f"  Confidence: {result1.get('confidence', 0):.2%}")
    print(f"  Answer preview: {result1['answer'][:200]}...")
    
    # Query 2: Follow-up on same actor
    print("\n📝 Query 2: What tools does APT28 use?")
    start = time.time()
    result2 = process_query(
        "What tools does APT28 use?",
        conversation_id=conversation_id
    )
    elapsed = time.time() - start
    
    print(f"✓ Completed in {elapsed:.2f}s")
    print(f"  Answer preview: {result2['answer'][:200]}...")
    
    # Query 3: Context switch to different actor
    print("\n📝 Query 3: Tell me about TA558 instead")
    start = time.time()
    result3 = process_query(
        "Tell me about TA558 instead",
        conversation_id=conversation_id
    )
    elapsed = time.time() - start
    
    print(f"✓ Completed in {elapsed:.2f}s")
    print(f"  Actors: {result3.get('primary_actors', [])}")
    print(f"  Answer preview: {result3['answer'][:200]}...")
    
    # Verify conversation state
    conversation = conversation_manager.load_or_create_conversation(conversation_id)
    print(f"\n📊 Conversation State:")
    print(f"  Total messages: {len(conversation.messages)}")
    print(f"  Actors mentioned: {conversation.actors_mentioned}")
    print(f"  Current actor: {conversation.current_actor}")
    print(f"  Cached actors: {list(conversation.actor_chunks_cache.keys())}")


def test_comparison_queries():
    """Test comparison queries between multiple actors."""
    print("\n" + "=" * 80)
    print("TEST 2: Actor Comparison Queries")
    print("=" * 80)
    
    # Initialize components
    if not initialize_components():
        logger.error("Failed to initialize components")
        return
    
    # Create new conversation for comparison test
    conversation_id = f"test_comp_{int(time.time())}"
    
    # Comparison query
    print("\n📝 Query: Compare APT28 and TA558 in terms of tools and tactics")
    start = time.time()
    result = process_query(
        "Compare APT28 and TA558 in terms of tools and tactics",
        conversation_id=conversation_id
    )
    elapsed = time.time() - start
    
    print(f"✓ Completed in {elapsed:.2f}s")
    print(f"  Query type: {result.get('query_type', 'unknown')}")
    print(f"  Response mode: {result.get('response_mode', 'unknown')}")
    print(f"  Comparison actors: {result.get('comparison_actors', [])}")
    print(f"  Confidence: {result.get('confidence', 0):.2%}")
    print(f"\n📋 Answer:\n{result['answer']}")
    
    # Verify caching
    conversation_manager = ConversationManager()
    conversation = conversation_manager.load_or_create_conversation(conversation_id)
    print(f"\n📊 Conversation State After Comparison:")
    print(f"  Actors mentioned: {conversation.actors_mentioned}")
    print(f"  Cached actors: {list(conversation.actor_chunks_cache.keys())}")
    for actor, chunks in conversation.actor_chunks_cache.items():
        print(f"    - {actor}: {len(chunks)} chunks cached")


def test_latency_comparison():
    """Compare latency for cold vs cached queries."""
    print("\n" + "=" * 80)
    print("TEST 3: Latency Comparison (Cold vs Cached)")
    print("=" * 80)
    
    # Initialize components
    if not initialize_components():
        logger.error("Failed to initialize components")
        return
    
    conversation_id = f"test_latency_{int(time.time())}"
    
    # Cold query - first time querying APT28
    print("\n📝 COLD QUERY: APT28 attack methods")
    start = time.time()
    result1 = process_query(
        "What attack methods does APT28 use?",
        conversation_id=conversation_id,
        use_cache=False
    )
    cold_time = time.time() - start
    
    print(f"✓ Cold query completed in {cold_time:.2f}s")
    if 'timings' in result1:
        print(f"  Retrieval time: {result1['timings'].get('retrieval', 0):.2f}s")
        print(f"  Generation time: {result1['timings'].get('generation', 0):.2f}s")
    
    # Warm query - follow-up on same actor (uses cache)
    print("\n📝 WARM QUERY: APT28 infrastructure (follow-up)")
    start = time.time()
    result2 = process_query(
        "What infrastructure does APT28 use?",
        conversation_id=conversation_id,
        use_cache=False
    )
    warm_time = time.time() - start
    
    print(f"✓ Warm query completed in {warm_time:.2f}s")
    if 'timings' in result2:
        print(f"  Retrieval time: {result2['timings'].get('retrieval', 0):.2f}s")
        print(f"  Generation time: {result2['timings'].get('generation', 0):.2f}s")
    
    print(f"\n⏱️  Performance:")
    print(f"  Cold query (first mention): {cold_time:.2f}s")
    print(f"  Warm query (follow-up): {warm_time:.2f}s")
    if cold_time > 0:
        improvement = ((cold_time - warm_time) / cold_time) * 100
        print(f"  Improvement: {improvement:.1f}% faster")


def main():
    """Run all tests."""
    print("\n" + "🧪 THREAT-AI MULTI-ACTOR CONVERSATION TESTS".center(80, "="))
    print("Testing actor caching, comparison detection, and multi-turn conversations\n")
    
    try:
        test_multi_turn_conversation()
        test_comparison_queries()
        test_latency_comparison()
        
        print("\n" + "✓ ALL TESTS COMPLETED".center(80, "="))
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()
