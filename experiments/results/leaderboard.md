# Leaderboard

每行 = 一个唯一实验。指标由 `eval.py` 产出（机器）；**"改动"和"决策"两列由人手写**，eval 不代填。
横向比较只在 **corpus / golden 列都相同** 的行之间有效（控制变量）；完整指纹见 `results/<exp_id>.json`。
跑完把 eval.py 末尾打印的整行粘进来，把 `_改动?_`、`_决策?_` 替换成实际内容。

| exp_id | 改动(相对上条) | corpus | golden | R@1 | R@3 | MRR | 最小margin | q1春天 | q2少年闰土 | q3小孩子 | semantic@1 | 决策(人填) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| exp-000-baseline-longcontext | oracle sanity | 4060baa1a7d5 | aaa8e13802a2 | 1.000 | 1.000 | 1.000 | — | ✅ | ✅ | ✅ | 5/5 | 语料 / golden 完整性 OK；1.0 为构造值 |
| exp-001-dense-only | 审计后 stress set baseline | 4060baa1a7d5 | aaa8e13802a2 | 0.571 | 0.857 | 0.726 | -0.0365 | ✅ | ✅ | ✅ | 2/5 | 保留为 baseline；关系/主题 query 仍排序不稳 |
| exp-002-query-instruction | +query 指令前缀 | 4060baa1a7d5 | aaa8e13802a2 | 0.286 | 1.000 | 0.571 | -0.0206 | ✅ | ✅ | ❌ | 0/5 | 回滚：审计后继续证伪；query_instruction 不启用 |
| exp-003-rerank | +cross-encoder rerank top10 | 4060baa1a7d5 | aaa8e13802a2 | 1.000 | 1.000 | 1.000 | +0.0352 | ✅ | ✅ | ✅ | 5/5 | 保留：审计后全绿且 margin 转正；P2 默认候选 |

> margin = 最佳 gold-doc chunk 分 − 最佳非 gold-doc chunk 分。它用于暴露 Recall 饱和后的排序脆弱性；只在同模型、同语料、同 chunker 的配置族内横向比较，不作跨模型验收目标。
> oracle 行（exp-000）的 1.000 是构造值、非真上界，margin 不适用，仅作 sanity。
> semantic@1 = axis 以 `semantic` 开头的 query 中 Top1 命中文档数 / 该类 query 总数。
