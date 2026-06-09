"""评测 harness —— 签名骨架（v0.1 填实现）。

设计意图（这是项目的"真相源"，先于功能存在）：
  - 它直接打 core RAG 库，不经过 HTTP / MCP（Ports & Adapters：核心是纯库）。
  - 每个组件是一个 Strategy（Protocol）；实验配置 = 用哪些 Strategy 组装一条 pipeline。
    => 这就是"消融在物理上可行"的前提：换组件 = 改配置，不改代码。
  - 指标在 golden set 上算 Recall@k / MRR；full-context 走 oracle 上界分支。

关联：docs/design.md（问题→动机→设计→选择→演进→开放）、
     experiments/README.md（诊断链 / 消融矩阵）

骨架仅依赖标准库，保证设计阶段零依赖可读。v0.1 引入 bge / 向量库后再补实现。
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

# --------------------------------------------------------------------------- #
# 数据模型
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class GoldenQuery:
    """golden/queries.jsonl 的一行。"""

    id: str
    query: str
    gold_doc: str
    gold_chunk_ids: list[str] = field(default_factory=list)  # 空 => 回填前用文档级兜底
    axis: str = ""   # keyword | entity | semantic —— 解释这条考察哪根轴
    note: str = ""


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_id: str
    text: str


@dataclass(frozen=True)
class Retrieved:
    chunk: Chunk
    score: float


@dataclass
class QueryReport:
    query: GoldenQuery
    hits: list[Retrieved]
    hit_at_1: bool
    hit_at_3: bool
    reciprocal_rank: float


@dataclass
class EvalReport:
    exp_id: str
    recall_at_1: float
    recall_at_3: float
    mrr: float
    per_query: list[QueryReport]

    def leaderboard_row(self, change: str = "", note: str = "") -> str:
        """渲染成 results/leaderboard.md 的一行。"""
        raise NotImplementedError("TODO(v0.1)")


# --------------------------------------------------------------------------- #
# Strategy 接口（消融轴）—— 每个轴一个 Protocol
# --------------------------------------------------------------------------- #


@runtime_checkable
class Chunker(Protocol):
    """消融轴②：fixed / paragraph / heading，size、overlap。"""

    def split(self, doc_id: str, text: str) -> list[Chunk]: ...


@runtime_checkable
class Embedder(Protocol):
    """消融轴④：bge-small / base / large-zh / m3e。"""

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@runtime_checkable
class Retriever(Protocol):
    """消融轴③：dense / bm25 / hybrid(RRF)。"""

    def index(self, chunks: Sequence[Chunk]) -> None: ...
    def search(self, query: str, top_k: int) -> list[Retrieved]: ...


@runtime_checkable
class Reranker(Protocol):
    """消融轴⑤：cross-encoder，对 candidate 精排后截断。"""

    def rerank(self, query: str, hits: Sequence[Retrieved], top_k: int) -> list[Retrieved]: ...


@runtime_checkable
class QueryTransform(Protocol):
    """消融轴③：query rewrite / expansion。默认恒等。"""

    def transform(self, query: str) -> str: ...


@dataclass
class Pipeline:
    """一条被评测的检索管线 = 一组 Strategy 的组装。

    long_context oracle 模式不走这里，见 run_long_context_baseline。
    """

    chunker: Chunker
    embedder: Embedder
    retriever: Retriever
    top_k: int
    reranker: Reranker | None = None
    query_transform: QueryTransform | None = None

    def build_index(self, corpus: dict[str, str]) -> None:
        """corpus: {doc_id: full_text} -> chunk -> embed -> index。"""
        raise NotImplementedError("TODO(v0.1)")

    def retrieve(self, query: str) -> list[Retrieved]:
        """query_transform -> retriever.search(top_k 放宽) -> reranker -> 截断。"""
        raise NotImplementedError("TODO(v0.1)")


# --------------------------------------------------------------------------- #
# Factory：配置 -> pipeline（配置即组装 / DI）
# --------------------------------------------------------------------------- #


def build_pipeline(config: dict) -> Pipeline:
    """按 configs/*.yaml 的 block 选择各 Strategy 实现并组装。

    每个 type 字段映射到一个具体类；这是"换组件=改配置"得以成立的唯一入口。
    """
    raise NotImplementedError("TODO(v0.1): 按 type 分发到具体 Strategy 实现")


# --------------------------------------------------------------------------- #
# 加载
# --------------------------------------------------------------------------- #


def load_golden(path: Path) -> list[GoldenQuery]:
    """读 golden/queries.jsonl。"""
    queries: list[GoldenQuery] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            queries.append(GoldenQuery(**json.loads(line)))
    return queries


def load_corpus(corpus_dir: Path) -> dict[str, str]:
    """读 corpus/（含 distractors/），返回 {doc_id: full_text}。doc_id = 文件名去扩展名。"""
    raise NotImplementedError("TODO(v0.1): 递归读 *.txt，含 distractors/")


# --------------------------------------------------------------------------- #
# 指标
# --------------------------------------------------------------------------- #


def _is_hit(query: GoldenQuery, hit: Retrieved) -> bool:
    """命中判定：有 gold_chunk_ids 用 chunk 级，否则回退到文档级（gold_doc）。"""
    if query.gold_chunk_ids:
        return hit.chunk.id in query.gold_chunk_ids
    return hit.chunk.doc_id == query.gold_doc


def score_query(query: GoldenQuery, hits: list[Retrieved]) -> QueryReport:
    raise NotImplementedError("TODO(v0.1): 基于 _is_hit 计算 @1/@3/RR")


def run_eval(exp_id: str, pipeline: Pipeline, corpus: dict[str, str],
             golden: list[GoldenQuery]) -> EvalReport:
    """主评测：建索引 -> 逐 query 检索打分 -> 聚合 Recall@k / MRR。"""
    raise NotImplementedError("TODO(v0.1)")


def run_long_context_baseline(corpus: dict[str, str],
                              golden: list[GoldenQuery]) -> EvalReport:
    """oracle 上界：整库塞入，让模型直接指认 gold_doc。

    见 design.md 选择一——这是检索质量的天花板参照，不是主路径。
    """
    raise NotImplementedError("TODO(v0.1)")


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #


def load_config(path: Path) -> dict:
    raise NotImplementedError("TODO(v0.1): 读 yaml")


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 评测 harness（golden set 上算 Recall@k / MRR）")
    parser.add_argument("--config", type=Path, required=True, help="experiments/configs/*.yaml")
    parser.add_argument("--golden", type=Path,
                        default=Path(__file__).parent / "golden" / "queries.jsonl")
    parser.add_argument("--corpus", type=Path,
                        default=Path(__file__).parent / "golden" / "corpus")
    args = parser.parse_args()

    config = load_config(args.config)
    golden = load_golden(args.golden)
    corpus = load_corpus(args.corpus)

    if config.get("mode") == "long_context":
        report = run_long_context_baseline(corpus, golden)
    else:
        report = run_eval(config["id"], build_pipeline(config), corpus, golden)

    # TODO(v0.1): 打印汇总 + 追加一行到 results/leaderboard.md
    print(report)


if __name__ == "__main__":
    main()
