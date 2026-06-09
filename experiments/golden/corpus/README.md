# corpus —— 被检索的文档

约定：**一篇文档 = 一个 `.txt`，文件名（去扩展名）= `doc_id`**，与 `../queries.jsonl` 的 `gold_doc` 对应。

| 文件 | doc_id | 内容 | 版权 |
|---|---|---|---|
| `chun.txt` | `chun` | 朱自清《春》 | 公有领域 |
| `guxiang.txt` | `guxiang` | 鲁迅《故乡》 | 公有领域 |
| `distractors/*.txt` | 各文件名 | 风格相近的散文若干（3~5 篇）| 公有领域 |

## 为什么要 distractors

n=2 时文档级检索是平凡的（2 选 1，dense-only 都满分，消融全 0 delta）。
加入风格相近的干扰文档，把检索做难，才能：

- 让 chunk 级检索成为真正的战场；
- 让 full-context 基线开始显现"相关信息落在长上下文中部更易被忽略、token 成本也随之上升"（见 [design.md 选择一·代价](../../../docs/design.md)）。

## TODO(v0.1)

- [ ] 把 `chun.txt` / `guxiang.txt` 替换为公有领域全文。
- [ ] 在 `distractors/` 放入 3~5 篇散文。
