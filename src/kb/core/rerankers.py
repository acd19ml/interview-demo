from __future__ import annotations

from collections.abc import Sequence

from .models import Retrieved


class CrossEncoderReranker:
    def __init__(self, model: str, candidate_k: int = 10) -> None:
        if candidate_k <= 0:
            raise ValueError("candidate_k must be positive")
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError(
                "CrossEncoderReranker requires sentence-transformers. Install project deps first."
            ) from exc
        self.model_name = model
        self.candidate_k = candidate_k
        try:
            self._model = CrossEncoder(model, local_files_only=True)
        except Exception:
            self._model = CrossEncoder(model)

    def rerank(self, query: str, hits: Sequence[Retrieved], top_k: int) -> list[Retrieved]:
        candidates = list(hits)[:self.candidate_k]
        if not candidates:
            return []
        pairs = [(query, hit.chunk.text) for hit in candidates]
        scores = self._model.predict(pairs, show_progress_bar=False)
        reranked = [
            Retrieved(chunk=hit.chunk, score=float(score))
            for hit, score in zip(candidates, scores)
        ]
        reranked.sort(key=lambda hit: hit.score, reverse=True)
        return reranked[:top_k]

