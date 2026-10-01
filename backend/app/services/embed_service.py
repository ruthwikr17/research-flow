from __future__ import annotations

import numpy as np
from fastembed import TextEmbedding


class EmbedService:
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self.model_name = model_name
        self.model = TextEmbedding(model_name=model_name)

    @property
    def is_ready(self) -> bool:
        return self.model is not None

    def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = list(self.model.embed(texts))
        return [vec.tolist() for vec in embeddings]

    def most_similar_chunk(self, claim: str, chunks: list[str]) -> tuple[int, float]:
        if not chunks:
            raise ValueError("chunks must not be empty")
        vectors = np.array(self.embed([claim, *chunks]))
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1e-9, norms)
        vectors = vectors / norms
        scores = vectors[1:] @ vectors[0]
        index = int(np.argmax(scores))
        return index, float(scores[index])

