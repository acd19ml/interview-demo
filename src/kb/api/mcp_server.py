from __future__ import annotations

from pathlib import Path
from concurrent.futures import TimeoutError as FutureTimeoutError, ThreadPoolExecutor

import yaml
from mcp.server.fastmcp import FastMCP

from kb.core.service import build_service, load_corpus

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "experiments" / "configs" / "exp-003-rerank.yaml"
CORPUS = ROOT / "experiments" / "golden" / "corpus"
DB = ROOT / ".data" / "kb.sqlite"
TIMEOUT_SECONDS = 20
# 相关性下限（reranker sigmoid 概率量纲；0.2 校准：合法 query 最低≈0.43，乱码≈0.0）
MIN_RELEVANCE = 0.2

mcp = FastMCP("interview-demo-kb")
_service = None


def get_service():
    global _service
    if _service is None:
        DB.parent.mkdir(exist_ok=True)
        config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        _service = build_service(config, DB)
        _service.rebuild(load_corpus(CORPUS))
    return _service


@mcp.tool()
def kb_search(query: str, top_k: int = 5) -> dict:
    """检索知识库，返回与 query 语义最相关的文档片段。

    当用户想从知识库/资料里查找某个主题、人物、作品或相关内容时，应直接调用本工具，
    不要去读取配置或源码文件。支持语义检索：query 不必与原文字面一致（如「小孩子」可命中《故乡》）。

    Args:
        query: 查询词或自然语言描述，例如「春天」「少年闰土」「小孩子」。
        top_k: 返回的最相关片段数量，默认 5。

    Returns:
        成功 {"ok": true, "results": [{"doc_id","title","snippet","score"}, ...]}；
        无相关命中 {"ok": true, "results": [], "reason": "NO_RELEVANT_RESULT"}；
        失败 {"ok": false, "error": {"code","message"}}（如 EMPTY_QUERY / TOOL_TIMEOUT）。
    """
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            hits = pool.submit(get_service().search, query, top_k).result(timeout=TIMEOUT_SECONDS)
    except ValueError as exc:
        return {"ok": False, "error": {"code": str(exc), "message": str(exc)}, "results": []}
    except FutureTimeoutError:
        return {"ok": False, "error": {"code": "TOOL_TIMEOUT", "message": "tool call timed out"}, "results": []}
    except Exception as exc:
        return {
            "ok": False,
            "error": {"code": "RETRIEVAL_FAILED", "message": str(exc)},
            "results": [],
        }
    if not hits or max(hit.score for hit in hits) < MIN_RELEVANCE:
        return {"ok": True, "results": [], "reason": "NO_RELEVANT_RESULT"}
    service = get_service()
    title_by_doc = {doc_id: service.get_document(doc_id).title for doc_id in {h.chunk.doc_id for h in hits}}
    return {
        "ok": True,
        "results": [
            {
                "doc_id": hit.chunk.doc_id,
                "title": title_by_doc[hit.chunk.doc_id],
                "chunk_id": hit.chunk.id,
                "snippet": hit.chunk.text[:160],
                "score": hit.score,
            }
            for hit in hits
        ],
    }


if __name__ == "__main__":
    mcp.run()
