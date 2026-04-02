"""Generate embeddings using sentence transformers."""

import logging
import os
import numpy as np
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class LocalEmbedder:
    """Generate vector embeddings using local transformer models."""
    
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2", batch_size: int = 32):
        """
        Initialize embedder.
        
        Args:
            model_name: HuggingFace model identifier
            batch_size: Batch size for embedding generation
        """
        self.model_name = model_name
        self.batch_size = batch_size
        self.model = None
        self.device = os.getenv("THREATAI_EMBED_DEVICE", "auto")
        self._cpu_fallback_attempted = False
        self._load_model()

    def _is_cuda_compatible(self) -> bool:
        """Best-effort CUDA compatibility check for current torch build and GPU."""
        try:
            import torch

            if not torch.cuda.is_available():
                return False

            arch_list = torch.cuda.get_arch_list() or []
            major, minor = torch.cuda.get_device_capability(0)
            device_arch = f"sm_{major}{minor}"

            # If arch list is available and device arch is missing, CUDA kernels will fail.
            if arch_list and device_arch not in arch_list:
                logger.warning(
                    "CUDA device %s is not supported by this PyTorch build (%s). Falling back to CPU.",
                    device_arch,
                    ", ".join(arch_list),
                )
                return False

            return True
        except Exception as e:
            logger.warning("Could not validate CUDA compatibility (%s). Falling back to CPU.", e)
            return False

    @staticmethod
    def _is_cuda_runtime_error(error: Exception) -> bool:
        """Detect known CUDA runtime failures that should trigger CPU retry."""
        msg = str(error).lower()
        return (
            "cuda" in msg
            and (
                "no kernel image is available" in msg
                or "acceleratorerror" in msg
                or "device-side assert" in msg
                or "cudaerror" in msg
            )
        )

    def _reload_model_on_cpu(self):
        """Reload embedding model on CPU after CUDA runtime failure."""
        if self._cpu_fallback_attempted:
            raise RuntimeError("CPU fallback already attempted")

        self._cpu_fallback_attempted = True
        self.device = "cpu"
        logger.warning("Reloading embedding model on CPU after CUDA runtime error")
        self.model = SentenceTransformer(self.model_name, device="cpu")
    
    def _load_model(self):
        """Load the embedding model."""
        try:
            logger.info(f"Loading embedding model: {self.model_name}")
            model_device = None

            if self.device in {"cpu", "cuda"}:
                model_device = self.device
            elif self.device == "auto":
                model_device = None if self._is_cuda_compatible() else "cpu"

            if model_device:
                logger.info("Embedding model device: %s", model_device)
                self.model = SentenceTransformer(self.model_name, device=model_device)
            else:
                self.model = SentenceTransformer(self.model_name)

            logger.info(f"Model loaded successfully. Embedding dimension: {self.model.get_sentence_embedding_dimension()}")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    def _encode_with_fallback(self, payload, **kwargs):
        """Encode text payload and retry once on CPU when CUDA runtime fails."""
        if not self.model:
            raise RuntimeError("Model not loaded")

        try:
            return self.model.encode(payload, **kwargs)
        except Exception as e:
            if self._is_cuda_runtime_error(e):
                self._reload_model_on_cpu()
                return self.model.encode(payload, **kwargs)
            raise
    
    def embed_text(self, text: str) -> np.ndarray:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector
        """
        embedding = self._encode_with_fallback(text, convert_to_numpy=True)
        return embedding
    
    def embed_texts(self, texts: List[str]) -> List[np.ndarray]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        embeddings = self._encode_with_fallback(texts, batch_size=self.batch_size, convert_to_numpy=True)
        return [emb for emb in embeddings]
    
    def embed_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Embed a list of chunks.
        
        Args:
            chunks: List of chunk dictionaries with 'text' field
            
        Returns:
            Chunks with added 'embedding' field
        """
        texts = [chunk['text'] for chunk in chunks]
        embeddings = self.embed_texts(texts)
        
        embedded_chunks = []
        for chunk, embedding in zip(chunks, embeddings):
            chunk_copy = chunk.copy()
            chunk_copy['embedding'] = embedding.tolist()
            embedded_chunks.append(chunk_copy)
        
        return embedded_chunks
