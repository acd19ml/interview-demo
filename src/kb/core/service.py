from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from uuid import uuid4

from kb.store.sqlite_repo import SQLiteStore

from .chunkers import FixedChunker
from .embedders import BgeEmbedder
from .models import Document, Retrieved
from .rerankers import CrossEncoderReranker
from .retrievers import DenseRetriever


class KnowledgeService:
    def __init__(
        self,
        store: SQLiteStore,
        chunker: FixedChunker,
        embedder: BgeEmbedder,
        reranker: CrossEncoderReranker | None = None,
    ) -> None:
        self.store = store
        self.chunker = chunker
        self.embedder = embedder
        self.reranker = reranker
        self.retriever = DenseRetriever()

    def rebuild(self, corpus: dict[str, str]) -> None:
        self.store.reset()
        self._save_documents(
            Document(id=doc_id, title=_doc_title(content), content=content)
            for doc_id, content in corpus.items()
        )

    def _save_documents(self, docs: Iterable[Document]) -> None:
        all_chunks = []
        for doc in docs:
            self.store.save_document(doc)
            all_chunks.extend(self.chunker.split(doc.id, doc.content))
        try:
            vectors = self.embedder.embed([chunk.text for chunk in all_chunks])
        except Exception as exc:
            raise ValueError("EMBEDDING_FAILED") from exc
        self.store.save_chunks(all_chunks, vectors)
        self.load_index()

    def ingest_document(self, title: str, content: str, doc_id: str | None = None) -> Document:
        title = title.strip()
        content = content.strip()
        if not title:
            raise ValueError("EMPTY_TITLE")
        if not content:
            raise ValueError("EMPTY_DOCUMENT")
        doc = Document(id=doc_id or uuid4().hex, title=title, content=content)
        self.store.delete_document_chunks(doc.id)
        self._save_documents([doc])
        return doc

    def list_documents(self, page: int = 1, size: int = 20) -> tuple[list[Document], int]:
        if page < 1 or size < 1:
            raise ValueError("BAD_PAGINATION")
        return self.store.list_documents(page, size)

    def get_document(self, doc_id: str) -> Document:
        doc = self.store.get_document(doc_id)
        if doc is None:
            raise ValueError("DOCUMENT_NOT_FOUND")
        return doc

    def update_document(self, doc_id: str, title: str, content: str) -> Document:
        self.get_document(doc_id)
        return self.ingest_document(title, content, doc_id=doc_id)

    def delete_document(self, doc_id: str) -> None:
        if not self.store.delete_document(doc_id):
            raise ValueError("DOCUMENT_NOT_FOUND")
        self.load_index()

    def load_index(self) -> None:
        chunks, vectors = self.store.load_chunks_and_vectors()
        self.retriever.index(chunks, vectors)

    def search(self, query: str, top_k: int = 5) -> list[Retrieved]:
        query = query.strip()
        if not query:
            raise ValueError("EMPTY_QUERY")
        if self.store.is_empty():
            raise ValueError("KB_NOT_FOUND")
        if not self.retriever.chunks:
            self.load_index()
        try:
            query_vector = self.embedder.embed_query(query)
        except Exception as exc:
            raise ValueError("EMBEDDING_FAILED") from exc
        try:
            if self.reranker is None:
                return self.retriever.search(query_vector, top_k)
            dense_hits = self.retriever.search(query_vector, self.reranker.candidate_k)
            return self.reranker.rerank(query, dense_hits, top_k)
        except Exception as exc:
            raise ValueError("VECTOR_SEARCH_FAILED") from exc


def _doc_title(content: str) -> str:
    """语料标题：取首个非空行，优先《》内文字，否则去掉残留书名号。"""
    line = next((ln.strip() for ln in content.splitlines() if ln.strip()), "")
    match = re.search(r"《([^》]+)》", line)
    if match:
        return match.group(1)
    return line.replace("《", "").replace("》", "").strip() or line


def load_corpus(corpus_dir: Path) -> dict[str, str]:
    corpus: dict[str, str] = {}
    for path in sorted(corpus_dir.rglob("*.txt")):
        if path.name.startswith("."):
            continue
        if path.stem in corpus:
            raise ValueError(f"DUPLICATE_DOC_ID: {path.stem}")
        corpus[path.stem] = path.read_text(encoding="utf-8").strip()
    return corpus


def build_service(config: dict, db_path: str | Path = ":memory:") -> KnowledgeService:
    chunker_config = config.get("chunker") or {}
    embedder_config = config.get("embedder") or {}
    reranker_config = config.get("reranker")
    reranker = None
    if reranker_config:
        reranker = CrossEncoderReranker(
            model=reranker_config["model"],
            candidate_k=int(reranker_config.get("candidate_k", 10)),
        )
    return KnowledgeService(
        SQLiteStore(db_path),
        FixedChunker(
            size=int(chunker_config.get("size", 512)),
            overlap=int(chunker_config.get("overlap", 0)),
        ),
        BgeEmbedder(
            model=embedder_config.get("model", "BAAI/bge-small-zh-v1.5"),
            query_instruction=embedder_config.get("query_instruction", ""),
        ),
        reranker,
    )
