# experiments —— 评测驱动的迭代

这里是整个项目的**真相源**。功能不靠"感觉对了"合并，靠 golden set 上的指标 delta。

## 为什么先有这个目录

题目把评测集白送了：`golden/queries.jsonl` 里的三条 query 就是 golden set。
一旦它可跑（Recall@k / MRR），消融 / A-B / PR 决策才有支点（见 [design.md §2 动机](../docs/design.md)）。

## 工作流（诊断在前、优化在后）

1. **v0.1 走骨架**：`exp-001-dense-only` —— 纯 dense + 固定 chunk，跑 golden set。
2. 看哪条 query fail，沿**诊断链**定位失败段（下表）。
3. 若 Recall 全绿但某类 query 很脆，先扩同类 golden query，确认问题不是单题偶然。
4. **只拉定位到那段的杠杆**，重跑，记一行 `results/leaderboard.md` + 一句决策。
5. 扩展后的 golden set 全绿即停（YAGNI 停止规则）。

```bash
python experiments/eval.py --config experiments/configs/exp-001-dense-only.yaml
python experiments/eval.py --config experiments/configs/exp-000-baseline-longcontext.yaml  # oracle 上界
```

## 消融矩阵（菜单，不是计划——诊断决定点哪几道）

| 诊断段 | 杠杆 | 触发条件 | 被哪条 golden query 驱动 |
|---|---|---|---|
| ① 数据完整性 | 校验，不消融 | 人工都找不到答案 | 全部（前置 sanity gate）|
| ② chunking | size{256/512/整段}、overlap{0/64}、按段落切 | 答案被切碎 / 稀释 | 影响全部，长答案尤甚 |
| ③ query↔doc 鸿沟 | hybrid(BM25+dense)、query rewrite | 词面错位 | 小孩子(要 dense)、少年闰土/春天(奖励 sparse) |
| ④ embedding | bge-small ↔ base/large-zh ↔ m3e | 领域术语整体低 recall | 小孩子→故乡 的语义判别 |
| ⑤ rerank | +cross-encoder，top20→top5 | gold 召回了但排在 TopK 外 | k 小、gold 排 6~20 时 |
| baseline | full-context 全塞 = oracle 上界 | — | 全部（参照系）|

**纪律**：菜单 6 行，实际只跑 baseline + 骨架 + 诊断指向的 1~2 行。未被指向的不跑、不写文档。

## 目录结构

```
experiments/
  golden/
    queries.jsonl        # golden set（3 条核心 + semantic stress set）
    corpus/              # 被检索的文档（doc_id = 文件名）
      chun.txt           #   《春》
      guxiang.txt        #   《故乡》
      distractors/       #   风格相近的散文，把检索做难（见 design.md 选择一·代价）
  configs/               # 每个实验 = 一个 yaml（Strategy 组装 / DI）
  results/
    leaderboard.md       # 数字一览，每个实验一行（"改动""决策"两列人填）
    <exp_id>.json        # 每次跑的机器真值 + 指纹（code/corpus/golden/model/config）
  journal.md             # 实验日志：观察→诊断→决策→下一步假设（学习闭环）
  eval.py                # 评测 harness（直接打 core 库，产出 json + leaderboard 行）
```

## 评测约定

- **gold 粒度 = 文档级**：判分只问"top 结果是否来自 `gold_doc`"（客观）。**不做 chunk 级 gold**（哪段算对无客观标准、人工重，见 design.md 选择四）；`queries.jsonl` 的 `gold_chunk_ids` 保留字段但不使用。
- **指标**：Recall@1 / Recall@3 / MRR / **margin**（最佳 gold 分 − 最佳非 gold 分；Recall 饱和时的脆弱性信号）。margin 只在同模型、同语料、同 chunker 的配置族内横向比较；跨 embedding 模型不直接比 margin 数值。
- **三层产物**：`results/*.json` = 机器真值(含 code/corpus/golden/model/config 指纹) ｜ `results/leaderboard.md` = 数字一览 ｜ `journal.md` = 推理与学习。耐用结论上浮 `docs/design.md` §选择。
