from __future__ import annotations

import numpy as np

from .models import Chunk, Retrieved


class DenseRetriever:
    def __init__(self) -> None:
        self.chunks: list[Chunk] = []
        self.vectors: np.ndarray | None = None

    def index(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        self.chunks = chunks
        self.vectors = vectors

    def search(self, query_vector: np.ndarray, top_k: int) -> list[Retrieved]:
        if self.vectors is None or len(self.chunks) == 0:
            return []
        scores = self.vectors @ query_vector.reshape(-1)
        order = np.argsort(-scores)[:top_k]
        return [Retrieved(self.chunks[int(i)], float(scores[int(i)])) for i in order]

