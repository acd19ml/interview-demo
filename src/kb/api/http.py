from __future__ import annotations

import asyncio
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from kb.core.service import build_service, load_corpus

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "experiments" / "configs" / "exp-003-rerank.yaml"
CORPUS = ROOT / "experiments" / "golden" / "corpus"
DB = ROOT / ".data" / "http_kb.sqlite"
FRONTEND = Path(__file__).resolve().parent / "static" / "index.html"
# 相关性下限（reranker sigmoid 概率量纲；0.2 校准：合法 query 最低≈0.43，乱码≈0.0）
MIN_RELEVANCE = 0.2

app = FastAPI(title="interview-demo knowledge base")
_service = None


class DocumentIn(BaseModel):
    title: str
    content: str


class SearchIn(BaseModel):
    query: str
    top_k: int = 5


def get_service():
    global _service
    if _service is None:
        DB.parent.mkdir(exist_ok=True)
        config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        _service = build_service(config, DB)
        if _service.store.is_empty():
            _service.rebuild(load_corpus(CORPUS))
        else:
            _service.load_index()
    return _service


def doc_json(doc):
    return {"id": doc.id, "title": doc.title, "content": doc.content}


def hit_json(hit, title):
    return {
        "doc_id": hit.chunk.doc_id,
        "title": title,
        "chunk_id": hit.chunk.id,
        "snippet": hit.chunk.text[:240],
        "score": hit.score,
    }


_ERROR_STATUS = {
    "DOCUMENT_NOT_FOUND": 404,
    "KB_NOT_FOUND": 404,
    "EMBEDDING_FAILED": 503,
    "VECTOR_SEARCH_FAILED": 503,
}


def value_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    return HTTPException(status_code=_ERROR_STATUS.get(code, 400), detail={"code": code, "message": code})


@app.get("/")
def index():
    return FileResponse(FRONTEND)


@app.post("/documents")
def create_document(doc: DocumentIn):
    try:
        saved = get_service().ingest_document(doc.title, doc.content)
        return doc_json(saved)
    except ValueError as exc:
        raise value_error(exc) from exc


@app.get("/documents")
def list_documents(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)):
    try:
        docs, total = get_service().list_documents(page, size)
        return {"items": [doc_json(doc) for doc in docs], "page": page, "size": size, "total": total}
    except ValueError as exc:
        raise value_error(exc) from exc


@app.get("/documents/{doc_id}")
def get_document(doc_id: str):
    try:
        return doc_json(get_service().get_document(doc_id))
    except ValueError as exc:
        raise value_error(exc) from exc


@app.put("/documents/{doc_id}")
def update_document(doc_id: str, doc: DocumentIn):
    try:
        return doc_json(get_service().update_document(doc_id, doc.title, doc.content))
    except ValueError as exc:
        raise value_error(exc) from exc


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    try:
        get_service().delete_document(doc_id)
        return {"ok": True}
    except ValueError as exc:
        raise value_error(exc) from exc


@app.post("/search")
def search(body: SearchIn):
    try:
        service = get_service()
        hits = service.search(body.query, body.top_k)
        if not hits or max(hit.score for hit in hits) < MIN_RELEVANCE:
            return {"query": body.query, "results": [], "reason": "NO_RELEVANT_RESULT"}
        title_by_doc = {doc_id: service.get_document(doc_id).title for doc_id in {h.chunk.doc_id for h in hits}}
        return {
            "query": body.query,
            "results": [hit_json(hit, title_by_doc[hit.chunk.doc_id]) for hit in hits],
        }
    except ValueError as exc:
        raise value_error(exc) from exc


@app.get("/search/stream")
async def search_stream(q: str = Query(..., min_length=1), top_k: int = Query(3, ge=1, le=20)):
    try:
        hits = get_service().search(q, top_k)
    except ValueError as exc:
        raise value_error(exc) from exc
    text = "\n".join(hit.chunk.text[:240] for hit in hits) or "未找到相关内容"

    async def events():
        for ch in text:
            yield f"data: {ch}\n\n"
            await asyncio.sleep(0.005)
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
