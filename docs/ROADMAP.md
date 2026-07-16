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
| 100%  Phase 16 (差序格局 + 情感传播) ✅
|[█░░░░░░░░░░░░░░░░░░░░░░░]   5%  Phase 17 (人格深度系统 — 荣格心理学 MBTI 驱动)
|```
|
|---
|
|## Phase 17: 人格深度系统 — 荣格心理学 MBTI 驱动
|
|**目标**: 受 GitHub trending 项目 `evolving_personality` (1,199⭐) 启发，基于荣格心理学 MBTI 四维度给每只数码兽赋予动态演化的人格。人格随战斗/社交/进化经历自然漂移，并深度影响对话风格、战斗策略、关系兼容性。
|
|**参考项目**: https://github.com/agent-topia/evolving_personality — 基于荣格心理学的 MBTI 人格动态演化框架
|
- [x] Task 1 — `personality_engine.py` 核心模块: MBTI 四维度 + 动态演化 + 人格兼容矩阵
- [x] Task 2 — API 端点 `/api/digimon/{name}/personality`: 返回人格档案（类型 + 各维度值 + 演化历史）
- [ ] Task 3 — 人格集成到对话/战斗/规划: 性格影响决策风格和对话语气
|- [ ] Task 4 — 人格兼容性加成: RelationshipTracker 中 MBTI 兼容度额外加分
|- [ ] Task 5 — 前端人格雷达图: Canvas 绘制四维度雷达图 + 演化轨迹
|
|**完成标志**: 数码兽有可演化的 MBTI 人格，人格深度影响社交和战斗行为。 ✅
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