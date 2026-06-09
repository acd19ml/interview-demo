# 实验日志 / Lab Notebook

记录每次实验的**推理与学习**：观察 → 诊断 → 决策 → 下一步假设。

- 数字看 `results/leaderboard.md` 与 `results/*.json`；本日志只记"为什么这么判、下一步赌什么"。
- 下一轮做完先**回看上一轮的假设**是否成立，再写新条目 —— 这就是学习闭环。
- 某条结论变成耐用决策后，上浮到 `docs/design.md` §选择。

## 每条怎么写（模板）

观察 → 诊断 → 决策 → **选下一步（决策链）**；下一条以「回看」开头验证上一条的假设，形成闭环。

「选下一步」固定五步，保证每个实验→下个实验之间都有可追溯的决策链：

1. **定位**：哪条 query / 指标弱（引数据）。
2. **定段**：落在诊断链 ①~⑤ 哪段，排除了哪些段（各一句理由）。
3. **候选+排序**：本段杠杆按「成本 / 用对>换大 / 通用>手调」排序，写明否决了谁。
4. **选定+假设 Hn**：取最便宜的，写成**可证伪**的预测（某指标会怎么动）。
5. **诚实标注**：哪步靠证据、哪步靠先验（先验=待验证，不当结论）。

正序追加，最新在底。

---

## 2026-06-09 · exp-000 / exp-001 基线

- 指纹：corpus `4060baa1a7d5` · code `4de3d78+dirty` · model `bge-small-zh-v1.5`
- 结果：`results/exp-001-dense-only.json`、`results/exp-000-baseline-longcontext.json`

**观察**
- exp-001 dense-only：Recall@1/@3/MRR 全 1.000；min_margin **+0.0088**。
- 三条 margin：q1 春天 +0.2328 ｜ q2 少年闰土 +0.1905 ｜ q3 小孩子 **+0.0088**。
- q3 top3：故乡 0.4723 / 春 0.4635 / 药 0.4611（三篇挤在 0.011 内，近乎三方平局）。
- exp-000 oracle：1.000 构造值，仅 sanity —— 说明答案确实在库里，语料完整性 OK。

**诊断**
- Recall 饱和（全 1.0），但 margin 把真相暴露：q1/q2 稳，**q3 极脆**。
- q3「小孩子」零字面重合、纯语义 → 瓶颈在语义鸿沟 / embedding 能力（诊断链 ③/④）。
- 反向结论：**hybrid / BM25 不适用** —— q3 零字面重合 BM25 帮不上，q1/q2 又不需要。证据否决了消融菜单里的 hybrid。

**决策**
- 保留 exp-001 为基线。q1/q2 不动（YAGNI，没坏不修）。不上 hybrid。

**选下一步（决策链）→ exp-002**
1. **定位**（证据）：q3「小孩子」margin +0.0088（故乡 0.4723 / 春 0.4635 / 药 0.4611，近三方平局）；q1/q2 稳，不动（YAGNI）。
2. **定段**（诊断链）：③ query↔文档语义鸿沟为主、④ embedding 次之。排除 ①（oracle 过）、②（gold 已排第 1）、⑤（rerank 治"召回了但排在 TopK 外"，此处已第 1，不对症）。
3. **候选+排序**：第③段三类——(a) 检查是否用错（指令前缀，最便宜）＜ (b) query 改写/扩展（中；手挑近义词=照测试集调，有数据泄漏风险）＜ (c) 换/微调模型（贵，转④）。**否决 hybrid/BM25**：q3 零字面重合 BM25 帮不上，q1/q2 又不需要。
4. **选定+H1**：取最便宜的 (a)——query 加 bge 指令前缀、passage 不加。预测：**q3 margin 明显↑、q1/q2 不退化**。证伪则不启用该前缀，并先扩同类语义评测集，而不是直接换模型。
5. **诚实标注**：「bge 要 query 前缀」是我的**先验**、非数据所得，且 bge-v1.5 特意弱化了对指令的依赖 → 它是**待测假设**，eval 是裁判，测不动即证伪。

---

## 2026-06-09 · exp-002 query 指令前缀（回看 H1）

- 指纹：corpus `4060baa1a7d5` · code `4de3d78+dirty` · model `bge-small-zh-v1.5`
- 结果：`results/exp-002-query-instruction.json`；exp-001 已在同代码下复现（+0.0088 三条全同 → 开关对 baseline 零副作用，对照干净）。

**回看 H1：❌ 证伪，且有害。**
- 预测 q3 margin↑、q1/q2 不退化。实际：q1/q2 margin 几乎没动（+0.2330 / +0.1931），但 **q3 不升反降**：+0.0088 → **−0.0113**，故乡从 rank1 掉到 **rank3**（chun 0.3873 / yao 0.3843 / guxiang 0.3761）；Recall@1 1.000→0.667。

**诊断**
- 前缀让相似度整体下移；q3 本就近三方平局，任何扰动都可能翻盘，这次正好翻向错的。
- 印证当初的诚实标注：bge-v1.5 弱化了指令依赖，前缀在此非但无益、反把唯一弱点推下悬崖。
- 方法论收获：**先验被评测一票否决**；若按"最佳实践"盲加，会在展示题上发布回归。

**决策**：回滚 exp-002 —— `query_instruction` 保持默认空（开关与 config/json 留档作负结果）。基线仍是 exp-001。

**复议后的决策（不直接换模型）**
- 回滚 exp-002 的同时，删除未运行的换模型配置：它只有配置，没有结果，不算完成实验。
- 暂停换模型不是因为"更大模型一定错"，而是验收标准错了：`+0.0088` 是同一模型、同一语料、同一 chunker 下的 margin 信号，不能直接当作跨模型比较门槛。不同 embedding 模型的 cosine 分数尺度未必可比。
- 更根本的问题：只有 3 条 golden query，且 exp-001 已 Recall@1=1.0。继续追 q3 的 margin，容易变成围着单题调参，而不是证明系统有稳健语义检索能力。

**新的下一步（决策链）→ semantic stress set**
1. **定位**：q3 是零字面重合语义题，但当前只有 1 条语义样例，不足以支撑"换模型 / 加组件"的结论。
2. **定段**：先回到评测集覆盖度，而不是直接拉 ③/④/⑤ 的功能杠杆。排除 ③ query 扩展：容易对 gold query 手调；排除 ④ 换大模型：跨模型 margin 不可直接比；排除 ⑤ rerank：目前没有"gold 召回但排在 TopK 外"的稳定失败集。
3. **候选+排序**：先扩 semantic golden set（小孩/儿童/孩童/儿时伙伴/童年伙伴/少年形象/农村少年 等）＜ 再看是否需要 rerank/doc enrichment/query expansion ＜ 最后才换更大 embedding。
4. **选定+H2**：下一条可运行实验改为 `semantic-stress-set`（只扩 query，不改检索）。预测：若 dense-only 仍全绿，则停止；若出现 rank 退化，再按失败形态选择一个最小组件。
5. **诚实标注**：扩展 query 本身也有泄漏风险；只能加入自然、通用、面试题语义等价的查询，不为当前模型弱点手调措辞。

**复盘（更宽视角）**：H1 的前缀本质是**无条件、无业务接地的 query 侧变换**——它把 query 推离了文档语言，margin 下降正是这件事的度量。教训不止"bge-v1.5 不需要指令"，而是**任何统一、脱离语料语言的 query 改动都危险**；要做须 路由+接地+评测门控（禁止对 gold query 手调=泄漏）。耐用原则已上浮 `docs/design.md`。

---

## 2026-06-09 · semantic stress set（只扩 query，不改检索）

- 指纹：corpus `4060baa1a7d5` · golden `6511dee2946a` · code `4de3d78+dirty`
- 结果：`results/exp-001-dense-only.json`、`results/exp-002-query-instruction.json`

**回看 H2：✅ stress set 有必要。**
- 扩展 7 条自然语义 query 后，exp-001 dense-only 从原 3 条全绿变成 Recall@1 **0.500**、Recall@3 **0.900**、MRR **0.708**；semantic@1 = **3/8**。
- 弱点集中在短语义 / 主题型 query：`儿童` rank2、`孩童` rank2、`童年伙伴` rank4、`少年形象` rank3、`农村少年` rank2。
- exp-002 query_instruction 在扩展集上更差：Recall@1 **0.200**、semantic@1 = **0/8**。这强化了回滚决策。

**诊断**
- 这不是数据完整性问题：oracle sanity 全 1.000。
- 也不是"完全召回不到"：dense-only 的 Recall@3 仍有 0.900，多数失败的 gold_doc 已在 Top3/Top5，只是排序被《春》《药》《风波》压过。
- 因此主要问题从"是否有语义召回"转成"短 query 下语义排序不稳"。这更像 ⑤ rerank 的触发条件；但 `童年伙伴` rank4 也提示召回候选深度至少要放到 top5/top10。

**决策**
- 保留 exp-001 为 baseline；它满足原始 3 条题目，但不再宣称对语义 stress set 稳。
- exp-002 继续回滚；`query_instruction` 不启用。
- 删除未运行的换模型配置；下一步若继续 P2，优先设计 rerank top10→top5 的单变量实验。文档增强 / query expansion 暂不动，避免把同义词直接写进索引或 query 造成泄漏。

---

## 2026-06-09 · exp-003 rerank top10

- 指纹：corpus `4060baa1a7d5` · golden `6511dee2946a` · model `bge-small-zh-v1.5` + `bge-reranker-base`
- 结果：`results/exp-003-rerank.json`

**回看假设：大体成立，但暴露一个评测标签问题。**
- exp-003 相对 exp-001：Recall@1 **0.500 → 0.900**，Recall@3 **0.900 → 1.000**，MRR **0.708 → 0.950**，semantic@1 **3/8 → 7/8**。
- 原始题目三条仍全绿；q3「小孩子」从 margin +0.0088 提升到 +0.0352。
- 唯一 Top1 失败是 q6「孩童」：reranker 排《春》在《故乡》前。这里不能简单算模型错，因为《春》原文也有“地上孩子也多了”，而「孩童」本身泛化、无上下文，gold_doc=故乡 的唯一性不强。

**诊断**
- reranker 对“gold 已在 dense top10 里但排序不稳”的形态有效，符合 ⑤ rerank 的触发条件。
- min_margin 仍为负，来自 q6；这说明 margin 继续作为脆弱性信号有效，但此处更像评测样例歧义，而非组件继续堆叠的理由。

**决策**
- 保留 `exp-003-rerank` 作为 P2 候选方案；不把它写成最终默认，直到 stress set gold 标注审计完。
- 下一步不是继续加组件，而是审计 semantic stress set：去掉或改写 gold 不唯一的泛化 query（如「孩童」），保留能清楚指向《故乡》的关系型/主题型 query（如「儿时伙伴」「童年伙伴」「少年形象」「农村少年」）。

---

## 2026-06-09 · stress set 审计后复跑

- 指纹：corpus `4060baa1a7d5` · golden `aaa8e13802a2`
- 结果：`results/exp-001-dense-only.json`、`results/exp-002-query-instruction.json`、`results/exp-003-rerank.json`

**审计**
- 删除泛化儿童同义 query：`小孩`、`儿童`、`孩童`。理由：这些词在《春》《风波》《孔乙己》《药》中也有自然对应，gold_doc 不唯一。
- 保留关系型 / 主题型 query：`儿时伙伴`、`童年伙伴`、`少年形象`、`农村少年`。理由：它们更明确指向《故乡》里的少年闰土与回忆结构。

**复跑结果**
- exp-001 dense-only：Recall@1 **0.571**，Recall@3 **0.857**，semantic@1 **2/5**。baseline 仍能过原始三题，但 stress set 排序不稳。
- exp-002 query_instruction：Recall@1 **0.286**，semantic@1 **0/5**。负结果成立，继续回滚。
- exp-003 rerank：Recall@1/Recall@3/MRR **全 1.000**，semantic@1 **5/5**，min_margin **+0.0352**。

**决策**
- `exp-003-rerank` 从候选升为 P2 默认候选：它只新增 reranker 单变量，解决了 stress set 暴露的排序问题。
- 不继续加文档增强 / query expansion / 换 embedding。当前失败已由 rerank 处理，继续堆组件会越过停止规则。
