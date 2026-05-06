"""Vector store using Chroma DB for semantic search."""

import logging
from typing import List, Dict, Any, Tuple, Optional
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
                
                # Store comprehensive metadata for filtering
                metadata = {
                    'actor_id': chunk.get('actor_id', ''),
                    'source_field': chunk['metadata'].get('source_field', ''),
                    'chunk_type': chunk['metadata'].get('chunk_type', ''),
                    'chunk_index': str(chunk['metadata'].get('chunk_index', 0)),
                    'actor_name': chunk['metadata'].get('actor_name', ''),
                    'primary_name': chunk['metadata'].get('primary_name', ''),
                    'source_system': chunk['metadata'].get('source_system', ''),
                    'last_activity': chunk['metadata'].get('last_activity', ''),
                    'country_primary': chunk['metadata'].get('country_primary', ''),
                }
                
                # Add name_giver if present
                if 'name_giver' in chunk['metadata']:
                    metadata['name_giver'] = chunk['metadata']['name_giver']
                
                # Store aliases as comma-separated string (Chroma doesn't support lists in metadata)
                aliases = chunk['metadata'].get('aliases', [])
                if aliases:
                    metadata['aliases'] = ','.join(str(a) for a in aliases if a)
                
                # Store countries
                countries = chunk['metadata'].get('countries', [])
                if countries:
                    metadata['countries'] = ','.join(str(c) for c in countries if c)

                attack_methods = chunk['metadata'].get('attack_methods', [])
                if attack_methods:
                    metadata['attack_methods'] = ','.join(str(m) for m in attack_methods if m)

                target_sectors = chunk['metadata'].get('target_sectors', [])
                if target_sectors:
                    metadata['target_sectors'] = ','.join(str(s) for s in target_sectors if s)

                tactics = chunk['metadata'].get('tactics', [])
                if tactics:
                    metadata['tactics'] = ','.join(str(t) for t in tactics if t)

                observed_sectors = chunk['metadata'].get('observed_sectors', [])
                if observed_sectors:
                    metadata['observed_sectors'] = ','.join(str(s) for s in observed_sectors if s)

                observed_countries = chunk['metadata'].get('observed_countries', [])
                if observed_countries:
                    metadata['observed_countries'] = ','.join(str(c) for c in observed_countries if c)
                
                # Store information_sources
                info_sources = chunk['metadata'].get('information_sources', [])
                if info_sources:
                    metadata['information_sources'] = ','.join(str(s) for s in info_sources if s)

                source_ids = chunk['metadata'].get('source_ids', [])
                if source_ids:
                    metadata['source_ids'] = ','.join(str(s) for s in source_ids if s)
                
                # Store related_actors
                related_actors = chunk['metadata'].get('related_actors', [])
                if related_actors:
                    metadata['related_actors'] = ','.join(str(r) for r in related_actors if r)
                
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
    
    def search(self, query_embedding: List[float], k: int = 5, where: Optional[Dict[str, Any]] = None) -> List[Tuple[Dict[str, Any], float]]:
        """
        Search for similar chunks with optional metadata filtering.
        
        Args:
            query_embedding: Query embedding vector
            k: Number of results to return
            where: Optional metadata filter (e.g., {"actor_name": "APT28"})
            
        Returns:
            List of (chunk, similarity) tuples
        """
        try:
            query_params = {
                'query_embeddings': [query_embedding],
                'n_results': k,
                'include': ["embeddings", "documents", "metadatas", "distances"]
            }
            
            # Add metadata filter if provided
            if where:
                query_params['where'] = where
            
            results = self.collection.query(**query_params)
            
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
                
                # Reconstruct aliases list from comma-separated string
                aliases = []
                if metadata.get('aliases'):
                    aliases = [a.strip() for a in metadata['aliases'].split(',') if a.strip()]
                
                # Reconstruct countries list
                countries = []
                if metadata.get('countries'):
                    countries = [c.strip() for c in metadata['countries'].split(',') if c.strip()]
                
                # Reconstruct information_sources list
                info_sources = []
                if metadata.get('information_sources'):
                    info_sources = [s.strip() for s in metadata['information_sources'].split(',') if s.strip()]
                
                # Reconstruct related_actors list
                related_actors = []
                if metadata.get('related_actors'):
                    related_actors = [r.strip() for r in metadata['related_actors'].split(',') if r.strip()]
                
                chunk = {
                    'chunk_id': chunk_id,
                    'actor_id': metadata.get('actor_id', ''),
                    'text': document,
                    'metadata': {
                        'source_field': metadata.get('source_field', ''),
                        'chunk_type': metadata.get('chunk_type', ''),
                        'chunk_index': int(metadata.get('chunk_index', 0)),
                        'actor_name': metadata.get('actor_name', ''),
                        'primary_name': metadata.get('primary_name', ''),
                        'aliases': aliases,
                        'countries': countries,
                        'information_sources': info_sources,
                        'source_ids': [s.strip() for s in metadata.get('source_ids', '').split(',') if s.strip()],
                        'related_actors': related_actors,
                        'source_system': metadata.get('source_system', ''),
                        'last_activity': metadata.get('last_activity', ''),
                        'country_primary': metadata.get('country_primary', '')
                    }
                }
                
                # Add name_giver if present
                if 'name_giver' in metadata:
                    chunk['metadata']['name_giver'] = metadata['name_giver']

                if metadata.get('attack_methods'):
                    chunk['metadata']['attack_methods'] = [
                        m.strip() for m in metadata['attack_methods'].split(',') if m.strip()
                    ]

                if metadata.get('target_sectors'):
                    chunk['metadata']['target_sectors'] = [
                        s.strip() for s in metadata['target_sectors'].split(',') if s.strip()
                    ]

                if metadata.get('tactics'):
                    chunk['metadata']['tactics'] = [
                        t.strip() for t in metadata['tactics'].split(',') if t.strip()
                    ]

                if metadata.get('observed_sectors'):
                    chunk['metadata']['observed_sectors'] = [
                        s.strip() for s in metadata['observed_sectors'].split(',') if s.strip()
                    ]

                if metadata.get('observed_countries'):
                    chunk['metadata']['observed_countries'] = [
                        c.strip() for c in metadata['observed_countries'].split(',') if c.strip()
                    ]
                
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
