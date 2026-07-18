# 🗓️ 路线图 / Roadmap

> 详细分阶段任务列表。Phases 0-10 已完成, Phase 11 进行中 (规模化 + 涌现指标)。

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

## Phase 3: 数码兽进化 + 战斗 ✅ (100%)

**目标**: 进化系统跑通,战斗系统能跑完一回合。

- [x] 实现 `BattleSystem`: 回合制框架 ✅
- [x] 战斗 AI: LLM 决策 ✅
- [x] 属性克制计算 ✅
- [x] 实现 `EvolutionSystem`: 5 阶段进化链 ✅
- [x] 进化触发条件: 战斗胜利 / 羁绊值 / 剧情事件 ✅
- [x] 战斗观察者视角 ✅ (`/api/battle/recent` + `/api/battle/start` + `/api/digimon/{name}/battle_victories`)
- [x] 进化 UI: 进化时全屏动画 (多阶段: 闪白入场→扫描线+粒子→图标脉冲+飞升粒子) ✅

**完成标志**: 数码兽可以进化,可以打一架。 ✅

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

## Phase 5: 世界深度 + 玩家体验 ✅ (100%)

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
- [x] 成就系统 — 10 种里程碑(社交/战斗/进化/寿命/探索/繁衍) ✅
- [x] 用户进入世界(被选召的孩子模式) → 迁移至 Phase 12-① ✅
- [x] 跨世界实例联动 → 迁移至 Phase 12-② ✅
- [x] 模因传播、技能文化 → 迁移至 Phase 12-③ ✅
- [x] 多模态: 数码兽有专属配音、动画 → 迁移至 Phase 13-①(TTS)+②(动画) ✅
- [x] 移动端 H5 版本 → 迁移至 Phase 12-④ ✅

---

## Phase 6: CPM情绪演化 + 关系向量化 ✅ (100%)

**目标**: 情绪动态演化 + 4D关系向量 + 排行榜 + 显著性阈值。

- [x] CPM情绪模型 — 情绪随事件推移动态变化 ✅
- [x] 关系4D向量 — 信任/尊重/亲密/敌对 ✅
- [x] Leaderboard — 战斗/羁绊/徽章排行 ✅
- [x] 显著性阈值 — 事件重要性自动筛选 ✅

**完成标志**: 情绪和关系有了科学可量化的模型。 ✅

---

## Phase 7: 记忆压缩 + 因果链 ✅ (100%)

**目标**: 压缩长期记忆,记录因果链,监控世界活力。

- [x] 记忆压缩 — 旧记忆自动归并摘要,防无限增长 ✅
- [x] 因果链日志 — 事件因果关系追踪 ✅
- [x] 世界活力指标 — vitality.py (多样性/稳定性/涌现度) ✅

**完成标志**: 记忆管理可扩展,因果可追溯,活力可监控。 ✅

---

## Phase 8: 数码宝贝原作深度复刻 ✅ (100%)

**目标**: 完整复刻数码宝贝大冒险世界 (P0-P1 research items × 4).

- [x] 文件岛 14 子区域拓扑 — 无限山/创始村/齿轮草原/玩具城... ✅
- [x] 黑暗齿轮感染系统 — 子区域感染+战斗清除 ✅
- [x] 黑色齿轮 scheduler 接入 + API 端点 ✅
- [x] 战斗系统集成 — 进化阶段倍率 + 齿轮摧毁 ✅

**完成标志**: 数码宝贝原作世界观在代码中完整复现。 ✅

---

## Phase 9: 多元宇宙 API ✅ (100%)

**目标**: 多世界副本 — 创建/管理/删除/注入数码兽。

- [x] Multiverse API — create / gate / list / stats 端点 ✅
- [x] 世界种子数码兽注入 ✅
- [x] 按世界 ID 过滤事件 ✅
- [x] 世界删除 + 事件清理 ✅
- [x] seasons_enabled 参数 + 单世界详情 ✅
- [x] 多元宇宙聚合统计 ✅

**完成标志**: 可以同时运行多个独立数码兽世界实例,聚合管理。 ✅

---

## Phase 10: 环境自主演化 ✅ (100%)

**目标**: 环境本身也会变化 — 昼夜+天气+生态+环境事件。

- [x] 昼夜循环 (daynight.py) ✅
- [x] 天气系统 (weather.py) ✅
- [x] 生态动力学 (ecology.py) ✅
- [x] 环境事件 (environmental_events.py) ✅

**完成标志**: 环境不再静态,数码兽需要适应动态世界。 ✅

---

## Phase 11: 规模化 + 涌现指标 ✅ (100%)

**目标**: Agent数量从3扩大到30+,加LLM批量调用优化,Canvas缩放适配,涌现指标API。

- [x] ① Agent 3→30+ — 新增病毒种/数据种/自由种数码兽 ✅
- [x] ② LLM批量调用 — 思考轮次+计划缓存+对话降频 ✅
- [x] ③ Canvas缩放适配 — 1200×800 + 密度模式 ✅
- [x] ④ 涌现指标API — /api/emergence 端点(社交网络/行为熵/情绪传染) ✅
- [x] ⑤ 涌现指标测试 — 44 tests ✅
- [x] ⑥ 涌现指标前端 — stats.html 嵌入涌现数据面板 (社交网络/行为多样性/情绪景观/涌现事件)
- [x] ⑦ 30-agent 长时间运行一致性验证 — verify_phase11.py + 3 CI tests ✅
- [x] ⑧ Agent 100+ 压力测试 — stress_test.py (100 agents × 10 ticks, 4.6ms/tick) + 3 CI tests ✅

**完成标志**: 30+ agents 稳定运行,涌现指标可视化,100+ agent 压力测试 8/8 PASS。 ✅

---

## 📊 当前进度

```
[████████████████████] 100%  Phase 0 ✅ 完成 (技术调研 + 骨架)
[████████████████████] 100%  Phase 1 ✅ 完成 (网页地图 + 数码兽移动)
[████████████████████] 100%  Phase 2 ✅ 完成 (Agent 自主行为循环, verify_phase2.py 15/15 PASS)
[████████████████████] 100%  Phase 3 ✅ 完成 (进化系统 + 战斗引擎)
[████████████████████] 100%  Phase 4 ✅ 完成 (多智能体社交/派系/导演面板, 长期一致性在 Phase 12 完成)
[████████████████████] 100%  Phase 5 ✅ 完成 (28/28: 全部功能+5项迁移至 Phase 12/13)
[████████████████████] 100%  Phase 6 ✅ 完成 (CPM情绪 + 4D向量 + leaderboard + 显著性)
[████████████████████] 100%  Phase 7 ✅ 完成 (记忆压缩 + 因果链 + 世界活力)
[████████████████████] 100%  Phase 8 ✅ 完成 (原作深度复刻: 14子区域 + 黑暗齿轮)
[████████████████████] 100%  Phase 9 ✅ 完成 (多元宇宙 API: 6 端点 + 世界管理)
[████████████████████] 100%  Phase 10 ✅ 完成 (环境自主演化: 昼夜+天气+生态+事件)
[████████████████████] 100%  Phase 11 ✅ 完成 (8/8: 100-agent 压力测试 4.6ms/tick, 530 tests)
[████████████████████] 100%  Phase 12 ✅ 完成 (5/5: 被选召的孩子+跨世界联动+模因传播+移动端适配+长期一致性测试)
|[████████████████████████] 100%  Phase 13 (多模态 + 生产加固) ①-⑧ ✅
|[████████████████████████] 100%  Phase 14 (世界叙事系统) ✅
|[████████████████████████] 100%  Phase 15 (导演面板增强) ✅
|[████████████████████████] 100%  Phase 16 (差序格局 + 情感传播) ✅
|||[████████████████████████] 100%  Phase 17 (人格深度系统 — 荣格心理学 MBTI 驱动) ✅
|||||[████████████████████████] 100%  Phase 18 (Agent 自主记忆规划) ✅
||||||[████████████████████████] 100%  Phase 19 (计划持久化与上下文管理) ✅
||||||||||[████████████████████████] 100%  Phase 20 (自演化世界模型) ✅
|[████████████████████████] 100%  Phase 21 (Agent 内省聚合仪表板) ✅
|[████████████████████████] 100%  Phase 22 (共享记忆惯例与文化涌现) ✅
|[████████████████████████] 100%  Phase 23 (思考成本与认知能量系统) ✅
|[████████████████████████] 100%  Phase 24 (能量经济与互惠利他) ✅
||[██████████████████░░░░░░]  50%  Phase 25 (Agent 上下文质量与可靠性工程) 🔄
```

---

## Phase 12: 跨世界联动 + 玩家融入 + 生产就绪
|
|**目标**: 受 GitHub trending 项目 `evolving_personality` (1,199⭐) 启发，基于荣格心理学 MBTI 四维度给每只数码兽赋予动态演化的人格。人格随战斗/社交/进化经历自然漂移，并深度影响对话风格、战斗策略、关系兼容性。
|
|**参考项目**: https://github.com/agent-topia/evolving_personality — 基于荣格心理学的 MBTI 人格动态演化框架
|
- [x] Task 1 — `personality_engine.py` 核心模块: MBTI 四维度 + 动态演化 + 人格兼容矩阵
- [x] Task 2 — API 端点 `/api/digimon/{name}/personality`: 返回人格档案（类型 + 各维度值 + 演化历史）
- [x] Task 3 — 人格集成到对话/战斗/规划: 性格影响决策风格和对话语气 ✅
- [x] Task 4 — 人格兼容性加成: RelationshipTracker 中 MBTI 兼容度额外加分
- [x] Task 5 — 前端人格雷达图: Canvas 绘制四维度雷达图 + 演化轨迹 ✅
|
|**完成标志**: 数码兽有可演化的 MBTI 人格，人格深度影响社交和战斗行为。 ✅
|
|---
|
## Phase 18: Agent 自主记忆规划

**目标**: Agent 对自己的记忆拥有真正的自主权 — LLM 自评重要性替代固定规则算法，记忆随时间自然遗忘（Ebbinghaus曲线），通过复述机制巩固重要记忆，并自动检测世界状态变化导致的过期记忆。

**论文依据**: arXiv:2606.27472 "Supersede" + arXiv:2605.30690 "ElasticMem"

- [x] Task 1 — `memory_autonomy.py` 核心模块: LLM 自评重要性 + Ebbinghaus 遗忘曲线 + 记忆复述 + 过期检测 ✅
- [x] Task 2 — 接入 DigimonAgent 主循环: agent.step() 中调用记忆自主评估 ✅
- [x] Task 3 — API 端点: `/api/digimon/{name}/memory-health` 记忆健康诊断 ✅
- [x] Task 4 — 前端记忆健康面板: 遗忘曲线可视化 (堆叠条形图+Ebbinghaus曲线) + 弱记忆列表 + 复述历史 ✅
- [x] Task 5a — 集成测试: 58 tests PASS ✅
- [x] Task 5b — 端到端验证: verify_phase18.py 脚本 ✅ (8项全部通过)

**完成标志**: 数码兽能自主评估记忆重要性，记忆有自然的遗忘-复述生命周期。 ✅
|
|---
|
|## Phase 12: 跨世界联动 + 玩家融入 + 生产就绪

**目标**: 多元宇宙世界可互通,用户以「被选召的孩子」身份进入世界,夯实长期稳定性。

- [x] ① 被选召的孩子 POC — ChosenChildAgent 类型,用户可创建角色进入世界 ✅
- [x] ② 跨世界实例联动 — 数码兽可在不同世界间迁移 (批量/自动迁移 + 18 tests) ✅
- [x] ③ 模因传播/技能文化 — agent 间知识传递 + 文化跟踪 ✅ (MemePool + 28 tests)
- [x] ④ 移动端 H5 适配 — 响应式布局 + 触控操作 ✅
- [x] ⑤ 长期一致性测试 — verify_phase12.py + 9 CI tests, 运行一周世界时间无 memory leak / state drift ✅

**完成标志**: 用户可创建被选召的孩子,穿梭于多元宇宙,移动端可玩,跑一周不崩。

---

## Phase 13: 多模态 + 生产加固

**目标**: 数码兽有专属语音/动画,世界更稳健,为长期运行做准备。

- [x] ① 数码兽 TTS 配音 — 每只数码兽有独特声线 (Edge TTS / Fish Audio) ✅ 后端 tts.py + /api/tts 端点 + 前端播放 + 12 tests
- [x] ② 进化/战斗动画增强 — sprite sheet 动画替换当前 CSS 动画 ✅ 动画引擎完整 (idle呼吸/平滑移动/行走弹跳±3°/拖尾残影/邻近连线/精灵色光环/随机相位/粒子特效/音效集成/键盘导航), 精灵数据 29 种已齐全, 集成测试 79 PASS; **待用户决策**: sprite 素材生成方案 (AI 管线 vs 手工绘制)
- [x] ③ 后端性能优化 — DB 索引(6个) + WAL mode + mmap + /api/health/perf 端点 ✅
- [x] ④ 前端性能优化 — Canvas 离屏缓存 (静态背景 blit) + 渐变对象复用 ✅
- [x] ⑤ 世界存档系统 — 定时快照 + 版本迁移 + 回滚 ✅
- [x] ⑥ 管理后台 — 世界管理/Agent 控制/日志查询 Web UI ✅
- [x] ⑦ 自动化部署增强 — CI (backend + lint + frontend-check) + 健康检查 + 冒烟测试 ✅
- [x] ⑧ Phase 5 多模态迁移 — 从 Phase 5 待办中迁移完成 ✅

**完成标志**: 用户能听到数码兽的声音,世界可长期无人值守运行。

---

## Phase 14: 世界叙事系统 ✅ (100%)

**目标**: LLM 驱动的世界叙事生成 — 自动产出故事，前端实时展示。

- [x] Task 1 — NarratorSystem 骨架 + 单例模式 ✅
- [x] Task 2 — _collect_context 事件收集 + 上下文构建测试 ✅
- [x] Task 3 — LLM 叙事生成 _compose_async + MiniMax Text-01 ✅
- [x] Task 4 — 接入 Scheduler _process_narrative ✅
- [x] Task 5 — API 端点 /api/narratives + /api/narratives/latest ✅
- [x] Task 6 — 前端叙事面板 HTML+CSS+JS 轮询 ✅

**完成标志**: 世界自动生成叙事故事，前端面板实时展示。 ✅

---

## Phase 15: 前端体验增强 — 注入反馈 + 事件日志 ✅ (100%)

**目标**: 事件注入后能看到实时反馈和影响范围，导演面板增加事件历史。

- [x] Task 1 — 后端注入反馈增强 — /api/director/inject_event 返回 affected_agents + impact_summary
- [x] Task 2 — 前端事件历史面板 — 导演面板中展示最近 10 条注入事件 + 展开详情
- [x] Task 3 — 注入结果实时展示 — 注入后高亮受影响数码兽 + 弹出通知
- [x] Task 4 — 事件模板扩展 — 新增"进化事件""节日事件""遭遇事件"等预设模板

**完成标志**: 用户注入事件后能看到实时反馈和影响范围。 ✅

---

## Phase 16: 关系深度系统 — 差序格局 + 情感传播 ✅ (100%)

**目标**: 受费孝通「差序格局」理论及 ACL 2026 论文启发，将现有的四维关系向量升级为可量化的关系圈层系统，让数码兽根据亲疏远近决定合作/对抗策略。

**论文依据**: arXiv:2606.23764 "Emergent Relational Order in LLM Agent Societies: From Collective Affect to Authority Stratification" (ACL 2026)

- [x] Task 1 — `relational_circle.py` 核心模块: RelationalCircle 枚举 + AffectVector 情感向量 + RelationalDistance 关系距离分类器 ✅
- [x] Task 2 — API 端点 `/api/relations/{name}`: 返回某数码兽的完整差序格局视图（圈层分类 + 关系距离 + 情感向量）
- [x] Task 3 — 前端关系圈层可视化: 在数码兽详情侧栏展示差序格局同心圆图（Canvas 绘制）
- [x] Task 4 — 情感传播引擎: 当某数码兽情绪剧烈变化时，按关系距离衰减传播至圈内其他数码兽
- [x] Task 5 — 合作阈值集成: 在对话/战斗/组队场景中，用关系距离调节互动概率

**完成标志**: 关系系统从"分数"升级为"圈层"，差序格局可视化，情感传播可用。

---

## Phase 19: 计划持久化与上下文管理 ✅ (100%)

**目标**: LLM agent 的计划信号在写入后 1 步就衰减 4.1×（arXiv:2606.22953）。当前 `current_plan` 只存在于内存中——服务重启、记忆压缩/eviction 后计划丢失，agent 失忆。Phase 19 建立 PlanCheckpoint 系统，计划获得独立于 memory_stream 的持久化存储，支持计划恢复和历史追溯。

**论文依据**: arXiv:2606.22953 "Plans Don't Persist: Why Context Management Is Load Bearing for LLM Agents"

- [x] Task 1 — `plan_persistence.py` 核心模块: PlanCheckpoint 数据类 + PlanPersistenceEngine（checkpoint/resume/update_progress/complete/abandon/get_history/相似度检测）✅
- [x] Task 2 — 集成 DigimonAgent: plan_next() 后自动 save checkpoint；step() 开始时检测计划丢失→从 checkpoint 恢复；plan 重要性 boost (+2) ✅
- [x] Task 3 — API 端点: `GET /api/digimon/{name}/plans`（当前计划 + 历史列表）、`GET /api/digimon/{name}/plans/{plan_id}`（计划详情）✅
- [x] Task 4 — 集成测试: 28 tests PASS（create→resume→progress→complete + expire→abandon）✅
- [x] Task 5 — 前端计划状态面板: 显示当前计划进度条 + 历史计划列表（可选，进阶） ✅

**完成标志**: Agent 重启/记忆压缩后仍能恢复当前计划，计划有完整的 checkpoint→progress→complete 生命周期。

---

## Phase 20: 自演化世界模型 — WorldEvolver 框架 ✅ (100%)

**目标**: 数码兽建立自己对世界的认知模型。受 WorldEvolver (arXiv:2606.30639) 启发，通过 Episodic Memory（检索真实转移）、Semantic Memory（提取启发式规则）、Selective Foresight（过滤低置信预测）三个模块实现世界模型自演化。

**论文依据**: arXiv:2606.30639 "Self-Evolving World Models for LLM Agent Planning"

- [x] Task 1 — `world_model.py` 核心模块: WorldModel + EpisodicMemory + SemanticMemory + SelectiveForesight ✅ (38 tests)
- [x] Task 2 — 集成 DigimonAgent: step() 中捕获 pre_state + 记录情节到世界模型 ✅
- [x] Task 3 — API 端点: `GET /api/digimon/{name}/world-model`（世界观快照 + 规则库）✅
- [x] Task 4 — 前端世界模型面板: 展示 agent 学到的规则 + 预测置信度 ✅
- [x] Task 5 — 集成测试 + 端到端验证 ✅ (53 tests, verify_phase20.py 10/10)

**完成标志**: 数码兽能基于历史经验预测行动结果，规则库随经历自然演化。 ✅

---

## Phase 21: Agent 内省聚合仪表板 ✅ (100%)

**目标**: Phase 18（记忆自主）、19（计划持久化）、20（世界模型）三个系统各自独立运行，缺少统一的健康诊断视图。Phase 21 构建 `AgentInsightEngine`，聚合三大系统数据生成每个 agent 的内省报告——记忆健康评分、计划成功率、习得规则概览——一站式 Agent 自我认知仪表板。

**论文依据**: arXiv:2607.00233 "From Signals to Structure: How Memory Architecture Drives Language Emergence in LLM Agents" — 记忆架构决定了 agent 能否将交互历史转化为稳定惯例。

- [x] Task 1 — `agent_insights.py` 核心模块: AgentInsightEngine 聚合 memory_autonomy + plan_persistence + world_model 数据，生成统一内省报告 ✅
- [x] Task 2 — API 端点: `GET /api/digimon/{name}/insights` 返回内省报告（记忆健康评分 + 计划成功率 + 习得规则摘要 + 综合评分）✅
- [x] Task 3 — 前端内省面板: 在 digimon 详情侧栏新增「内省」tab，展示综合评分环 + 三维雷达图（记忆/计划/世界观）+ 各维度明细 ✅
- [x] Task 4 — 集成测试: 21 tests PASS ✅
- [x] Task 5 — 端到端验证: verify_phase21.py ✅

**完成标志**: 每只数码兽有一个统一的「内省仪表板」，一眼看清其记忆健康度、计划执行力和世界观成熟度。 ✅

---

## Phase 22: 共享记忆惯例与文化涌现 ✅ 100%

**目标**: 当多个 agent 通过持久化记忆反复交互时，自然发展出共享符号系统和文化惯例。受 arXiv:2607.00233 启发——记忆架构驱动语言涌现，persistent private notebook 的 agent 达到了最高协调率 (0.867)。Phase 18 的 Ebbinghaus 遗忘 + 复述机制已为个体记忆打下基底，Phase 22 向上一层：**群体记忆**。

**论文依据**: arXiv:2607.00233 "From Signals to Structure: How Memory Architecture Drives Language Emergence in LLM Agents"

- [x] Task 1 — `shared_conventions.py` 核心模块: ConventionDetector（检测 2+ agent 重复使用的术语/行为模式）+ ConventionPool（全局共享惯例池，每个惯例有 adoption_count + last_used + decay 曲线）+ ConventionPropagation（按社交网络传播惯例）✅ (49 tests)
- [x] Task 2 — API 端点: `GET /api/conventions`（世界共享惯例列表 + sort_by/category/limit 过滤）、`GET /api/conventions/{id}`（惯例详情 + 采用 agent 列表）、`GET /api/digimon/{name}/conventions`（某 agent 的惯例快照）✅
- [x] Task 3 — 前端文化面板: 导演面板新增「🌍 共享文化」section，显示惯例列表（term + category标签 + adoption_count + strength进度条），8秒轮询 /api/conventions ✅
- [x] Task 4 — 集成测试: ConventionDetector 检测正确性 + 传播衰减 + 去重 + 多 agent 同步 + API 端点测试 ✅ (49 条用例)
- [x] Task 5 — 端到端验证: verify_phase22.py 脚本（验证惯例涌现、传播、衰减、生命周期、API 端点）✅ (20/20 PASS)

**完成标志**: 数码兽能自发形成共享术语和行为惯例，世界中有「文化」——惯例有自己的生命周期（涌现→传播→遗忘）。908 tests total。

---

## Phase 23: 思考成本与认知能量系统 ✅ 100%

**目标**: LLM 推理本身也是一种资源消耗。受 arXiv:2607.14865 "The Energy Society" 启发——agent 的推理成本直接与生存挂钩，token 消耗能量，能量归零 = 死亡（休眠）。当前 30 只数码兽每 tick 调用 LLM 反思+规划，没有任何节制。Phase 23 引入「认知能量池」：每次 LLM 调用按 token 量扣能量，简单规则行为免费，能量耗尽后 agent 进入休眠——只做基于规则的随机移动，直到通过休息/进食/社交恢复。

**论文依据**: arXiv:2607.14865 "The Energy Society: A Simulation Environment for Studying Agent Cooperation under Survival Pressure" (2026-07-18)

- [x] Task 1 — `thinking_cost.py` 核心模块: CognitiveEnergyPool（每 agent 一个能量池 0-100，初始 100，base_drain=1/tick，LLM 调用按 token_estimate 扣额外能量）+ DormancySystem（能量 ≤ 0 进入休眠模式，跳过 LLM 调用）+ EnergyRecovery（rest: +2/tick 待机恢复，social: +5/次互动，eat: +10/次觅食）✅ (53 tests)
- [x] Task 2 — 集成 DigimonAgent.step(): 反思/计划/对话前检查能量 → 低能量跳过 LLM，使用规则 fallback；调用后记录 token cost 并扣能量；dormant agent 只执行随机移动 ✅
- [x] Task 3 — API 端点: `GET /api/digimon/{name}/energy`（能量详情 + 历史分类账）、`GET /api/energy/ledger`（世界能量总览：活跃/休眠 agent 数、平均能量、总 LLM 调用次数）✅
- [x] Task 4 — 前端能量面板: 数码兽详情侧栏新增「⚡ 认知能量」tab，显示能量条 + 休眠标记 + 最近 5 次 LLM 调用成本记录 ✅
- [x] Task 5 — 集成测试 (53 tests) + 端到端验证: verify_phase23.py（验证能量衰减/扣减/恢复/休眠/唤醒完整生命周期，45/45 PASS）✅

---

## Phase 24: 能量经济与互惠利他 ✅ 100%

**目标**: Phase 23 为每个 agent 引入了认知能量池，但 agent 之间只能各自管理自己的能量。Phase 24 在能量池之上构建 agent 间的能量经济：**互相转移/交易能量、利他行为、唤醒休眠朋友**。受生物学「互惠利他主义」启发——agent 帮助过的对象会产生「人情债」，债务随时间衰减，形成自然的回报循环。

**论文依据**: Trivers (1971) "The Evolution of Reciprocal Altruism" + Axelrod & Hamilton (1981) "The Evolution of Cooperation"

- [x] Task 1 — `economy/energy_economy.py` 核心模块: EnergyTransfer（不可变转移记录）+ ReciprocalAltruism（agent 间债务追踪+衰败）+ EnergyEconomy（转移验证/执行/机会扫描）✅ (728 行)
- [x] Task 2 — API 端点: `GET /api/economy/stats`（能量经济统计）、`GET /api/economy/transfers`（转移历史 + agent 过滤）、`GET /api/altruism/{name}`（利他评分 + 债权人/欠债人排行）✅
- [x] Task 3 — 调度器集成: 在 WorldScheduler.tick_once() 中添加 economy.step() 调用，每 tick 执行债务衰败、绝望救济、唤醒休眠好友 ✅
- [x] Task 4 — 前端经济面板: 导演面板新增「⚡ 能量经济」tab，显示转移历史、利他排行榜、活跃债务关系图 ✅
- [x] Task 5 — 集成测试 (65 条): EnergyTransfer + ReciprocalAltruism + EnergyEconomy + API 端点 ✅
- [x] Task 6 — 端到端验证: verify_phase24.py（56/56 PASS，验证捐赠/交易/唤醒/债务衰败/互惠救济/API 端点完整生命周期）✅

**完成标志**: Agent 之间可以互相帮助、产生人情债、在朋友低能量时主动回报——世界中有「利他经济」自然涌现。

---

## Phase 25: Agent 上下文质量与可靠性工程 🔄 (50%)

**目标**: Phase 21 提供个体 agent 内省（记忆/计划/世界观健康），Phase 22-24 构建了群体文化、能量、经济体系——但缺少一层**上下文质量监控**来保障所有认知系统正常运行。受 arXiv:2607.14275 "AI Agents Do Not Fail Alone: The Context Fails First" 启发，上下文工程质量是 agent 可靠性的**独立先行指标**。Phase 25 构建 ContextQualityMonitor，在每个 tick 对 agent 的上下文做快照诊断，自动生成优化建议。

**论文依据**: arXiv:2607.14275 "AI Agents Do Not Fail Alone: The Context Fails First" (2026-07-18) — Agent 不独立失败：上下文弱时 agent 漂移、幻觉、误用工具、被注入攻击。

- [x] Task 1 — `context_quality.py` 核心模块: ContextQualitySnapshot + ContextHealthMonitor（每 tick 快照：记忆鲜度/相关性/计划时效性/上下文大小/一致性评分）+ ContextOptimizer（自动生成优化建议：记忆复述/压缩/plan恢复/规则重验证）✅ (766行, 29 tests)
- [x] Task 2 — Scheduler 集成: tick_once() 中调用 context_quality.snapshot()，生成诊断日志；低健康分数时触发 optimizer 建议 ✅
- [x] Task 3 — API 端点: `GET /api/digimon/{name}/context-health`（上下文健康报告 + 历史趋势）、`GET /api/context/overview`（世界级上下文健康总览：最需要关注的 5 个 agent）✅ (已部署验证)
- [ ] Task 4 — 前端上下文健康面板: 内省仪表板新增「🔍 上下文健康」tab，显示六维雷达图（鲜度/相关性/时效性/覆盖度/大小/一致性）+ 优化建议操作按钮
- [ ] Task 5 — 集成测试 (≥25): ContextHealthMonitor + Optimizer + 边界情况
- [ ] Task 6 — 端到端验证: verify_phase25.py（20 tick 运行，验证快照准确性、诊断正确性、建议合理性）

**完成标志**: 每个 agent 拥有上下文健康评分，世界级仪表板可监控所有 agent 的上下文质量——从「盲目信任」升级为「可观测可靠」。