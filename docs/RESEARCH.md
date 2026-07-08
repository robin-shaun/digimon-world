# 📚 调研笔记 / Research Notes

> 长期积累,每个调研都有日期和结论。

---

## 2026-07-07 · Stanford Generative Agents

**参考仓库**: `github.com/joonspk-research/generative_agents`

**论文**: Park et al., "Generative Agents: Interactive Simulacra of Human Behavior" (2023)

**核心结构**:
- `reverie/backend_server/persona/persona.py` — 核心 agent 类
- 25 个 agent 在 Smallville 小镇自主生活
- 三件套:
  - **Memory Stream**: 时间戳记忆,带重要性评分
  - **Reflection**: 当累计记忆达阈值,LLM 生成高级抽象
  - **Planning**: 高层计划 → 子计划 → 行动

**可借鉴的精华**:
- 记忆检索: 3 维评分 (近因性 0.3 + 重要性 0.4 + 关联性 0.3)
- 反思触发: 重要性累积和 > 阈值
- 反思树: 反思本身也存记忆,成为新记忆的一部分

**对本项目的影响**:
- 数码兽 agent 复用这三件套
- "反思"对数码兽尤其重要 —— 它们需要"顿悟"才能进化

---

## 2026-07-07 · 数码宝贝动画世界观

**原作**: 数码宝贝大冒险 (Digimon Adventure, 1999) + 后续系列

**核心元素**:
- **被选召的孩子** (Chosen Children): 现实世界的 8 个孩子
- **神圣计划** (Digivice): 装备,负责触发进化
- **徽章** (Crest): 勇气 / 友情 / 爱心 / 知识 / 诚实 / 纯真 / 希望 / 光明
- **进化**: 数码兽可以通过羁绊"超进化"到下一阶段
- **黑暗四大天王** (Dark Four Heavenly Kings): 主要反派

**对本项目的影响**:
- 用户先以"观察者"身份进入,暂不扮演被选召的孩子
- 数码兽依然有完整的进化体系,但触发由 LLM 评估"剧情张力"
- 徽章系统预留接口(可让用户给某只数码兽"赋能")

---

## 2026-07-07 · LLM Agent 最新进展

**待调研** (持续更新):
- LangGraph: 有状态 agent 编排,适合多步骤
- MCP (Model Context Protocol): 工具调用标准化
- ReAct 变体: Plan-and-Execute / Reflexion
- 长期记忆压缩技术

(此节会随项目推进持续补充)

---

## 调研方法

每次大决策前:
1. 看论文 / 仓库 README
2. 复制核心代码片段,本地跑通
3. 写心得到本文件
4. 在 DESIGN.md 中标注参考来源

---

## 2026-07-08 · 每日调研(补: 08:30 cron ticker 异常,手动补)

**调研方式**: Semantic Scholar API 查 Stanford Generative Agents (arXiv 2304.03442) 的 2026 年最新引用

**注意**: arXiv API 在本沙箱不可达(超时 30s),所以只走了 Semantic Scholar。下一轮 cron 若恢复正常,会补充 arXiv 原始数据。

### 今日发现 — 2026 年新引用 Stanford Generative Agents 的论文(10 篇)

1. **VirtualCompanySim** (SoftwareX, 2026) — 多 agent 关怀场景, 解释性人格参数化
   - 借鉴点: "explainable personality parameterization" 对数码兽的"性格 → 行为"映射很有用, 我们 DigimonAgent 应该有可解释的性格向量
2. **FLAIR** (Transportation Research Part C, 2026) — LLM-integrated 多层框架, 细粒度活动类型
   - 借鉴点: "多层" 概念 — 我们 Phase 2 的 agent 循环 (Observe/Memory/Reflect/Plan/Act) 已经是 5 层, 可以更细致
3. **Generating Realistic Human Mobility Data with Hybrid LLM Agent** (KDD 2026) — 混合 LLM agent 生成真实人类移动
   - 借鉴点: 移动模式生成 — Phase 1 我们的亚古兽是"脚本移动", Phase 2+ 应该 LLM 决策移动
4. **LLMs as Research Instruments for Problems in Engineering Management** (J. Management in Eng., 2026) — LLM 作为研究工具
   - 借鉴点: 不直接相关
5. **LLM-CECM** (Renewable Energy, 2026) — 战略生成行为仿真
   - 借鉴点: 战略决策 — 数码兽战斗 AI 可以借鉴
6. **Coordination of LLM-Embodied Agents for manufacturing task allocation** (J. Manufacturing Systems, 2026) — 制造任务分配的多 agent 协调
   - 借鉴点: 任务分配机制 — Phase 4 多 agent 涌现的核心
7. **People shift political expression in small online group chats** (CHB 2026) — 小群体对话的政治表达
   - 借鉴点: 小群体动态 — 我们的数码兽也是小组(被选召的孩子 + 几只)
8. **Narrative and dialogue generation for video-games** (EAAI 2026) — 系统映射
   - 借鉴点: 视频游戏剧情生成综述 — 数码世界就是"游戏 + 涌现"
9. **Knowledge is power? The impact of agent knowledge on persuasion** (CHB 2026) — 知识对说服力的影响
   - 借鉴点: 数码兽"知识" (记忆) 越多, 说服/战斗越强
10. **SovereignPA-Bench** (2026) — 用户拥有的个人 agent 评估
    - 借鉴点: 评测方法 — 我们 Phase 4 评估"世界活没活"需要量化指标

### GitHub Trending (本日)
- arXiv sandbox 限制导致无法深入搜索, 跳过 GitHub Trending 详细调研
- 但已知继续在 Phase 1-2 推进的后端代码 (llm/client.py) 是核心基础, 暂时不需要新依赖

### 与本项目对接(对 Phase 2 的影响)
- **Phase 2 重点**: 性格参数化 (VirtualCompanySim) + LLM 决策移动 (Mobility)
- **Phase 3 战斗 AI**: 借鉴 LLM-CECM 的战略决策思路
- **Phase 4 涌现**: Coordination 论文的任务分配机制直接可用

### 建议调整
- 立刻: 不调整, 继续 Phase 1 → Phase 2
- 中期 (Phase 2 末): 加 DigimonAgent 的"性格向量" 字段 (向 VirtualCompanySim 学习)
- 长期 (Phase 4): 用 SovereignPA-Bench 的评估方法做世界"活力指数"

### 明日调研方向
- 调研 LangGraph (设计文档已提到, 还没深入)
- 调研 MCP (Model Context Protocol) — 我们的 agent 需要工具调用
- 调研最新 "agent simulation" GitHub 项目 (找优质仓库, 上次 GitHub Trending 没找到)

### 调研工具问题(技术债)
- arXiv API 在 Hermes 沙箱里访问超时(30s)
- 需要找到替代: 1) 缓存 arXiv 数据; 2) 改用 HuggingFace papers API; 3) 用 web 工具打开 arxiv.org
- 下次 cron 触发时尝试 1) + 3)

---

## 2026-07-08 · 每日调研 (11:00 cron ticker)

**调研方式**: 直接抓 arXiv HTML 列表页 + GitHub Trending HTML + Lilian Weng 博客 + HN Algolia API
**修正昨日**: arXiv HTML 列表可达,只是 API 超时。已能从列表直接解析标题/作者。

### 今日发现 — arXiv cs.MA + cs.AI 2026 顶级相关论文

筛选标准: 与"涌现 / 记忆 / LLM-agent / 多智能体社交"直接相关。三篇:

1. **arXiv:2601.06490 · Bi-Mem: Bidirectional Construction of Hierarchical Memory for Personalized LLMs via Inductive-Reflective Agents**
   - 作者: Wenyu Mao 等 (2026-01-10)
   - 核心: **双向构建层级记忆** — Inductive Agent 自底向上聚类事实→场景→人格; Reflective Agent 自顶向下用全局人格修正局部场景。提出 **spreading activation 联想检索**(事实激活场景,场景反哺事实)
   - 对本项目: ⭐⭐⭐⭐⭐ 与我们 Phase 2 `MemoryStream` + `Reflector` **完全同构**。Stanford 2023 的反思是单向(局部→全局),Bi-Mem 加了反向校验。我们 Phase 2/3 应该参考这套**双向校验 + 联想检索**,避免反思幻觉。

2. **arXiv:2601.05606 · Conformity Dynamics in LLM Multi-Agent Systems: Topology and Self-Social Weighting**
   - 作者: Chen Han 等 (2026-01-09)
   - 核心: **从众动力学** — 中心化结构对 hub 能力敏感、有同模型对齐偏差;分布式结构更鲁棒,但过度连通会触发"wrong-but-sure cascade"(自信地错)。提出 confidence-normalized pooling rule 调自我/社会权重
   - 对本项目: ⭐⭐⭐⭐⭐ Phase 4 多 agent 涌现的**反脆弱性设计**。我们不能默认让数码兽之间全连接(都互相看得见),要设计**拓扑结构** + **自我权重**,避免整个世界被一只"网红数码兽"带偏。

3. **arXiv:2601.08129 · Emergent Coordination via Pressure Fields and Temporal Decay**
   - 作者: Roland Rodriguez 等 (2026-01-13)
   - 核心: **拒斥层级编排** — 主张 agent 不靠 planner/manager 协调,而是靠**共享工件上的压力梯度** + **时间衰减**。1350 次实验: pressure-field 48.5% 解题率 vs 对话式 12.6% vs 层级式 1.5%。时序衰减是关键(去掉降 10pp)
   - 对本项目: ⭐⭐⭐⭐ 数码世界的"区域热度"是天然的 pressure field(数码兽聚集→资源紧张→压力上升→迁移)。比硬编码"派系规则"更涌现。但要小心 — 我们的反思/规划还是要 LLM,**两者结合**:LLM 做个体决策,pressure field 做全局涌现。

### 额外扫到的值得后续关注的(收藏)
- 2601.03328 · **LLM-Enabled Multi-Agent Systems: Empirical Evaluation** (Renney et al., AAMAS 2026) — 实际案例研究,三周出 prototype,一月可生产,跟我们 Phase 1 时间表对得上
- 2601.09742 · **Adaptive Orchestration: Scalable Self-Evolving Multi-Agent Systems** — Phase 4 规模化的备选架构
- 2601.00121 · **Digital Twin AI: From LLMs to World Models** (cs.AI, 2601.01321) — 数字孪生框架综述,跟我们"世界模型"思路相关

### GitHub Trending (今日, Python Daily)

| 仓库 | 简述 | 借鉴点 |
|------|------|--------|
| **HKUDS/AI-Trader** | 100% 全自动代理交易,多 agent 决策。20.6k★ | **与我们最相关**: 同样是多 agent 在世界里自主决策。可以看它怎么设计**多个 LLM agent 长期持仓 + 互相博弈**(Phase 4 涌现) |
| **NousResearch/hermes-agent** | Hermes Agent 本体。685★/日 | 我们正在跑的就是它,可以看它的 release notes / 新技能,留意有没有"agent 记忆压缩"或"长会话调度"新能力 |
| **anthropics/claude-plugins-official** | Anthropic 官方插件目录。86★/日 | 中长期关注,我们后期给 agent 装工具(观察世界 / 战斗 / 移动)可能用得上 |

不推荐的(repo 看起来热度但跟我们无关): claude-video / pocket-tts / claude-skills 集合(资源站) / Ghost-Downloader / openmed(医疗)。

### 技术博客 — 1 篇高价值

**Lilian Weng · Harness Engineering for Self-Improvement (2026-07-04)**
链接: https://lilianweng.github.io/posts/2026-07-04-harness/
- 核心: "**harness**"(包裹 base model 的系统层,负责编排执行 + 决定模型如何思考)比模型本体同样重要
- 三个设计模式:
  1. Workflow Automation(我们已有:DigimonAgent 主循环)
  2. **File System as Persistent Memory**(⭐⭐⭐ — 我们 MemoryStream 现在是内存,Phase 4 应该考虑文件/对象存储做长程记忆)
  3. Sub-agent and Backend Jobs(Phase 4 多个数码兽并行时的子代理调度)
- 关键命题: "模型权重 vs harness 层,应该共同优化" — 对应到我们:**好的 LLM 不如好的 harness**,我们花时间在 `MemoryStream` / `Reflector` / `Planner` 上比换个更强模型收益更高

### 数码宝贝原作资料(本周已覆盖,跳过)

无新发现。已记录的"被选召的孩子 / 神圣计划 / 徽章 / 进化"够 Phase 2-3 用。Phase 4"黑暗四大天王出现"待 Phase 3 末再深挖。

### 与本项目对接(对 Phase 2 的影响)

- **立刻加入 Phase 2 backlog**:
  - `Reflector` 加**双向校验**: 反思不只自底向上生成,也要用全局人格(性格向量)反向修正局部抽象,避免"反思幻觉"。(Bi-Mem)
  - MemoryStream 加**联想检索**: 事实可激活场景,场景可反哺事实检索。(Bi-Mem)
- **Phase 4 设计原则**:
  - 不要"全连接"社交图,设计**拓扑** + **自我/社会权重**避免从众级联。(Conformity)
  - "区域热度/资源稀缺"做成 pressure field 引导涌现,而不是硬编码派系规则。(Pressure Fields)
  - 长期记忆逐步从内存迁到文件/对象存储(File System as Memory)
- **Phase 2 收益最高的调整**: 把 harness 思路写在 DESIGN.md — 我们已经做的 Observe→Memory→Reflect→Plan→Act 就是 harness 的实例化,只是没在文档里点明

### 建议调整

- 立刻: **不调整代码**,等 Phase 2 当前 PR(MemoryStream + Reflector + Planner 4+5 测试)收尾
- 短期(本周): 把"Bi-Mem 双向校验 + 联想检索"加到 `DESIGN.md` 作为 MemoryStream v2 设计目标
- 中期(Phase 4 启动前): 写一份 `DESIGN-EMERGENCE.md`,明确**拓扑 + 自我权重 + pressure field** 三个涌现机制的设计
- 长期: harness 思路系统化,把我们目前散在各处(MemoryStream / Reflector / Planner / 主循环)的"包裹层"在文档里画清楚

### 明日调研方向
1. **LangGraph** — 用户决策清单里的旧账,Phase 2 决定要不要引入前先把它吃透
2. **MCP (Model Context Protocol)** — 我们 agent 工具调用迟早要标准化
3. 找一篇 "agent evaluation / world liveness" 的具体方法论(Phase 4 评估用)
4. 试一下 HuggingFace papers API,看是否比 Semantic Scholar 稳

### 调研工具问题(技术债更新)
- ✅ arXiv **HTML 列表页**可达 → 已用 `/list/cs.MA/2026` 直接解析
- ❌ arXiv API 仍超时 → 继续用 HTML 绕过
- ❌ Semantic Scholar → 今日 429 限速 → 暂时跳过,等 key
- ✅ GitHub Trending HTML 可达,但要自定义 parser(没官方 API)
- ✅ HN Algolia API 可达 → 备用的"博客/讨论"来源
