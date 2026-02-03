"""Rebuild vector store with new entity-level chunking strategy."""

import sys
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from ingestion.load_raw import load_raw_actors
from ingestion.normalize import normalize_actors
from chunking.chunker import SemanticChunker
from embeddings.embedder import LocalEmbedder
from embeddings.vector_store import VectorStore
import yaml

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config():
    """Load configuration."""
    with open('config/settings.yaml', 'r') as f:
        return yaml.safe_load(f)


def rebuild_vector_store():
    """Rebuild vector store with new chunking strategy."""
    logger.info("=" * 60)
    logger.info("REBUILDING VECTOR STORE WITH ENTITY-LEVEL CHUNKING")
    logger.info("=" * 60)
    
    # Load config
    config = load_config()
    
    # Step 1: Load and normalize actors
    logger.info("\n[1/5] Loading raw actor data...")
    actors = load_raw_actors(config['data']['canonical_path'])
    logger.info(f"Loaded {len(actors)} actors")
    
    logger.info("\n[2/5] Normalizing actor data...")
    actors = normalize_actors(actors)
    logger.info(f"Normalized {len(actors)} actors")
    
    # Step 2: Create new chunker with entity-level strategy
    logger.info("\n[3/5] Chunking actors (entity-level strategy)...")
    chunking_config = config['chunking']
    chunker = SemanticChunker(
        chunk_size=chunking_config.get('chunk_size', 800),
        chunk_overlap=chunking_config.get('chunk_overlap', 128),
        min_length=chunking_config.get('min_chunk_length', 50),
        entity_level=chunking_config.get('entity_level', True)
    )
    
    all_chunks = []
    for actor in actors:
        chunks = chunker.chunk_actor(actor)
        all_chunks.extend(chunks)
    
    logger.info(f"Created {len(all_chunks)} chunks from {len(actors)} actors")
    logger.info(f"Average chunks per actor: {len(all_chunks) / len(actors):.2f}")
    
    # Step 3: Generate embeddings
    logger.info("\n[4/5] Generating embeddings...")
    emb_config = config['embeddings']
    embedder = LocalEmbedder(
        model_name=emb_config.get('model', 'sentence-transformers/all-MiniLM-L6-v2'),
        batch_size=emb_config.get('batch_size', 32)
    )
    
    chunks_with_embeddings = embedder.embed_chunks(all_chunks)
    logger.info(f"Generated embeddings for {len(chunks_with_embeddings)} chunks")
    
    # Step 4: Rebuild vector store
    logger.info("\n[5/5] Rebuilding vector store...")
    vs_config = config['vector_store']
    
    # Delete old collection
    logger.info("Deleting old collection...")
    try:
        old_store = VectorStore(
            dimension=emb_config.get('embedding_dim', 384),
            persist_directory=vs_config.get('persist_directory', 'data/chroma_db')
        )
        old_store.delete_collection()
    except Exception as e:
        logger.warning(f"Could not delete old collection: {e}")
    
    # Create new vector store
    logger.info("Creating new vector store...")
    vector_store = VectorStore(
        dimension=emb_config.get('embedding_dim', 384),
        persist_directory=vs_config.get('persist_directory', 'data/chroma_db')
    )
    
    # Add chunks
    added_count = vector_store.add_chunks(chunks_with_embeddings)
    logger.info(f"Added {added_count} chunks to new vector store")
    
    # Verify
    final_count = vector_store.get_size()
    logger.info(f"Final vector store size: {final_count} chunks")
    
    logger.info("\n" + "=" * 60)
    logger.info("✓ VECTOR STORE REBUILD COMPLETE")
    logger.info("=" * 60)
    logger.info("\nSummary:")
    logger.info(f"  • Actors processed: {len(actors)}")
    logger.info(f"  • Total chunks: {len(all_chunks)}")
    logger.info(f"  • Chunks in vector store: {final_count}")
    logger.info(f"  • Chunking mode: Entity-level (one chunk per actor)")
    logger.info(f"  • Features enabled: Alias normalization, Metadata filtering, Hybrid search")
    logger.info("\nYou can now restart the application to use the new system!")


if __name__ == "__main__":
    try:
        rebuild_vector_store()
    except Exception as e:
        logger.error(f"Error rebuilding vector store: {e}", exc_info=True)
        sys.exit(1)
