# 🗓️ 路线图 / Roadmap

> 详细分阶段任务列表。Phase 0+1+2 已完成,正在进入 Phase 3 (数码兽进化 + 战斗)。

## Phase 0: 技术调研 + 项目骨架 ✅ (本阶段)

**目标**: 弄清技术选型,把骨架立起来,把仓库推到 Gitee。

- [x] 调研 Stanford Generative Agents 仓库结构
- [x] 调研数码宝贝动画世界观
- [x] 确认技术栈(Python + FastAPI + PixiJS + SQLite)
- [x] 写设计文档 (DESIGN.md)
- [x] 写项目骨架(目录、README、pyproject)
- [ ] 推到 Gitee (等用户提供认证)
- [ ] 写调研笔记 (RESEARCH.md)

**完成标志**: Gitee 仓库有可运行骨架,DESIGN.md 通过 review。

---

## Phase 1: 网页地图雏形 + 数码兽在地图上移动

**目标**: 在浏览器里看到一个 2D 插画风的地图,有数码兽(暂时是脚本控制)在上面走来走去。

- [x] 前端: 加载 2D 插画地图(文件岛,代码生成 + POI 标签) ✅
- [x] 前端: 数码兽 sprite 在地图上移动(脚本驱动亚古兽随机走动) ✅
- [x] 后端: FastAPI,`/api/digimon` / `/api/digimon/{name}` / `/api/digimon/{name}/position` / `/api/digimon/{name}/move` ✅
- [x] 后端: 内存中的 `WorldState`(含 2 个地区 / 3 只数码兽 / 4 个 POI) ✅
- [x] WebSocket: `/ws/world` 端点 + 1Hz 位置广播(占位) ✅
- [x] 测试: 25 个 pytest 全通过(API + world_state + smoke) ✅
- [x] 前端: 鼠标点击数码兽 → 侧栏显示详情 + "戳一下"按钮 ✅
- [x] 前端: WebSocket 客户端(自动重连 + HTTP 降级轮询) ✅

**完成标志**: 浏览器看到一个会动的数码世界,后端 API 全跑通。

---

## Phase 2: Agent 自主行为循环

**目标**: 数码兽不再由脚本控制,而是 LLM 自主决策"接下来去哪、做什么"。

- [x] 实现 `MemoryStream`: 写入、重要性评分、检索 ✅
- [x] 实现 `Reflector`: 阈值触发反思,生成高级抽象 ✅
- [x] 实现 `Planner`: 计划生成 (LLM-driven,Fallback 兜底) ✅
- [x] 实现 `DigimonAgent` 主循环 (Observe → Memory → Reflect → Plan → Act) ✅
- [x] LLM 客户端: 中转 API 调用,模型分层 (opus/haiku) ✅
- [x] WorldClock + WorldScheduler: 周期驱动 agent.step() ✅
- [x] 单 agent 单元测试: 88+ 个 pytest 全通过(act/step/planner/reflector/memory/scheduler/api/world_state/smoke/llm_client) ✅
- [x] 多 agent 简单互动: 两只数码兽相遇→对话 ✅
- [x] 把 scheduler 接入 FastAPI startup,真正让世界跑起来 ✅
- [x] 端到端: 跑 1 天世界时间,检查 agent 记忆 / 反思 / 计划可读 ✅ (脚本: `backend/scripts/verify_phase2.py`)

**完成标志**: 一个数码兽能在文件岛上自主生活一天,有日志可看。

**验证方法**:

    cd backend && source .venv/bin/activate
    python scripts/verify_phase2.py            # 默认 24 tick,15/15 PASS
    python -m pytest tests/test_verify_phase2.py  # CI 兜底测试

输出包含:
- ✅ 15 项校验全过(时钟推进 / 移动 / 记忆 / plan / dialogue 等)
- 🐾 每只数码兽的"一天生活报告"(位置 / 记忆数 / 当前计划 / 最近 3 条记忆)
- 🌍 最近 5 条世界事件
- 💬 主动触发 proximity 后的对话样本

---

## Phase 3: 数码兽进化 + 战斗 (85%)

**目标**: 进化系统跑通,战斗系统能跑完一回合。

- [x] 实现 `BattleSystem`: 回合制框架 ✅
- [x] 战斗 AI: LLM 决策 ✅
- [x] 属性克制计算 ✅
- [x] 实现 `EvolutionSystem`: 5 阶段进化链 ✅
- [x] 进化触发条件: 战斗胜利 / 羁绊值 / 剧情事件 ✅
- [x] 战斗观察者视角 ✅ (`/api/battle/recent` + `/api/battle/start` + `/api/digimon/{name}/battle_victories`)
- [ ] 进化 UI: 进化时全屏动画(占位) ⏳

**完成标志**: 数码兽可以进化,可以打一架。

---

## Phase 4: 多智能体社交 / 剧情涌现

**目标**: 世界真正"活"起来。

- [x] 多 agent 社交网络 (`relationships.py`) ✅
- [x] 派系 / 敌对 / 结盟 (`factions.py`) ✅
- [x] 剧情事件 (`events.py`) ✅
- [x] 观察者导演面板 (前端 sidebar: 关系图 + 派系 + 事件 + 速度/注入) ✅
- [x] 时间快进 60x 验证涌现 ✅ (脚本: `backend/scripts/verify_emergence.py`)
- [x] 持久化: 世界状态可保存/加载 (SQLite) ✅
- [x] 世界日志页 — 事件表格 + 关系变化实时显示 ✅
- [ ] 长期一致性测试(跑一周世界时间)

**完成标志**: 放 7 天,世界自己生出了可看的故事。

---

## Phase 5: 世界深度 + 玩家体验 (50%)

**目标**: 让世界更有深度和可玩性,增加玩家互动系统。

已完成:
- [x] 数码兽技能系统 — 技能学习/升级/释放 ✅
- [x] 饥饿+觅食系统 — 需求驱动行为 ✅
- [x] 季节系统 + 多世界实例 ✅
- [x] 数码兽繁衍系统 — 关系>80 × 500ticks × 25%概率产蛋 ✅
- [x] 隐性欲望系统 — 基于深度调研的涌现目标 ✅
- [x] 叙事一致性监控 — NarrativeMonitor ✅
- [x] 天气+日夜系统 — SUNNY/RAINY/STORMY/FOGGY ✅
- [x] 徽章系统 — 勇气/友情/爱心/知识/希望/光明 ✅
- [x] 数码兽日记系统 — 每日记忆浓缩 ✅
- [x] 记忆压缩系统 — 防 MemoryStream 无限增长 ✅
- [x] 数码兽个性化 — 性格特征影响决策 ✅
- [x] 地标探索系统 — 9测试通过 ✅
- [x] 数码兽图鉴系统 — 8只初始数据+API+前端 ✅
- [x] 道具掉落系统 — heal/buff/进化石 ✅
- [x] 排行榜 — 战斗/羁绊/徽章 Top ✅
- [x] 切磋系统 — 友好对战 ✅
- [x] 前端: 通知弹出 — 战斗/进化/剧情 3秒渐隐 ✅
- [x] 前端: 顶部导航栏 — 主页/战斗/进化/日志 ✅
- [x] 前端: 战斗模拟页 — 选角/回合日志/HP条/技能 ✅
- [x] 前端: 进化图鉴页 — 完整进化链+技能 ✅
- [x] 依赖图分析工具 — 发现循环依赖 ✅

待做:
- [ ] 成就系统 (开发中) ⏳
- [ ] 用户进入世界(被选召的孩子模式)
- [ ] 跨世界实例联动
- [ ] 模因传播、技能文化
- [ ] 多模态: 数码兽有专属配音、动画
- [ ] 移动端 H5 版本

---

## 📊 当前进度

```
[████████░░░░░░░░░░░░░░]  35%  Phase 0
[████████████████████] 100%  Phase 1 ✅ 完成
[████████████████████] 100%  Phase 2 ✅ 完成 (verify_phase2.py 15/15 PASS)
[█████████████████░░░]  85%  Phase 3 (仅剩进化 UI 全屏动画)
[██████████████████░░]  90%  Phase 4 (社交/派系/事件/导演面板/涌现测试/持久化/世界日志 ✅, 剩长期一致性测试)
[██████████░░░░░░░░░░]  50%  Phase 5 (20+ 功能已完成, 成就系统开发中)
```
