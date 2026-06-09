# Leaderboard

每条改动一行。"改动"列只写**相对上一行变了什么**（一次一个杠杆）。
q1/q2/q3 列填该 golden query 是否命中（✅/❌）。决策列写**保留 / 回滚**及一句原因。

| exp_id | 改动(相对上条) | Recall@1 | Recall@3 | MRR | q1 春天 | q2 少年闰土 | q3 小孩子 | 决策 | 依据 |
|---|---|---|---|---|---|---|---|---|---|
| exp-000-baseline-longcontext | oracle 上界 | – | – | – | – | – | – | 参照系 | design.md 选择一 |
| exp-001-dense-only | 骨架基线 | _待跑_ | | | | | | | design.md 选择二 |

> 说明：oracle 行不参与检索指标，仅作答案上界参照。
