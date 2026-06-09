"""评测 harness —— 在 golden set 上度量检索质量，产出可版本化的结果 artifact。

要点：
  - 直接打 core 库（kb.core.service），不经过 HTTP / MCP。
  - 判分到【文档级】：top 结果是否来自 gold_doc。不做 chunk 级 gold
    （哪段算对没有客观标准、且需大量人工，见 docs/design.md 选择四）。
  - margin = 最佳 gold-doc chunk 分 − 最佳非 gold-doc chunk 分，用于暴露排序脆弱性；
    只在同模型、同语料、同 chunker 的配置族内横向比较。
  - 每次跑落一份 results/<exp_id>.json，带指纹（code + corpus + golden + model + config），
    用于控制变量比较。指标是机器产的；leaderboard 的"决策"由人手写，eval 不代填。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kb.core.models import Chunk, Retrieved  # noqa: E402
from kb.core.service import build_service, load_corpus  # noqa: E402


# --------------------------------------------------------------------------- #
# 数据模型
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class GoldenQuery:
    """golden/queries.jsonl 的一行。判分到文档级，gold_chunk_ids 保留字段但不使用。"""

    id: str
    query: str
    gold_doc: str
    gold_chunk_ids: list[str] = field(default_factory=list)
    axis: str = ""   # keyword | entity | semantic —— 这条考察哪根轴
    note: str = ""


@dataclass
class QueryReport:
    query: GoldenQuery
    hits: list[Retrieved]   # 截断留证（前若干）
    rank: int               # 第一个 gold-doc chunk 的名次；0 = 未命中
    margin: float           # 最佳 gold 分 − 最佳非 gold 分；越大越稳，<0 = 排错；nan = 不适用

    @property
    def hit_at_1(self) -> bool:
        return self.rank == 1

    @property
    def hit_at_3(self) -> bool:
        return 0 < self.rank <= 3

    @property
    def reciprocal_rank(self) -> float:
        return 0.0 if self.rank == 0 else 1.0 / self.rank


@dataclass
class EvalReport:
    exp_id: str
    recall_at_1: float
    recall_at_3: float
    mrr: float
    min_margin: float | None    # 最弱一条 query 的 margin；oracle 行为 None
    per_query: list[QueryReport]


# --------------------------------------------------------------------------- #
# 加载 / 打分
# --------------------------------------------------------------------------- #


def load_golden(path: Path) -> list[GoldenQuery]:
    queries: list[GoldenQuery] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            queries.append(GoldenQuery(**json.loads(line)))
    return queries


def score_query(query: GoldenQuery, ranked: list[Retrieved]) -> QueryReport:
    """ranked: 按当前策略分数降序的候选列表。判分到文档级 + 计算 margin。"""
    rank = 0
    for idx, hit in enumerate(ranked, start=1):
        if hit.chunk.doc_id == query.gold_doc:
            rank = idx
            break
    gold = [h.score for h in ranked if h.chunk.doc_id == query.gold_doc]
    other = [h.score for h in ranked if h.chunk.doc_id != query.gold_doc]
    margin = (max(gold) if gold else 0.0) - (max(other) if other else 0.0)
    return QueryReport(query=query, hits=ranked[:5], rank=rank, margin=float(margin))


def run_service_eval(config: dict, corpus: dict[str, str], golden: list[GoldenQuery]) -> EvalReport:
    service = build_service(config)
    service.rebuild(corpus)
    full_k = max(len(service.retriever.chunks), 1)   # 全量排序，margin 才能取到全局最佳非 gold
    per_query = [score_query(q, service.search(q.query, full_k)) for q in golden]
    n = len(per_query)
    return EvalReport(
        exp_id=config["id"],
        recall_at_1=sum(r.hit_at_1 for r in per_query) / n,
        recall_at_3=sum(r.hit_at_3 for r in per_query) / n,
        mrr=sum(r.reciprocal_rank for r in per_query) / n,
        min_margin=min(r.margin for r in per_query),
        per_query=per_query,
    )


def run_long_context_baseline(corpus: dict[str, str], golden: list[GoldenQuery]) -> EvalReport:
    """oracle sanity 行：直接以 gold_doc 构造命中。

    注意：1.000 是构造出来的、不是真上界（真上界需 LLM，而 eval 保持 LLM-free）；
    margin 不适用。仅作"答案确实在库里"的兜底 sanity。见 docs/design.md 选择一。
    """
    per_query = []
    for q in golden:
        chunk = Chunk(id=f"{q.gold_doc}:oracle", doc_id=q.gold_doc, text=corpus.get(q.gold_doc, ""))
        per_query.append(QueryReport(query=q, hits=[Retrieved(chunk, 1.0)], rank=1, margin=math.nan))
    return EvalReport("exp-000-baseline-longcontext", 1.0, 1.0, 1.0, None, per_query)


# --------------------------------------------------------------------------- #
# 指纹（控制变量）—— 一个结果只有 pin 住 code+corpus+model+config 才叫"实验"
# --------------------------------------------------------------------------- #


def _git_sha() -> tuple[str, bool]:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                                    capture_output=True, text=True).stdout.strip())
        return sha or "unknown", dirty
    except Exception:
        return "unknown", False


def _corpus_hash(corpus: dict[str, str]) -> str:
    h = hashlib.sha256()
    for doc_id in sorted(corpus):
        h.update(doc_id.encode()); h.update(b"\x00")
        h.update(corpus[doc_id].encode()); h.update(b"\x00")
    return h.hexdigest()[:12]


def _golden_hash(golden: list[GoldenQuery]) -> str:
    h = hashlib.sha256()
    for q in golden:
        h.update(json.dumps(q.__dict__, ensure_ascii=False, sort_keys=True).encode())
        h.update(b"\x00")
    return h.hexdigest()[:12]


def make_provenance(config: dict, config_path: Path, corpus: dict[str, str],
                    golden: list[GoldenQuery]) -> dict:
    sha, dirty = _git_sha()
    reranker_config = config.get("reranker") or {}
    return {
        "code_sha": sha,
        "code_dirty": dirty,
        "corpus_hash": _corpus_hash(corpus),
        "golden_hash": _golden_hash(golden),
        "model": (config.get("embedder") or {}).get("model", "(n/a)"),
        "reranker_model": reranker_config.get("model"),
        "reranker_candidate_k": reranker_config.get("candidate_k"),
        "config_id": config.get("id", config_path.stem),
        "config_hash": hashlib.sha256(config_path.read_bytes()).hexdigest()[:12],
    }


# --------------------------------------------------------------------------- #
# 产物
# --------------------------------------------------------------------------- #


def to_artifact(report: EvalReport, provenance: dict) -> dict:
    def m(x: float) -> float | None:
        return None if isinstance(x, float) and math.isnan(x) else x
    return {
        "exp_id": report.exp_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "provenance": provenance,
        "metrics": {
            "recall@1": report.recall_at_1,
            "recall@3": report.recall_at_3,
            "mrr": report.mrr,
            "min_margin": report.min_margin,
        },
        "per_query": [
            {
                "id": r.query.id, "query": r.query.query, "gold_doc": r.query.gold_doc,
                "axis": r.query.axis, "rank": r.rank, "margin": m(r.margin),
                "topk": [
                    {"chunk_id": h.chunk.id, "doc_id": h.chunk.doc_id, "score": round(h.score, 4)}
                    for h in r.hits
                ],
            }
            for r in report.per_query
        ],
    }


def write_artifact(artifact: dict) -> Path:
    out = ROOT / "experiments" / "results" / f"{artifact['exp_id']}.json"
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def leaderboard_row(report: EvalReport, corpus_hash: str, golden_hash: str) -> str:
    """供人粘进 leaderboard。'改动'与'决策'两列留占位，由人填——eval 不代填决策。"""
    q = {r.query.id: ("✅" if r.hit_at_1 else "❌") for r in report.per_query}
    semantic = [r for r in report.per_query if r.query.axis.startswith("semantic")]
    semantic_ok = sum(r.hit_at_1 for r in semantic)
    semantic_cell = f"{semantic_ok}/{len(semantic)}" if semantic else "—"
    mm = "—" if report.min_margin is None else f"{report.min_margin:+.4f}"
    return (f"| {report.exp_id} | _改动?_ | {corpus_hash} | {golden_hash} | "
            f"{report.recall_at_1:.3f} | "
            f"{report.recall_at_3:.3f} | {report.mrr:.3f} | {mm} | "
            f"{q.get('q1', '')} | {q.get('q2', '')} | {q.get('q3', '')} | "
            f"{semantic_cell} | _决策?_ |")


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 评测：golden set 上算 Recall@k / MRR / margin")
    parser.add_argument("--config", type=Path, required=True, help="experiments/configs/*.yaml")
    parser.add_argument("--golden", type=Path, default=ROOT / "experiments" / "golden" / "queries.jsonl")
    parser.add_argument("--corpus", type=Path, default=ROOT / "experiments" / "golden" / "corpus")
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    golden = load_golden(args.golden)
    corpus = load_corpus(args.corpus)
    provenance = make_provenance(config, args.config, corpus, golden)

    if config.get("mode") == "long_context":
        report = run_long_context_baseline(corpus, golden)
    else:
        report = run_service_eval(config, corpus, golden)

    path = write_artifact(to_artifact(report, provenance))

    dirty = "+dirty" if provenance["code_dirty"] else ""
    mm = "—" if report.min_margin is None else f"{report.min_margin:+.4f}"
    print(f"\n{report.exp_id}  (corpus={provenance['corpus_hash']} "
          f"golden={provenance['golden_hash']} "
          f"code={provenance['code_sha']}{dirty} model={provenance['model']})")
    if provenance.get("reranker_model"):
        print(f"reranker={provenance['reranker_model']} "
              f"candidate_k={provenance['reranker_candidate_k']}")
    print(f"Recall@1={report.recall_at_1:.3f}  Recall@3={report.recall_at_3:.3f}  "
          f"MRR={report.mrr:.3f}  min_margin={mm}")
    for r in report.per_query:
        top3 = [f"{h.chunk.doc_id}:{h.score:.4f}" for h in r.hits[:3]]
        mg = "nan" if math.isnan(r.margin) else f"{r.margin:+.4f}"
        print(f"- {r.query.id} {r.query.query:<6} rank={r.rank} margin={mg}  top3={top3}")
    print(f"\n结果已存: {path.relative_to(ROOT)}")
    print("把下面这行粘进 experiments/results/leaderboard.md，补上'改动'与'决策'两列：")
    print(leaderboard_row(report, provenance["corpus_hash"], provenance["golden_hash"]))


if __name__ == "__main__":
    main()
