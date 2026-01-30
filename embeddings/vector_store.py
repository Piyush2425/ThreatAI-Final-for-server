"""Vector store using Chroma DB for semantic search."""

import logging
from typing import List, Dict, Any, Tuple
import chromadb
import uuid
import os

logger = logging.getLogger(__name__)


class VectorStore:
    """Vector store using Chroma DB for persistent vector storage."""
    
    def __init__(self, dimension: int = 384, persist_directory: str = "data/chroma_db"):
        """
        Initialize vector store with Chroma DB.
        
        Args:
            dimension: Embedding dimension (384 for MiniLM)
            persist_directory: Path to persistent storage
        """
        self.dimension = dimension
        self.persist_directory = persist_directory
        self.collection = None
        self._initialize_chroma()
    
    def _initialize_chroma(self):
        """Initialize Chroma DB client and collection."""
        try:
            # Create persist directory if it doesn't exist
            os.makedirs(self.persist_directory, exist_ok=True)
            
            # Create persistent Chroma client using new API
            client = chromadb.PersistentClient(path=self.persist_directory)
            
            # Create or get collection
            self.collection = client.get_or_create_collection(
                name="threat_actors",
                metadata={"hnsw:space": "cosine"}
            )
            
            logger.info(f"Initialized Chroma DB collection with persist directory: {self.persist_directory}")
        except Exception as e:
            logger.error(f"Failed to initialize Chroma DB: {e}")
            raise
    
    def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """
        Add chunks with embeddings to store.
        
        Args:
            chunks: List of chunks with 'embedding' field
            
        Returns:
            Number of chunks added
        """
        if not chunks:
            return 0
        
        try:
            # Prepare data for Chroma
            ids = []
            embeddings = []
            metadatas = []
            documents = []
            
            for chunk in chunks:
                if 'embedding' not in chunk:
                    logger.warning(f"Chunk {chunk.get('chunk_id')} missing embedding")
                    continue
                
                chunk_id = chunk.get('chunk_id', str(uuid.uuid4()))
                ids.append(chunk_id)
                embeddings.append(chunk['embedding'])
                documents.append(chunk['text'])
                
                # Store metadata
                metadata = {
                    'actor_id': chunk.get('actor_id', ''),
                    'source_field': chunk['metadata'].get('source_field', ''),
                    'chunk_type': chunk['metadata'].get('chunk_type', ''),
                    'chunk_index': str(chunk['metadata'].get('chunk_index', 0)),
                }
                metadatas.append(metadata)
            
            # Add to collection
            if ids:
                self.collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas
                )
                logger.info(f"Added {len(ids)} chunks to Chroma DB vector store")
                return len(ids)
            
            return 0
        except Exception as e:
            logger.error(f"Error adding chunks to vector store: {e}")
            raise
    
    def search(self, query_embedding: List[float], k: int = 5) -> List[Tuple[Dict[str, Any], float]]:
        """
        Search for similar chunks.
        
        Args:
            query_embedding: Query embedding vector
            k: Number of results to return
            
        Returns:
            List of (chunk, similarity) tuples
        """
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                include=["embeddings", "documents", "metadatas", "distances"]
            )
            
            if not results or not results['ids'] or len(results['ids']) == 0:
                return []
            
            # Convert Chroma results to our format
            matches = []
            for idx, (chunk_id, document, metadata, distance) in enumerate(
                zip(
                    results['ids'][0],
                    results['documents'][0],
                    results['metadatas'][0],
                    results['distances'][0]
                )
            ):
                # Chroma returns cosine distance (0-2), convert to similarity (0-1)
                similarity = 1 - (distance / 2)
                
                chunk = {
                    'chunk_id': chunk_id,
                    'actor_id': metadata.get('actor_id', ''),
                    'text': document,
                    'metadata': {
                        'source_field': metadata.get('source_field', ''),
                        'chunk_type': metadata.get('chunk_type', ''),
                        'chunk_index': int(metadata.get('chunk_index', 0)),
                    }
                }
                
                matches.append((chunk, similarity))
            
            return matches
        except Exception as e:
            logger.error(f"Error searching vector store: {e}")
            return []
    
    def get_size(self) -> int:
        """Get number of chunks in store."""
        try:
            count = self.collection.count()
            return count
        except Exception as e:
            logger.error(f"Error getting collection size: {e}")
            return 0
    
    def delete_collection(self):
        """Delete the collection (useful for resets)."""
        try:
            client = chromadb.PersistentClient(path=self.persist_directory)
            client.delete_collection("threat_actors")
            logger.info("Deleted Chroma DB collection")
        except Exception as e:
            logger.warning(f"Could not delete collection: {e}")
