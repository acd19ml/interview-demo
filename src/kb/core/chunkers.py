from __future__ import annotations

from .models import Chunk


class FixedChunker:
    def __init__(self, size: int = 512, overlap: int = 0) -> None:
        if size <= 0:
            raise ValueError("chunk size must be positive")
        if overlap < 0 or overlap >= size:
            raise ValueError("overlap must be >= 0 and smaller than size")
        self.size = size
        self.overlap = overlap

    def split(self, doc_id: str, text: str) -> list[Chunk]:
        clean = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        step = self.size - self.overlap
        chunks: list[Chunk] = []
        for start in range(0, len(clean), step):
            piece = clean[start:start + self.size]
            if piece:
                chunks.append(Chunk(id=f"{doc_id}:{len(chunks)}", doc_id=doc_id, text=piece))
        return chunks

