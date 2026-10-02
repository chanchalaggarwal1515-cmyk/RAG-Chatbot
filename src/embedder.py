"""Shared MiniLM encoder for chunks and queries.

Architecture: sentence-transformers/all-MiniLM-L6-v2, 384-d, local.
Use the same NORMALIZE_EMBEDDINGS flag at ingest and query time.
"""

from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM = 384
NORMALIZE_EMBEDDINGS = True


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    return SentenceTransformer(EMBED_MODEL_NAME, device="cpu")


def embed_texts(texts: list[str], batch_size: int = 8) -> list[list[float]]:
    model = get_model()
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=NORMALIZE_EMBEDDINGS,
        show_progress_bar=len(texts) > 32,
    )
    if vectors.shape[1] != EMBED_DIM:
        raise ValueError(f"Expected {EMBED_DIM}-d embeddings, got {vectors.shape[1]}")
    return vectors.tolist()
