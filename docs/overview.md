# 概要设计文档

> 本文回答 **是什么 / 用什么栈 / 分几期 / 每期做什么·不做什么**。
> "为什么这么选"见 [design.md](design.md)（问题→动机→设计→选择→演进→开放），此处不重复论证，只给结论与边界。

## 1. 系统概览

一句话：一个**评测驱动的 RAG 知识库**，核心是纯库，对外两个入口——给人的 HTTP（CRUD + 流式问答）和给 agent 的 MCP（单次检索原语）。

```
        Agent (Claude Code 等)          浏览器 / curl
              │ MCP                          │ HTTP
        ┌─────▼──────┐               ┌───────▼────────┐
        │ MCP Server │               │  FastAPI        │
        │ kb_search  │               │  CRUD+分页/上传 │
        └─────┬──────┘               │  /search · SSE  │
              └──────────┬───────────┴───────┬─────────┘
                  ┌──────▼────────────────────▼─────┐
                  │      Core RAG Library (纯库)      │
                  │  Service: ingest / crud / search  │
                  │  Pipeline = Strategy 组装         │
                  │  Chunker·Embedder·Retriever·      │
                  │  Reranker·QueryTransform          │
                  └──────┬─────────────────┬─────────┘
              ┌──────────▼──────┐   ┌───────▼─────────┐
              │ SQLite          │   │ VectorStore     │
              │ 文档/chunk/元数据 │   │ 暴力精确 cosine  │
              │ (CRUD+分页)      │   │ (接口后,可换)    │
              └─────────────────┘   └─────────────────┘
                                    ┌─────────────────┐
                                    │ Generator (LLM) │  ← SSE 答案合成
                                    └─────────────────┘
```

评测（`experiments/eval.py`）**直接打 Core Library**，不经过 HTTP/MCP——这是"先评测后功能"得以成立的关键（见 design.md §3.1）。

## 2. 技术栈与决策

| 层 | 选型 | 为什么 | 不选 / 替代 |
|---|---|---|---|
| 语言 | Python 3.11+ | RAG/ML 生态、官方 MCP SDK、async | — |
| API 框架 | FastAPI + uvicorn | 原生 SSE、pydantic、async、自动 OpenAPI | Flask（SSE/async 不够顺） |
| 文档/元数据存储 | SQLite | 单文件零运维，天然支持 CRUD + 分页(limit/offset) | Postgres（n 小，运维过重） |
| 向量检索 | numpy 暴力**精确** cosine（封装在 `VectorStore` 接口后）| n≈数百 chunk 时瞬时；精确检索**避免 ANN 近似误差污染消融信号** | FAISS/Chroma（额外依赖）；pgvector（规模化时的 swap-in） |
| Embedding | bge-small-zh-v1.5（本地）| 离线可复现、中文强、快；本身是消融轴④ | API embedding（key/成本，损可复现）；large 先不上，让评测决定 |
| 稀疏检索 | rank_bm25 | 纯 Python、简单；hybrid 用 | — |
| 重排 | bge-reranker-base | **仅当诊断指向⑤时引入** | — |
| 流式传输 | SSE（FastAPI StreamingResponse）| 满足 req4 的**传输层**，本身不依赖 LLM | — |
| 答案生成（可选）| OpenAI 兼容 API（你的中转 key），封装在 `Generator` 接口后 | 仅人侧 `/search/stream` 的**薄展示层**；core/MCP/eval 全 LLM-free；无 key 时降级为流式吐 snippet | 纯检索流式（不生成）|
| Agent 接口 | 官方 `mcp` SDK (FastMCP) | 题目要求、可被 Claude Code 等直接挂载 | 自写 skill（二选一，MCP 更通用可复用） |
| 依赖管理 | uv + pyproject.toml | 快、锁定可复现 | pip + requirements |
| 测试 | pytest + `experiments/eval.py` | 单测保正确性；eval 保检索质量 | — |

## 3. 模块划分

```
src/kb/
  core/
    models.py        # Document / Chunk / Retrieved
    interfaces.py    # Strategy Protocols（eval.py 现内联的接口 v0.1 搬到这，单一来源）
    pipeline.py      # Pipeline + build_pipeline(config) 工厂
    chunkers.py embedders.py retrievers.py rerankers.py
    service.py       # 纯库门面：ingest / crud / search
  store/
    sqlite_repo.py   # 文档/chunk 仓储（CRUD + 分页）
    vector_store.py  # 暴力精确 cosine；pgvector swap 路径
  generation/
    generator.py     # LLM Generator 接口 + provider
  api/
    http.py          # FastAPI：CRUD + 上传 + /search + SSE
    mcp_server.py    # MCP：kb_search + 错误契约
  config.py
experiments/         # 已建：golden / configs / eval.py / leaderboard
```

> 注：`eval.py` 现在内联了 Strategy 接口作为设计草图；v0.1 把它们搬进 `core/interfaces.py`，由 eval 反向 import，避免两处定义。

## 4. 对外接口概要

**MCP（给 agent）**
- `kb_search(query: str, top_k: int = 5)` → `{results: [{doc_id, title, snippet, score}], ...}`
- 错误契约（结构化返回，让 agent 能自我纠正——只取这条原则，不建 repair harness）：
  `EMPTY_QUERY` / `KB_EMPTY` / `RETRIEVAL_FAILED` / `TIMEOUT`。

**HTTP（给人）**
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/documents` | 上传 txt 或直接文本 → 入库(切分+嵌入) |
| GET | `/documents?page=&size=` | 列表，分页 |
| GET/PUT/DELETE | `/documents/{id}` | 读 / 改(重切重嵌) / 删(级联 chunk) |
| POST | `/search` | 相关性检索，返回排序 chunk（结构化，非流式）|
| GET | `/search/stream?q=` | SSE 流式（逐字）。有 key→LLM 生成式答案；无 key→流式吐 top snippet |

> 边界：生成只在 `/search/stream`；MCP `kb_search` 与 `/search` 只做检索、返回结构化结果——调用方 agent 自己生成，工具内不重复生成（design.md §3.3）。

**数据模型**
- `Document(id, title, source_type, content, created_at, updated_at)`
- `Chunk(id, doc_id, ord, text)` + 向量存 VectorStore

## 5. 项目排期（总 7h，设计 > 代码）

| 期 | 版本 | 时长 | 做什么 | **本期不做** | 完成定义（挂在评测/可验证点）|
|---|---|---|---|---|---|
| P0 设计+脚手架 | – | 1.5h | design.md、experiments 脚手架、本概要 | 任何功能代码 | ✅ 已基本完成 |
| P1 走骨架 | v0.1 | 1.0h | core 纯库(SQLite+dense 暴力+bge-small+fixed chunk)、入库真实《春》《故乡》+≥3 distractor、填 `eval.py`、MCP `kb_search` 可调用 | hybrid / rerank / rewrite / 流式 / HTTP CRUD / 错误打磨 | exp-001 与 exp-000(oracle) 跑出指标，leaderboard 第一行；kb_search 返回结构化结果 |
| P2 检索质量迭代 | v0.5 | 2.0h | 诊断驱动拉杆：chunk 策略 →（按需）hybrid →（按需）rerank，每条一行 leaderboard+一句决策 | 给没 fail 的 query 加组件；诊断没指向的杠杆 | golden 全绿（q1/q2/q3 命中，Recall@3=1.0）；≥2 行有信息量的消融对比 |
| P3 接口层 | v1.0-rc | 1.5h | HTTP CRUD+分页+上传、`/search`、SSE 流式(传输层)+可选 LLM 生成、MCP 错误契约(4 类) | auth/多用户、前端页面(→P5)、部署 | curl 走通 CRUD+分页+上传；SSE 逐字；(有 key)生成式答案；MCP 4 类错误结构化返回 |
| P4 收尾交付 | v1.0 | 1.0h | README(运行说明 + 实现思路链到 design.md)、打包(命名文件夹+简历)、tag | 新功能 | 按命名规范打包可提交；`git tag v1.0` |
| P5 前端(stretch) | – | 余量 | 最小 HTML 页演示流式（用你的前端 skill）| 核心功能 | 低优先级，有余量再做 |

## 6. 全局边界与待确认

**明确不做（YAGNI，整项目级）**
- 鉴权 / 多用户 / 权限；部署 / 容器编排。
- CI：7h 内不搭，手跑 `eval.py` 贴结果即可——把流程 right-size 到与时间盒匹配。
- agentic 多跳 / 查询路由 / memory（见 design.md §6 开放项）。
- ANN 索引：暴力精确足够且对 eval 更干净。
- query rewrite：除非 P2 诊断指向，否则不上。
- **LLM 不进 core / MCP / eval**：只在人侧 HTTP 流式端点，保护检索核心与评测的确定性可复现。

**已定（本轮）**
- SSE 是传输层、不等于 LLM。生成作为**可选薄层**：有 OpenAI 兼容 key 则开生成式答案，无 key 降级吐 snippet。
- 前端：先纯 curl/脚本；最小页挪到 P5 低优先级（用你的前端 skill）。

**待你确认**
1. **简历**：打包需要，你提供文件即可。
