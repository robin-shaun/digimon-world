
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
