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
