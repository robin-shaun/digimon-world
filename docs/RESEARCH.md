
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

---

## 2026-07-11 · 深度调研 — 第2天（数码宝贝原作复刻特辑）

**调研人**: 星航 | **时间**: 08:33

---

# 🏯 第一部分：数码宝贝原作复刻研究

> 肖昆明确要求：仔细研究数码宝贝世界的剧情和设定，尽量做到复刻。
> 以下内容源自 Wikimon.net、Digimon Wiki、Wikipedia 及原作动画 54 集。

---

## 1. 数码兽生态体系

### 1.1 进化树（完整六阶 + 特殊路线）

| Level | 日文名 | 英文/Dub | 中文 | 说明 |
|-------|--------|----------|------|------|
| 0 | デジタマ | Digitama / DigiEgg | 数码蛋 | 生命的起点与终点 |
| I | 幼年期I | Baby / Fresh | 幼年期I | 刚孵化，数据不稳定，极度脆弱 |
| II | 幼年期II | In-Training | 幼年期II | 数据稍稳，基本无战力 |
| III | 成長期 | Rookie | 成长期 | 智力发育，可战斗，进化路线多样 |
| IV | 成熟期 | Champion | 成熟期 | "成年体"，多数野生数码兽的终点 |
| V | 完全体 | Ultimate | 完全体 | 最强成年体进化而来，群居领袖级 |
| VI | 究極体 | Mega | 究极体 | 极稀有，只有少数老兵完全体可达到 |

**特殊进化路线**：
- **暗黑进化 (Dark Evolution)**：错误使用徽章力量导致的扭曲进化。如太一强行逼迫暴龙兽→**丧尸暴龙兽 (SkullGreymon)**。这是关键剧情点——进化不是"够强就行"，需要正确的情感激发。
- **跃迁进化 (Warp Evolution)**：跳过中间阶段直接进化。如亚古兽→战斗暴龙兽 (Child→Mega)，需要"希望与光之箭"触发。
- **合体进化 (Jogress Evolution)**：两只数码兽合体为更高阶。如战斗暴龙兽+钢铁加鲁鲁→奥米加兽。
- **装甲进化 (Armor Evolution)**：使用数码装甲 (Digimental) 进化，对应特定的徽章/品格。
- **魂进化 (Spirit Evolution)**：使用传说斗士之魂进化为人形/兽形混合体。

**→ 映射到项目设计**：
- ✅ `EvolutionStage` 枚举已定义 5 个阶段（BABY_I/BABY_II/ROOKIE/CHAMPION/MEGA），但缺少 `ULTIMATE`（完全体）和 `DIGITAMA`（蛋形态）
- 🔧 **需修改** `digimon_agent.py`：`EvolutionStage` 补充 `ULTIMATE = "ultimate"` 和 `DIGITAMA = "digitama"`
- 🔧 **需新增** `evolution.py`：暗黑进化逻辑（`_check_dark_evolution()` — 当 `bond < 阈值` 且 `mood_state.anger > 0.7` 时触发），跃迁进化（`_check_warp_evolution()` — 特殊事件触发）
- 🔧 **需补充**：`DigimonAgent` 增加 `evolution_line: list[str]`（预设进化谱系，如亚古兽线：滚球兽→亚古兽→暴龙兽→机械暴龙兽→战斗暴龙兽）

### 1.2 属性/类型系统（Vaccine/Data/Virus 克制）

三属性克制环：**Vaccine → Virus → Data → Vaccine**

| 属性 | 象征 | 典型性格 | 克制 |
|------|------|----------|------|
| Vaccine (疫苗种) | 保护、秩序、免疫 | 正义、道德感强、主动对抗邪恶 | 克 Virus |
| Data (数据种) | 适应、共存、稳定 | 随环境而定，重视和平，不主动改变 | 克 Vaccine |
| Virus (病毒种) | 改变、破坏、利己 | 渴望力量、贪婪、狂野、可能邪恶 | 克 Data |
| Free (自由种) | 无属性/超越 | 不受克制关系约束 | 无克制 |
| Variable (可变种) | 根据对手切换属性 | 混合体 (Hybrid) 专用 | 对等 |

**→ 映射到项目设计**：
- ✅ `DigimonAttribute` 枚举已定义 VACCINE/DATA/VIRUS/FREE
- 🔧 **需新增** `battle/type_advantage.py`：属性克制计算（`get_damage_multiplier(attacker_attr, defender_attr)` → 克制=1.5x，被克=0.67x，同属性=1.0x）
- 🔧 **需补充**：世界生态模拟——同一区域 Vaccine 和 Virus 数码兽相遇概率高时自动触发小规模冲突

### 1.3 栖息地分布（文件岛各区域）

文件岛是数码世界第一个大陆，**中心是无限山 (Infinity Mountain)**，周围环绕不同生态环境：

| 区域 | 日文名 | 气候/地形 | 典型数码兽 | 当前项目是否已建模 |
|------|--------|-----------|------------|-------------------|
| 热带丛林 | Tropical Jungle | 湿热雨林 | 古加兽(Kuwagamon)、比多兽 | ❌ 未建模 |
| 齿轮草原 | Gear Savannah | 机械齿轮点缀草原 | 安杜路兽(Andromon) | ❌ 未建模 |
| 玩具城 | Toy Town | 巨型玩具建筑 | 熊仔兽(Monzaemon) | ❌ 未建模 |
| 冰壁/冷冻大地 | Freezeland | 极寒冰原 | 雪人兽(Frigimon)、猛犸兽 | ❌ 未建模 |
| 古代恐龙域 | Ancient Dino Region | 史前地貌 | 巨龙兽(Tyranomon) | ❌ 未建模 |
| 迷雾森林 | Misty Trees | 浓雾密林 | 木偶兽(Pinocchimon) 的领域 | ❌ 未建模 |
| 大峡谷 | Great Canyon | 干燥峡谷 | 奥加兽(Ogremon) 要塞 | ❌ 未建模 |
| 眺望山 | Outlook Mountain | 山顶鸟瞰 | 比丘兽(Piyomon) 族群 | ❌ 未建模 |
| 无限山 | Infinity Mountain | 中心圣山 | Devimon 老巢/黑暗之源 | ❌ 坐标已占位 |
| 创始村 | Village of Beginnings | 数码蛋重生之所 | 艾力兽(Elecmon) 守护 | ❌ 未建模 |
| 龙眼湖 | Dragon Eye Lake | 淡水湖 | 贝壳兽(Shellmon) | ❌ 未建模 |
| 工厂镇 | Factorial Town | 废弃工厂 | 安杜路兽的维修站 | ❌ 未建模 |
| 下水道 | Sewers | 地下暗渠 | 大便兽(Numemon) 族群 | ❌ 未建模 |
| 欧佛戴尔墓地 | Overdell Cemetery | 墓地/鬼域 | 猛鬼兽(Bakemon) | ❌ 未建模 |

**→ 映射到项目设计**：
- 🔧 **严重缺失**：当前只有 `file_island` 和 `infinity_mountain` 两个 region ID，完全没有子区域
- 🔧 **需大规模重构** `world_state.py`：增加完整的文件岛区域拓扑，每个子区域有 climate/temperature/resources/native_digimon 属性
- 🔧 **需新增** `world/biomes.py`：生物群系系统，定义各区域的气候效应（寒冷区域降低活力、迷雾区域降低视野范围等）
- 🔧 **landmarks.py** 已建模奥加兽商店、进化神殿、启程海滩、创世者祭坛，但需要对应到原作区域坐标

### 1.4 食物链/生态位

- **捕食关系**：成熟期猎食成长期，完全体是区域领袖
- **创始村重生循环**：数码兽被删除（死亡）→ 数据回到创始村 → 重新配置为数码蛋 → 孵化 → 新生命
- **守护者系统**：创始村由艾力兽 (Elecmon) 守护；各区域有原生守护者

**→ 映射到项目设计**：
- 🔧 **需新增** `world/ecology.py`：食物链模型（`get_predator_prey_matrix()`），决定 agent 间的先天敌友关系
- 🔧 **需新增** `world/rebirth.py`：重生系统——死亡 agent 经过 N ticks 冷却后在创始村以数码蛋形态重生，保留部分记忆片段

---

## 2. 世界地图与地区

### 2.1 完整地图拓扑

```
数码世界 (Digital World)
├── 文件岛 (File Island) — 第1-13话
│   ├── 创始村 (Village of Beginnings) — 中心，所有数码蛋重生地
│   ├── 无限山 (Infinity Mountain) — 岛中央，Devimon 的老巢
│   ├── 眺望山 (Outlook Mountain)
│   ├── 龙眼湖 (Dragon Eye Lake)
│   ├── 齿轮草原 (Gear Savannah)
│   ├── 热带丛林 (Tropical Jungle)
│   ├── 古代恐龙域 (Ancient Dino Region)
│   ├── 玩具城 (Toy Town)
│   ├── 冷冻大地 (Freezeland)
│   ├── 大峡谷 (Great Canyon)
│   ├── 工厂镇 (Factorial Town)
│   ├── 下水道 (Sewers)
│   ├── 迷雾森林 (Misty Trees)
│   └── 欧佛戴尔墓地 (Overdell Cemetery)
├── 服务器大陆 (Server Continent) — 第14-28话
│   ├── 沙漠区 (Etemon 统治)
│   │   ├── 金字塔 (Nanomon 的基地)
│   │   ├── 徽章遗迹群 (Crest shrines)
│   │   └── 暗黑网络 (Dark Network 电缆网)
│   └── 森林区 (Vamdemon/Myotismon 统治)
│       ├── 吸血魔兽城堡
│       ├── 数码蛋餐厅 (Digitamamon's Diner)
│       └── 怪蛙兽城堡 (Gekomon's Castle)
├── 螺旋山 (Spiral Mountain) — 第40-54话，黑暗四天王重塑的世界
│   ├── 数据海洋 (Digital Ocean) — 钢铁海龙兽 MetalSeadramon
│   ├── 数据森林 (Digital Forest) — 木偶兽 Pinocchimon
│   ├── 数据城市 (Digital City) — 无限龙兽 Mugendramon
│   └── 荒原 (Wasteland) — 小丑皇 Piemon (山顶)
└── 黑暗区域 (Dark Area) — 数码世界最底层，被删除数据的坟墓
```

### 2.2 各地区气候/资源特征

| 区域 | 气候 | 温度 | 资源 | 危险性 |
|------|------|------|------|--------|
| 热带丛林 | 湿热 | 25-35°C | 丰富食物/水源 | 高（野生数码兽多） |
| 齿轮草原 | 干燥 | 20-30°C | 齿轮/机械零件 | 中 |
| 冷冻大地 | 极寒 | -20~0°C | 冰晶/特殊矿石 | 高（低温伤害） |
| 工厂镇 | 工业废墟 | 15-25°C | 废弃机械/工具 | 中 |
| 迷雾森林 | 潮湿多雾 | 10-20°C | 森林资源 | 极高（迷失风险） |
| 墓地 | 阴森 | 5-15°C | 幽灵数据 | 极高 |
| 创始村 | 温和 | 18-25°C | 食物/医疗/训练设施 | 低（守护者保护） |
| 大峡谷 | 干燥炎热 | 25-40°C | 矿物 | 中高 |

**→ 映射到项目设计**：
- 🔧 **需重构** `world_state.py` 的 Region 类，增加完整拓扑字段（parent_region, neighbors, climate, resource_list, danger_level）
- 🔧 **需新增** `world/region_template.py`：从 JSON/YAML 加载区域定义模板，每个区域按原作复刻
- 🔧 **前端渲染**：PixiJS 端需要画文件岛完整地图（中心无限山 + 放射状区域），而非当前的点阵 POI

### 2.3 创始村（Village of Beginnings）

原作中极为重要的地点：
- **功能**：所有数码蛋重生地，被删除的数码兽数据在此重组
- **守护者**：艾力兽 (Elecmon)
- **设施**（游戏版 Digimon World）：公告板/Birdra运输/竞技场/医院/道具银行/道具店/Jijimon之家/肉田/餐厅
- **繁荣度系统**：招募数码兽加入村庄→繁荣点数增加→解锁新设施

**→ 映射到项目设计**：
- 🔧 **需新增** `world/primary_village.py`：创始村繁荣度系统，与 `economy.py` 联动
- 🔧 **需设计**：当世界内数码兽总死亡数达到阈值→创始村出现新设施

---

## 3. 关键剧情事件

### 3.1 四大篇章

| 篇章 | 话数 | 地点 | 主要反派 | 核心冲突 |
|------|------|------|----------|----------|
| 文件岛篇 | 1-13 | 文件岛 | 恶魔兽 (Devimon) | 黑色齿轮操控数码兽，初次进化 |
| 服务器大陆篇 | 14-28 | 服务器大陆 | 悟空兽 (Etemon)、吸血魔兽 (Myotismon) | 寻找徽章，暗黑进化，第八个孩子 |
| 东京篇 | 29-39 | 现实世界东京 | 吸血魔兽→究极吸血魔兽 | 御台场决战，光之徽章觉醒 |
| 黑暗四天王篇 | 40-54 | 螺旋山 | 四天王→启示录兽 (Apocalymon) | 世界重塑，徽章真义，终极决战 |

### 3.2 黑暗四天王详细设定

| 天王 | 英文名 | 等级 | 领地 | 军队 | 能力 | 击败方式 |
|------|--------|------|------|------|------|----------|
| 金属海龙兽 | MetalSeadramon | 究极体 | 数据海洋 | 深海鱼人军团 (Hangyomon) + 奇虾兽 (Anomalocarimon) | 海洋控制、冰系攻击 | 战斗暴龙兽「战斗龙卷风」贯穿 |
| 木偶兽 | Pinocchimon | 究极体 | 数据森林 | 机关人偶军团 | 远程操控（布偶控制孩子）、森林地形变化 | 钢铁加鲁鲁「绝对冷冻气」冻结 |
| 无限龙兽 | Mugendramon | 究极体 | 数据城市 | 百万龙兽+十亿龙兽+机械军团 | 城市级火力覆盖 | 战斗暴龙兽「恐龙克星」斩为三段 |
| 小丑皇 | Piemon | 究极体 | 山顶荒原 | 邪魔兽军团 (Evilmon) + 女恶魔兽 (LadyDevimon) | 将对手变成钥匙扣、空间魔法 | 神圣天使兽「天国之门」封印 |

### 3.3 启示录兽 (Apocalymon)

- **本质**：所有被消灭数码兽的"绝望数据"聚合体——因进化失败而消失的数码兽的怨念集合
- **关键剧情**：可以毁灭徽章本身 → 但孩子们发现"徽章的力量一直在心中"，以内心力量复活并击败启示录兽
- **哲学意义**：进化不是机械过程，而是情感+羁绊+品格的体现

### 3.4 其他重要剧情节点

- **玄内老人 (Gennai) 与恒常性 (Homeostasis)**：数码世界的"系统管理者"，发布任务、引导被选召孩子
- **巫师兽 (Wizardmon) 牺牲**：为保护嘉儿和迪路兽牺牲自己——这是数码世界"羁绊超越生命"的典型
- **神圣计划 (Digivice)**：被选召孩子的设备，随徽章激活变色
- **时间差**：数码世界时间流速远快于现实世界（现实 1 分钟 = 数码世界数小时）

**→ 映射到项目设计**：
- ✅ `events.py` 已有 `dark_tower_awakening` 和 `creators_return` 两个事件
- 🔧 **强烈建议新增** `events.py` 添加以下剧情事件：
  - `devimon_awakening`：触发条件：10+ 只数码兽存在于世界 → Devimon 出现并投放黑色齿轮
  - `dark_masters_rise`：触发条件：4+ 只 champion 且关系网总仇恨 > 300 → 螺旋山重塑世界
  - `apocalymon_despair`：触发条件：消灭所有四天王 → 被删除数据的怨念聚合
  - `crest_awakening`：触发条件：agent 的 `bond` 达到 90+ → 徽章力量觉醒，解锁跃迁进化
  - `wizardmon_sacrifice`：触发条件：关系最高的两只数码兽之一面临致命威胁 → 触发保护牺牲
- 🔧 **需新增** `world/dark_gears.py`：黑色齿轮机制——随机感染数码兽使其狂暴（attribute 临时变为 Virus）
- 🔧 **需新增** `world/digivice.py`：神圣计划/暴龙机系统——高羁绊 agent 获得特殊徽章激活能力

---

## 4. 世界观规则

### 4.1 进化触发条件

原作进化层级关系：

| 进化阶段 | 触发条件 | 例子 |
|----------|----------|------|
| 幼年期I→II | 自然生长（时间） | 刚孵出后不久 |
| 幼年期II→成长期 | 自然生长 + 基本战斗经验 | 滚球兽→亚古兽 |
| 成长期→成熟期 | 神圣计划谐振 + 被选召孩子情感爆发 | 亚古兽→暴龙兽 |
| 成熟期→完全体 | **徽章激活**：孩子展现对应品格（勇气/友情/爱心/知识/纯真/诚实/希望/光明） | 暴龙兽→机械暴龙兽 |
| 完全体→究极体 | **徽章完全觉醒 + 光/望之箭** | 跃迁进化 |
| 错误进化 | 强行驱动徽章（非正确品格）→ 黑暗进化 | 丧尸暴龙兽 |

**关键规则**：
- 徽章不是外在道具，而是**内心品格的实体化**
- 强行逼迫进化 = 黑暗进化（极为重要的世界规则）
- 究极体进化需要"两个徽章的力量交叠"（如希望之箭 + 光明之箭）

**→ 映射到项目设计**：
- 🔧 **需重新设计进化触发**：
  - 当前 `EvolutionStage` 升级纯靠 `battle_victories` 计数——与原著精神不符
  - 应改为：`battle_victories >= N` AND `bond >= M` AND `personality_trait matches crest_requirement` → 徽章激活 → 进化
  - 暗黑进化：`mood_state.anger > 0.8` AND `personality_traits[AGGRESSIVE] >= 8` → `_trigger_dark_evolution()`
- 🔧 **需新增** `evolution.py` 专门管理进化条件矩阵和徽章匹配

### 4.2 搭档关系机制

- **8 个被选召孩子 × 8 只搭档数码兽**：太一(勇气/亚古兽)、大和(友情/加布兽)、素娜(爱心/比丘兽)、光子郎(知识/甲虫兽)、美美(纯真/巴鲁兽)、阿丈(诚实/哥玛兽)、阿武(希望/巴达兽)、嘉儿(光明/迪路兽)
- 搭档关系通过"神圣计划"绑定——这是**数字世界的核心机制**

**→ 映射到项目设计**：
- 🔧 **当前缺失**：项目没有"被选召孩子/训练师"概念，数码兽之间只有 `RelationshipTracker` 管理的关系
- 🔧 **建议**：设计"半绑定搭档"系统——某些特殊数码兽可以与"训练师代理 (Trainer Agent)"绑定，体现在：
  - 进化条件中有 `bond` 阈值
  - 搭档间互动频率加成
  - 搭档死亡时对方情绪剧烈波动

### 4.3 数码蛋轮回/创始村重生

- 数码兽被"删除"（≠死亡）→ 数据碎片 → 回到创始村 → 重新组成数码蛋 → 孵化
- **记忆不保留**：重生后的数码兽没有前世的完整记忆（但有"模糊印象"——这是编剧留的伏笔口子）
- 创始村由艾力兽 (Elecmon) 守护——防止外来数码兽破坏数码蛋

**→ 映射到项目设计**：
- 🔧 **需新增** `world/rebirth.py`：
  - 死亡 agent → 标记为 `DELETED` → 经过 `REBIRTH_COOLDOWN_TICKS` → 在创始村以 `digitama` 形态出现
  - 重生时保留部分记忆：`memory.retain_fragments()` — 只保留 importance >= 8 的记忆
  - 新数码兽的 `species` 可以由前世进化路线决定（顺着进化树回退一级）或随机

### 4.4 数码世界的时空规则

- **时间流速差**：数码世界时间远快于现实世界。太一回到东京发现"几乎没时间流逝"
- **世界分层**：数码世界由多层/多服务器构成——文件岛→服务器大陆→文件夹大陆→WWW大陆→神之森林→网络海洋→黑暗区域→核心 (Kernel/Yggdrasill)
- **数字之门 (Digital Gate)**：连接数码世界与现实世界的通道

**→ 映射到项目设计**：
- 🔧 **无需在代码中实现时间差**，但可以在文档/narrative 中采用此设定解释世界演化速度
- 🔧 **需新增** `world/layers.py`：世界分层模型，为后续 "服务器大陆" 和 "黑暗区域" 扩展打基础

---

## 5. 复刻清单总结

| 优先级 | 功能模块 | 文件 | 内容 | 原作参考度 |
|--------|----------|------|------|-----------|
| 🔴 P0 | 进化树完善 | `digimon_agent.py` + 新 `evolution.py` | 补充 Ultimate/Digitama 阶段、暗黑进化、跃迁进化 | ⭐⭐⭐⭐⭐ |
| 🔴 P0 | 属性克制 | `battle/type_advantage.py` | Vaccine→Virus→Data→Vaccine 克制计算 | ⭐⭐⭐⭐ |
| 🔴 P0 | 文件岛子区域 | `world_state.py` + 新 `world/biomes.py` | 14 个子区域的完整拓扑 + 气候资源 | ⭐⭐⭐⭐⭐ |
| 🟡 P1 | 创始村重生 | 新 `world/rebirth.py` + `world/primary_village.py` | 数码蛋轮回 + 繁荣度 | ⭐⭐⭐⭐⭐ |
| 🟡 P1 | 黑暗四天王事件 | `events.py` 扩展 | 4 个天王事件 + 启示录兽 | ⭐⭐⭐⭐⭐ |
| 🟡 P1 | 黑色齿轮 | 新 `world/dark_gears.py` | 感染/狂暴机制 | ⭐⭐⭐⭐ |
| 🟢 P2 | 徽章系统 | 新 `world/crests.py` | 8 枚徽章 × 品格匹配 | ⭐⭐⭐⭐⭐ |
| 🟢 P2 | 搭档绑定 | `digimon_agent.py` 扩展 | 训练师半绑定、bond 驱动进化 | ⭐⭐⭐⭐ |
| 🟢 P2 | 世界分层 | 新 `world/layers.py` | 文件岛→服务器大陆→黑暗区域 | ⭐⭐⭐ |

---

# 🔬 第二部分：arXiv / GitHub / 博客最新发现

## arXiv 最新论文

### 1. 【arXiv 2607.08768】UniClawBench: A Universal Benchmark for Proactive Agents on Real-World Tasks

**核心**: LLM agent 的主动性 (proactive) 基准测试——agent 不只是响应指令，而是主动发现任务并执行。

**对数码宝贝世界的影响** ⭐⭐⭐⭐:
- 我们的 agent 目前是纯粹的"反应式"循环 (Observe→Plan→Act)，没有"主动找事做"
- **建议**: 给 `DigimonAgent` 增加 `_proactive_goal_generation()` — 在反思阶段，agent 不只是总结过去，还可以主动生成一个新目标（如"我想去探索未去过的区域"），注入到 `plan_next()` 中
- 这正好与"数码兽自主冒险"的 IP 精神吻合

### 2. 【arXiv 2606.08367】Emergence World: A Platform for Evaluating Long-Horizon Multi-Agent Autonomy

**核心**: 衡量"涌现"不是几小时的任务——需要**数周的长时间运行**。论文提出了一个长时间多智能体自治评估平台，监控 agent 在几周到几个月内的行为漂移、目标演化和社会结构固化。

**对数码宝贝世界的影响** ⭐⭐⭐⭐⭐:
- 这正是我们需要的！我们的 scheduler 目前以 tick 为单位，但缺乏"长周期"涌现监控
- **建议**: 在 `world_state.py` 增加 `WorldLongitudinalMetrics`：
  - 社交网络直径 (social_network_diameter): 随时间变化
  - 记忆一致性 (memory_coherence): agent 在不同时间对同一事件的记忆是否自洽
  - 目标漂移率 (goal_drift_rate): agent 的隐性欲望变化速度
  - 世界新奇度 (world_novelty): 单位时间内新事件的数量
- 这直接对接导演面板的"涌现健康度"仪表盘

### 3. 【arXiv 2606.26883】EconSimulacra: A Digital Twin Platform of Socio-Economic Systems Powered by LLM Agents

**核心**: LLM agent 的经济行为模拟——agent 会根据经济条件改变移动模式、社交互动和消费行为。经济与社交**双重闭环**。

**对数码宝贝世界的影响** ⭐⭐⭐:
- 我们的 `economy.py` 已有物品/货币系统，但 agent 行为不受经济状况影响
- **建议**: 当 agent 持有货币低于阈值 → 更倾向去奥加兽商店附近探索；当饥饿度高 → 更倾向去食物丰富区域
- 这其实已经在 `needs.py` 框架中，可以强化经济→行为的中介

### 4. 【arXiv 2606.31038】LLM-Driven Personalities for Decision Making in Emergency Simulations

**核心**: 在紧急情况模拟中使用 LLM 驱动的人格做决策。验证了个性特征对 agent 危机行为的显著影响。

**对数码宝贝世界的影响** ⭐⭐⭐:
- 我们的 `PersonalityTrait` 和 `personality_traits` 已有，但只在 planner prompt 中使用
- **建议**: 在 battle/disaster 事件中，personality 影响决策权重——如 `BRAVE` 的 agent 面对威胁时选择"战斗"的概率+30%，`TIMID` 的选择"逃跑"概率+40%

### 5. 【arXiv 2607.03220】CONTRA: Red-Teaming Configurations of Personalizable Agents

**核心**: 对可个性化 agent 的红队测试——agent 个性化配置可能被利用或产生意外行为。

**对数码宝贝世界的影响** ⭐⭐:
- 我们的导演面板本质上是"agent 配置注入"——这个论文提醒我们要考虑边界检查
- **建议**: `DirectorAPI.inject_event()` 和 `/api/director/override` 加参数校验白名单和时间窗口限制

---

## GitHub 趋势项目

### 1. ⭐5,130 FunyWolf/Viper — AI 驱动的攻击模拟/红队平台

**关联度**: ⭐⭐ 低(安全方向)，但它的"agent 自主决策+反馈循环"架构值得参考

### 2. ⭐1,200 agent-topia/evolving_personality — 基于 MBTI 的 LLM Agent 人格演化框架

**核心**: LLM agent 的 MBTI 人格不是静态标签，而是**随时间动态演化**——agent 的经历会改变其人格特质。

**对数码宝贝世界的影响** ⭐⭐⭐⭐⭐:
- 这是我们 `personality_traits` 目前最大的缺失：**人格是静态的**（初始化时随机生成后不再改变）
- **建议**: 接入人格演化：
  - 经常战斗 → `BRAVE`↑, `TIMID`↓
  - 经常社交 → `GENTLE`↑, `AGGRESSIVE`↓
  - 多次逃跑 → `TIMID`↑, `BRAVE`↓
  - 探索新区域 → `CURIOUS`↑
  - 长时间静止 → `LAZY`↑
- 这是 Phase 6 的"情绪演化"的自然延伸——情绪是短期的，人格是长期的

### 3. ⭐862 AIScientists-Dev/WorldSeed — "More is Different" 多智能体世界引擎

**关联度**: ⭐⭐⭐⭐ 高（我们已在竞品对标中追踪）。WorldSeed 的核心哲学是：agent 竞争+合作混合，不做显式规则约束。最新进展：加入了"派系领地争夺"机制。

**建议**: 借鉴其派系领地机制——我们已有 `faction` 系统，可以增加"领地标记 (Territory Marking)"：派系成员在频繁活动的区域留下"领地印记"，触发其他派系 agent 的回避或冲突行为。

### 4. ⭐1,118 tsinghua-fib-lab/AgentSociety — 清华的社会科学 agent 模拟平台

**核心**: 专门为社会科学实验设计的 LLM-native agent 模拟平台。支持大规模 agent（1000+）的社会行为实验。

**建议**: 参考其"社会实验配置"设计——我们的规则实验室可以借鉴其 DSL 定义方式，让导演（未来可能的玩家）用简单配置定义"如果 X 则触发 Y"的社会实验。

---

## 技术博客/社区动向

### 1. LLM Agent 记忆的主流方向

**趋势**: 2026 Q2 的主流方案从"全量记忆存储"转向"混合记忆"：
- **短期记忆**：最近 N 个事件（滑动窗口）
- **长期记忆**：经过反思压缩的摘要（summarization-based）
- **检索记忆**：基于向量相似度的语义检索（retrieval-augmented）
- **程序记忆**：可复用的行为模式/技能（procedural memory）

我们的 `MemoryStream` 目前偏向"全量存储 + 重要性过滤"，需要向"混合记忆"演进。

### 2. 涌现世界的评估指标共识

社区正在形成指标体系共识：
1. **社交网络熵 (Social Entropy)**: 关系分布的均匀程度
2. **行为多样性 (Action Diversity)**: 单位时间不同行为类型的数量
3. **叙事链长度 (Narrative Chain Length)**: 因果相关事件的最大链条长度
4. **世界可预测性 (World Predictability)**: 用过去 N tick 预测未来 M tick 的误差

---

# 🎯 第三部分：对 Phase 6/7 的影响和调整建议

## 立即行动（本周）

1. **P0: EvolutionStage 枚举修复** — 补充 ULTIMATE/DIGITAMA，修复中文注释错误（ROOKIE 误标为"成熟期"→应为"成长期"）
2. **P0: 文件岛子区域拓扑** — `world_state.py` 增加 14 个子区域定义，为生态模拟打基础
3. **P0: 属性克制计算** — 新增 `battle/type_advantage.py`，接入现有的 `DigimonAttribute`

## Phase 6 调整（情绪演化/关系向量化正在做）

4. **人格动态演化** — 基于 `evolving_personality` 论文，实现 personality_traits 的缓慢漂移（每 50 tick 微调一次）
5. **暗黑进化** — 在 `evolution.py` 中实现：当 anger > 0.8 且强行进化 → SkullGreymon 路线
6. **创始村重生** — `rebirth.py` 作为 Phase 6 的新模块，让世界有"生命循环"
7. **长时间涌现指标** — 接入 Emergence World 论文的 longitudinal metrics

## Phase 7 储备（地标/事件深化）

8. **黑暗四天王事件线** — 新增 4+1 个剧情事件（Devimon→四天王→启示录兽），让世界有"主线"
9. **黑色齿轮机制** — 感染系统，作为"世界灾难"的一种类型（已有 `disasters.py` 框架）
10. **徽章系统** — 8 枚徽章 × 品格匹配，驱动高级进化，这是 IP 核心
11. **世界分层** — 为"服务器大陆"和"黑暗区域"扩展做准备

---

### 🏆 竞品对标更新

| 项目 | Stars | 新增洞察 |
|------|-------|----------|
| evolving_personality | 1,200 | ⭐⭐⭐⭐⭐ 人格演化是 Phase 6 最佳增量——我们已有 personality_traits，只需加 drift 逻辑 |
| AgentSociety (清华) | 1,118 | 社会科学实验配置可借鉴 DSL 设计 |
| WorldSeed | 862 | 领地争夺机制——可与我们的 faction 系统融合 |

---

### 🔮 明天调研方向
- 数码兽具体进化谱系库（如亚古兽→暴龙兽→机械暴龙兽→战斗暴龙兽的完整参数）
- ChatDev / MetaGPT 等 agent 协作框架的最新进展（为"数码兽组队冒险"设计参考）
- PixiJS 地图渲染方案（文件岛完整地图的 2D 瓦片方案 vs canvas 绘制）
