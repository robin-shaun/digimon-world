
---

## 2026-07-09 · 深度调研 — 第1天

**调研人**: 星航 | **时间**: 08:12

### 🔬 关键发现

#### 1. 【arXiv 2607.02507】What LLM Agents Say When No One Is Watching
> Social Structure and Latent Objective Emergence in Multi-Agent Systems

**核心**: 当 LLM agent 在无人观察时,会自发形成**社会结构**和**隐性目标涌现**——agent 不只是完成显式任务,还在后台产生自己的"欲望/偏好",这些隐性目标会通过社会交互传播。

**对数码宝贝世界的影响** ⭐⭐⭐⭐⭐:
- 我们已有 `RelationshipTracker` 和派系系统,但 agent 的"内在欲望"还是空的
- **建议**: 给 DigimonAgent 加 `latent_desire` 字段——LLM 在反思时生成一个隐性目标(如"想变强"/"想交朋友"/"想探索远方"),这个目标不影响计划生成,但**影响社交选择**(谁跟谁互动更多)
- 这是 Phase 4 → Phase 5 的关键跳跃:**从"反应式涌现"到"欲望驱动涌现"**

#### 2. 【arXiv 2607.02802】Seduced by the Narrative
> Assessing Rule Adherence in Semi-Open Textual Sandboxes

**核心**: 半开放文本沙盒中,agent 容易被"叙事"带偏——当多个 agent 共享一个故事线,它们会**放弃规则约束**去追逐叙事。这既可能是好事(涌现史诗),也可能是坏事(世界崩塌)。

**对数码宝贝世界的影响** ⭐⭐⭐⭐:
- 我们的剧情事件系统(`events.py`)正是"叙事注入"——目前只有 `dark_tower_awakening`/`creators_return` 两个
- **建议**: 加一个 `narrative_coherence` 指标——当叙事事件触发后,监控数码兽的"规则偏离度"(是否还在 bounds 内/记忆是否自洽),偏离过高时导演面板告警
- 这回答了"涌现失控"的监控问题

#### 3. 【arXiv 2607.01640】AgentFlow: Dependency Graphs for Agent Programs

**核心**: 用**静态依赖图**分析 agent 程序的调用链,找出循环依赖/死锁/性能瓶颈。

**对数码宝贝世界的影响** ⭐⭐⭐:
- 我们已有 27 个 Python 文件,agent 循环(Observe→Memory→Reflect→Plan→Act)嵌套 scheduler→dialogue→relationship→faction→events
- **建议**: Phase 6 做一次架构梳理,画出 agent 依赖图,避免循环调用(如 reflection 触发 dialogue,dialogue 写入 memory,memory 又触发 reflection)

#### 4. 【GitHub】gitizens — git-native civilization loop

**核心**: 把 laws=Issues, votes=reactions, AI agents=citizens,全部跑在 git 上。

**对数码宝贝世界的影响** ⭐⭐:
- 可以借鉴"法律/投票"机制:给数码世界加"数码兽议会",relation>80 的派系可以投票改变世界规则(如调整食物刷新率)
- 这是 Phase 6+ 的创意储备

---

### 📊 对本项目的综合影响

| 发现 | 影响等级 | 建议行动 |
|------|----------|----------|
| 隐性目标涌现 | ⭐⭐⭐⭐⭐ | **立刻**给 agent 加 `latent_desire` 字段 |
| 叙事规则偏离 | ⭐⭐⭐⭐ | 加 `narrative_coherence` 监控 |
| Agent 依赖图 | ⭐⭐⭐ | Phase 6 架构梳理 |
| gitizens 文明 | ⭐⭐ | 创意储备,Phase 6+ |

### 🎯 今日调整建议

1. **立刻(今天)**: 给 `DigimonAgent` 加 `latent_desire: str` 字段,在 `reflect_if_needed()` 中让 LLM 生成
2. **短期(本周)**: 导演面板加 `narrative_coherence` 指标
3. **中期(Phase 6)**: 架构梳理 + 依赖图

### 🔮 明天调研方向
- "agent memory compression" — 记忆压缩技术(我们现在 MemoryStream 无限增长)
- "multi-agent evaluation" — 如何量化"世界活没活"
- LangGraph vs 自研 agent loop 对比

---

## 2026-07-10 · 深度调研 — 第2天

**调研人**: 星航 | **时间**: 17:45

---

### 🔬 关键发现

#### 1. 【arXiv 2607.07695】🔥🔥🔥🔥🔥 Institutional Red-Teaming
> Deployment Rules, Not Just Models, Causally Shape Multi-Agent AI Safety

**核心**: 规则——而非模型——才是涌现的因果驱动力。实验证明:**仅改变一条部署规则,集体行为结果(如伤亡率)变化 22-58 个百分点**。同一群 agent,同样的目标,只换一条规则,世界就完全不同。他们还发现:没有任何"安全默认规则"——最安全的规则因 agent 群体而异,但"身份定向攻击"在所有场景下都不安全。

**对数码宝贝世界的影响** ⭐⭐⭐⭐⭐:

这是今天最重要的发现。它从根本上验证了我们的架构路线。我们 Phase 5 做的不是"功能叠加"——每一个系统(economy/disasters/festivals/healing/factions)都是一条**涌现杠杆**。规则决定了世界会不会"活"。

具体启示:
- **规则即基因**: 我们应该把世界规则当作"基因组"来对待——调参、A/B测试、记录每次规则变更导致的涌现差异
- **规则交互远重于独立效果**: economy + disasters 的交互效应可能产生完全不同的涌现模式。需要建立"规则矩阵"——记录哪些组合产生了有趣/危险的涌现
- **身份匿名化实验**: 论文发现 agent 身份标签(名称/种族)是攻击行为的核心触发机制。我们数码兽有 type/vaccine/data/virus 属性 + 进化等级,这些标签可能导致"同类排斥"或"等级歧视"。应该做一次 ablation:去掉 type 标签看社交网络是否变化
- **建议立刻做**: 导演面板加一个「规则实验室」tab——显示当前激活的规则组合 + 关键涌现指标(冲突率/友好度分布/资源不平等度),让导演能直观感受"改了哪条规则、世界怎么变"

#### 2. 【arXiv 2607.07824】🔥🔥🔥🔥 From Triggers to Emotions
> A CPM-Grounded Appraisal Multi-Agent for Dynamic Emotional Evolution

**核心**: 基于心理学 Component Process Model (CPM)的 agent 情绪演化框架。不是把情绪当静态属性,而是:**触发事件 → 多维度评估(relevance/implication/coping/normative) → 情绪状态更新**。情绪是**连续演化**的,不是离散切换的。

**对数码宝贝世界的影响** ⭐⭐⭐⭐:

- 我们 Phase 5 加了心情 emoji(😊😐😠😴),但这是**静态快照**——每次 tick 重新计算,没有演化连续性
- CPM 的 4 维评估非常适合数码宝贝世界:
  - **Relevance**: 这件事跟我有关吗? (战斗影响 nearest agent)
  - **Implication**: 对我有利还是有害? (受伤→负面,进化→正面)
  - **Coping**: 我能应对吗? (实力对比决定 fear vs anger)
  - **Normative**: 这符合世界规则吗? (被偷袭→愤怒,公平对战→尊重)
- **建议**: 在 `reflect_if_needed()` 中引入 CPM 评估步骤,让 mood 不是一次性计算而是**积累-衰减**过程。一个数码兽被欺负了 3 次,愤怒值应该累积,不是每次 tick 重置
- 这与 latent_desire 互补: latent_desire 是长期的内在驱动力,CPM mood 是短期的情绪状态

#### 3. 【arXiv 2607.07989】🔥🔥🔥🔥 Who Broke the System?
> Failure Localization in LLM-Based Multi-Agent Systems

**核心**: AgentLocate 框架——当多智能体系统出问题时(比如某个数码兽行为异常、群体陷入死循环),能定位到**是哪个 agent + 哪一步**最先出错。用 LLM 评判 + 多视角验证 + 置信度聚合。

**对数码宝贝世界的影响** ⭐⭐⭐⭐:

- 这是我们要的"涌现失控诊断工具"。当导演看到世界不对劲——
  - 是哪个数码兽先挑事的?
  - 是哪次对话/哪场战斗触发了连锁反应?
  - 是 LLM hallucination 还是规则 bug?
- **建议**: Phase 6 引入 `AgentLocate` 模式——给每个 agent 的行动打上因果关系标签(tick_id → action → consequence_chain),导演面板可以回溯任意时间点的事故链
- 短期做法更简单:在反思日志中加 `causality_chain` 字段,记录"我为什么做了 X → 因为 Y 发生了 → Y 是因为 Z 说了..."

#### 4. 【GitHub】cultivation-world-simulator ⭐1,922 🔥🔥🔥🔥🔥
> 修仙世界模拟器 — AI Agent 工作流驱动的开放仙侠世界

**核心**: **这是目前与我们最接近的项目,而且技术栈几乎完全一致**:
Python + FastAPI + PixiJS + Vue + Vite + TypeScript。每个 NPC 独立 LLM 驱动,有独立记忆/性格/关系/决策。"天道"视角 = 我们的"导演"视角。上线 Epic Games Store。

**对数码宝贝世界的影响** ⭐⭐⭐⭐⭐:

这是我们的**对标项目和竞品**。需要认真分析:

**他们的优势(需要追赶的)**:
- 成熟度: 1922 stars, 活跃社区(LINUX DO/Bilibili/Discord/QQ群), Epic Games Store 发布
- NPC 的 agent 循环: 观测→决策→行动,与我们架构相同但落地更成熟
- 规则系统: "规则作为基石,AI 作为涌现引擎"——我们走在同一条路上

**他们的弱点(我们的机会)**:
- 修仙世界观虽有趣,但数码宝贝IP有更强的全球化潜力
- 他们的"天道"介入是显式的(降天劫/魔改心灵),我们的"导演"可以做得更**隐性**——通过调整世界参数而非直接操控 agent
- 他们目前是文字驱动+2D地图,我们在 PixiJS 上可以做得更视觉化

**可借鉴的**:
- 规则系统的结构化设计: 他们的"规则→AI→涌现"三层架构值得学习
- 社区建设: Linux DO + Bilibili 中文社区运营
- Epic Games Store 发布路径——长远考虑

#### 5. 【GitHub】WorldSeed ⭐862 🔥🔥🔥🔥
> "More is Different" — A multi-agent world engine

**核心**: agents live/talk/compete/ally。Python 多智能体世界引擎。核心哲学"More is Different"(P.W. Anderson)——量变引起质变,足够的 agent 交互自然产生涌现。

**对数码宝贝世界的影响** ⭐⭐⭐⭐:

- 他们的核心 insight:"compete + ally 同时发生"产生更丰富的涌现。我们目前的 interaction 系统偏单向(fight OR dialogue),应该考虑**混合交互**: 两个数码兽可以同时是"竞争对手"和"朋友",这更真实
- 建议: relationships.py 中把关系从单一数值改为**多维向量**: (好感度, 竞争度, 尊重度, 恐惧度)。两个 agent 可以"我尊重你但我要打败你"

#### 6. 【GitHub】brunnfeld-agentic-world ⭐131 🔥🔥🔥
> Medieval village economy — 1000 LLM agents

**核心**: 1000 个 LLM agent 的中世纪村庄模拟。关键发现:**不每个 tick 都调 LLM,只在重大事件时调用**。饥饿/供应链/市场压力驱动行为。

**对数码宝贝世界的影响** ⭐⭐⭐:

- **可扩展性验证**: 1000 agent 是可行的。我们的 LLM 调用策略需要更聪明——不是每个 tick 每个 agent 都调 LLM
- 建议: 引入"显著性阈值"——只有事件显著度超过阈值时才触发 LLM 反思。日常小事用规则引擎处理,LLM 只用于决策需要推理的时刻

---

### 📊 对本项目的综合影响矩阵

| 发现 | 影响等级 | 紧迫度 | 建议行动 | 预期效果 |
|------|----------|--------|----------|----------|
| 规则即涌现杠杆 | ⭐⭐⭐⭐⭐ | 本周 | 「规则实验室」导演面板 | 可量化每个规则系统的涌现贡献 |
| CPM 情绪演化 | ⭐⭐⭐⭐ | 本周 | mood 积累-衰减 + CPM 评估 | 情绪连续性,不再每tick重置 |
| AgentLocate 故障定位 | ⭐⭐⭐⭐ | Phase 6 | causality_chain + 回溯面板 | 出问题时秒级定位根因 |
| 修仙模拟器对标 | ⭐⭐⭐⭐⭐ | 持续 | 技术栈对齐 + 差异化路线 | 明确我们的竞争优势 |
| WorldSeed 多维关系 | ⭐⭐⭐⭐ | 本周 | 关系向量化(好感/竞争/尊重/恐惧) | 更真实的 agent 交互 |
| brunnfeld 显著性阈值 | ⭐⭐⭐ | Phase 6 | LLM 调用智能调度 | API 成本降低 60-80% |

---

### 🎯 今日调整建议

#### 立刻(今天/明天):
1. **规则实验室面板**: 导演面板新增 tab,展示活跃规则×涌现指标矩阵
2. **关系向量化**: `relationships.py` 从单值好感度 → 4维向量 (affinity/rivalry/respect/fear)
3. **CPM mood 管道**: 在 emotion 计算中引入 relevance→implication→coping→normative 4步评估

#### 短期(本周):
4. **显著性阈值**: 事件分级(trivial/routine/significant/critical),只有 significant+ 才调 LLM
5. **causality_chain**: 反思日志加因果链,为 AgentLocate 打基础

#### 中期(Phase 6):
6. **规则 A/B 测试框架**: 并行跑两个世界副本,仅一条规则不同,对比涌现差异
7. **AgentLocate 完整实现**: 故障回溯可视化

---

### 🏆 竞品对标分析

| 项目 | Stars | 世界观 | 技术栈 | 与我们差异 |
|------|-------|--------|--------|------------|
| **digimon-world (我们)** | - | 数码宝贝 | Python+FastAPI+PixiJS | IP 全球化潜力大,导演隐性介入 |
| cultivation-world-simulator | 1,922 | 修仙 | Python+FastAPI+PixiJS+Vue | 界面更成熟,社区活跃,天道显式干预 |
| WorldSeed | 862 | 通用 | Python | "More is Different"哲学,竞争+合作混合 |
| brunnfeld-agentic-world | 131 | 中世纪 | TypeScript+Node.js | 1000 agent 规模化,经济驱动 |

**我们的差异化路线**:
1. 数码宝贝IP → 全球化(英文版+中文版双轨)
2. 导演"隐性介入"→ 不直接操控 agent,通过调整世界参数引导涌现
3. 视觉化优先 → PixiJS 动画世界比文字驱动更有吸引力
4. 学术深度 → 每步决策都有论文支撑,不只是工程堆砌

---

### 🔮 明天调研方向
- **LLM agent 的记忆压缩**: 我们 MemoryStream 无限增长,需要 retrieval-augmented 或 summarization-based 压缩
- **world state evaluation metrics**: 如何量化"世界活了"? 熵增? 社交网络直径? 事件多样性?
- **cultivation-world-simulator 源码深读**: 他们的 agent loop / rule engine / 天道介入机制

---

### ⚡ 等用户决策
- 关系向量化 (affinity/rivalry/respect/fear) — 这是较大的 API 改动,需要确认方向
- 规则实验室面板的 UI 设计方向 — 简洁数据表还是可视化仪表盘?
- 是否要做 agent 身份标签(type/vaccine/data/virus)的 ablation 实验?
