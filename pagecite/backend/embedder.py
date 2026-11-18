"""Step 3 of the upload pipeline (and query side): text -> vectors."""
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from backend.config import EMBED_MODEL


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    return SentenceTransformer(EMBED_MODEL)


def embed(texts: list[str]) -> np.ndarray:
    vecs = get_model().encode(
        texts, normalize_embeddings=True, show_progress_bar=False, batch_size=64
    )
    return np.asarray(vecs, dtype="float32")


def dimension() -> int:
    return get_model().get_embedding_dimension()
