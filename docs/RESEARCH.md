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
