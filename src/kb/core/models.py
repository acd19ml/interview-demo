from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    content: str


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_id: str
    text: str


@dataclass(frozen=True)
class Retrieved:
    chunk: Chunk
    score: float

