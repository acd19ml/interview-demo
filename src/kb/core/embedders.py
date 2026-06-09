from __future__ import annotations

from collections.abc import Sequence

import numpy as np


class BgeEmbedder:
    def __init__(self, model: str = "BAAI/bge-small-zh-v1.5", query_instruction: str = "") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "BgeEmbedder requires sentence-transformers. Install project deps first."
            ) from exc
        self.model_name = model
        self.query_instruction = query_instruction
        try:
            self._model = SentenceTransformer(model, local_files_only=True)
        except Exception:
            self._model = SentenceTransformer(model)

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        vectors = self._model.encode(
            list(texts),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        """query 侧嵌入：可选加指令前缀（bge 非对称检索）；passage 侧用 embed（不加）。"""
        return self.embed([self.query_instruction + text])[0]
