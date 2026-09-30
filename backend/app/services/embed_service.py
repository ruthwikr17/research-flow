from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer


class EmbedService:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    @property
    def is_ready(self) -> bool:
        return self.model is not None

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True).tolist()

    def most_similar_chunk(self, claim: str, chunks: list[str]) -> tuple[int, float]:
        if not chunks:
            raise ValueError("chunks must not be empty")
        vectors = np.array(self.embed([claim, *chunks]))
        scores = vectors[1:] @ vectors[0]
        index = int(np.argmax(scores))
        return index, float(scores[index])

