from __future__ import annotations

import pickle
import sqlite3
from pathlib import Path

import numpy as np

from kb.core.models import Chunk, Document


class SQLiteStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("pragma foreign_keys = on")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            create table if not exists documents (
              id text primary key,
              title text not null,
              content text not null
            );
            create table if not exists chunks (
              id text primary key,
              doc_id text not null references documents(id) on delete cascade,
              ord integer not null,
              text text not null
            );
            create table if not exists vectors (
              chunk_id text primary key references chunks(id) on delete cascade,
              vector blob not null
            );
            """
        )
        self.conn.commit()

    def reset(self) -> None:
        self.conn.executescript("delete from vectors; delete from chunks; delete from documents;")
        self.conn.commit()

    def save_document(self, doc: Document) -> None:
        self.conn.execute(
            "insert or replace into documents(id, title, content) values (?, ?, ?)",
            (doc.id, doc.title, doc.content),
        )

    def get_document(self, doc_id: str) -> Document | None:
        row = self.conn.execute(
            "select id, title, content from documents where id = ?",
            (doc_id,),
        ).fetchone()
        if row is None:
            return None
        return Document(id=row["id"], title=row["title"], content=row["content"])

    def list_documents(self, page: int, size: int) -> tuple[list[Document], int]:
        offset = (page - 1) * size
        total = int(self.conn.execute("select count(*) as n from documents").fetchone()["n"])
        rows = self.conn.execute(
            "select id, title, content from documents order by id limit ? offset ?",
            (size, offset),
        ).fetchall()
        docs = [Document(id=row["id"], title=row["title"], content=row["content"]) for row in rows]
        return docs, total

    def delete_document(self, doc_id: str) -> bool:
        self.conn.execute(
            "delete from vectors where chunk_id in (select id from chunks where doc_id = ?)",
            (doc_id,),
        )
        self.conn.execute("delete from chunks where doc_id = ?", (doc_id,))
        cur = self.conn.execute("delete from documents where id = ?", (doc_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def delete_document_chunks(self, doc_id: str) -> None:
        self.conn.execute(
            "delete from vectors where chunk_id in (select id from chunks where doc_id = ?)",
            (doc_id,),
        )
        self.conn.execute("delete from chunks where doc_id = ?", (doc_id,))

    def save_chunks(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        for ord_, chunk in enumerate(chunks):
            self.conn.execute(
                "insert or replace into chunks(id, doc_id, ord, text) values (?, ?, ?, ?)",
                (chunk.id, chunk.doc_id, ord_, chunk.text),
            )
            self.conn.execute(
                "insert or replace into vectors(chunk_id, vector) values (?, ?)",
                (chunk.id, pickle.dumps(vectors[ord_])),
            )
        self.conn.commit()

    def load_chunks_and_vectors(self) -> tuple[list[Chunk], np.ndarray]:
        rows = self.conn.execute(
            """
            select chunks.id, chunks.doc_id, chunks.text, vectors.vector
            from chunks join vectors on vectors.chunk_id = chunks.id
            order by chunks.doc_id, chunks.ord
            """
        ).fetchall()
        chunks = [Chunk(id=row["id"], doc_id=row["doc_id"], text=row["text"]) for row in rows]
        vectors = [pickle.loads(row["vector"]) for row in rows]
        if not vectors:
            return chunks, np.empty((0, 0), dtype=np.float32)
        return chunks, np.vstack(vectors).astype(np.float32)

    def is_empty(self) -> bool:
        row = self.conn.execute("select count(*) as n from chunks").fetchone()
        return int(row["n"]) == 0
