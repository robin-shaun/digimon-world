# 🐉 DIGIMON WORLD / 数码宝贝虚拟世界

> 肖昆 (星航) 的长期项目 —— 构建一个网页版的**数码宝贝虚拟世界**

线上地址: https://digimon-world.robin-shaun.workers.dev

## 🎯 项目愿景

这是一个**涌现式数字生命世界**。数码兽们（亚古兽、加布兽、比丘兽……）在 2D 插画风的世界里**自主生活、战斗、进化、社交**。

用户（肖昆）以**观察者 / 导演**身份进入，观看一个个故事自发地展开。

## 🧬 核心思想

- **Stanford Generative Agents (2023)** 的多智能体架构（Observe → Memory → Reflect → Plan → Act）
- **数码宝贝动画**的世界观（无限山、文件岛、进化体系、徽章、被选召的孩子）
- 当前 LLM Agent 进展（分层模型调用、长期记忆、规划、涌现行为）
- **规则即涌现杠杆**（arXiv 2607.07695）：规则设计比模型选择更决定世界行为

我们**不**做聊天机器人；我们**做**一个会自己活起来的世界。

## 📂 目录结构

```
digimon-world/
├── README.md                # 本文件
├── docs/                    # 设计文档
│   ├── DESIGN.md            # 总体设计
│   ├── ROADMAP.md           # 路线图
│   └── RESEARCH.md          # 每日深度调研
├── frontend/                # 前端 (2D PixiJS Canvas)
│   ├── index.html           # 主页面 + 导演面板
│   ├── style.css            # 暗色主题 + 动画
│   ├── main.js              # Canvas渲染 + API轮询 + 状态管理
│   ├── almanac.js            # 世界年鉴面板
│   ├── economy.js            # 能量经济面板
│   ├── stats.html           # 数据仪表盘
│   ├── battle.html          # 战斗模拟
│   ├── evolution.html       # 进化图鉴
│   └── audio.js             # 音效
├── backend/                 # Python 后端
│   ├── src/digimon_world/
│   │   ├── agents/          # 数码兽智能体 + 进化 + 对话 + 徽章
│   │   ├── memory/          # 记忆流 (MemoryStream)
│   │   ├── battle/          # 战斗引擎 + 属性克制
│   │   ├── world/           # 世界状态 + 关系 + 经济 + 灾难 + 节日 + 活力
│   │   ├── llm/             # LLM 客户端
│   │   └── api/             # FastAPI 接口
|   └── tests/               # 1376 测试
└── src/index.js             # Cloudflare Worker (API反代)
```

## 🗺️ 路线图

| Phase | 内容 | 状态 |
|------|------|------|
| **0** | 技术调研 + Stanford Agent 复现 + 项目骨架 | ✅ 完成 |
| **1** | 网页地图雏形 + 数码兽在地图上移动 | ✅ 完成 |
| **2** | Agent 自主行为循环 (Observe/Memory/Reflect/Plan/Act) | ✅ 完成 |
| **3** | 数码兽进化系统 + 战斗引擎 + 属性克制 | ✅ 完成 |
| **4** | 多智能体社交 + 派系 + 对话 + 关系追踪 | ✅ 完成 |
| **5** | 经济系统 + 灾难 + 节日 + 治疗 + 广播 + 时间线 | ✅ 完成 |
| **6** | CPM情绪演化 + 关系4D向量 + leaderboard + 显著性阈值 | ✅ 完成 |
| **7** | 记忆压缩 + 因果链日志 + 世界活力指标 | ✅ 完成 |
| **8** | 数码宝贝原作深度复刻 (进化树+黑暗四天王+属性克制+创始村) | ✅ 完成 |
| **9** | 多元宇宙 — 多世界副本 API + 种子数码兽 + 世界管理 | ✅ 完成 |
| **10** | 环境自主演化 — 昼夜+天气+生态+环境事件 | ✅ 完成 |
| **11** | 规模化 3→30+ agents + LLM 批量调用 + 涌现指标 API | ✅ 完成 |
| **12** | 跨世界联动 + 被选召的孩子 POC + 长期稳定性 | ✅ 完成 |
| **13** | 多模态 (TTS 配音 + 动画增强) + 生产加固 | ✅ 完成 |
| **14** | 世界叙事系统 — LLM 驱动故事生成 + 前端叙事面板 | ✅ 完成 |
| **15** | 导演面板增强 — 注入反馈 + 事件历史 + 模板扩展 | ✅ 完成 |
| **17** | MBTI数码兽人格系统 — 四维度人格雷达 + 人格兼容加成 | ✅ 完成 |
| **18** | 记忆健康诊断 — 艾宾浩斯遗忘 + 复述机制 | ✅ 完成 |
| **19** | 🌍 世界地图扩展 — 4000×3000 服务器大陆 + 视口滚动 | ✅ 完成 |
| **20** | 🧠 自我演化世界模型 — 规则学习 + 选择性前瞻 | ✅ 完成 |
| **21** | 📊 Agent 内省聚合仪表板 — 记忆/计划/世界观统一诊断 | ✅ 完成 |
| **22** | 🗣️ 共享记忆惯例与文化涌现 — ConventionDetector + 文化面板 | ✅ 完成 |
| **23** | ⚡ 思考成本与认知能量系统 — 能量池 + 休眠/唤醒 | ✅ 完成 |
| **24** | 💰 能量经济与互惠利他 — 转移/债务/利他排行榜 | ✅ 完成 |
| **25** | 🔍 上下文质量与可靠性工程 — 六维健康雷达 + 自动优化 | ✅ 完成 |
| **26** | 🧬 社会互动驱动的人格动态演化 — 社会影响力 + 人格转变 | ✅ 完成 |
| **27** | 🧠 知识经济与科技树 — 知识发明/引用/传播/科技树解锁 | ✅ 完成 |
| **28** | 🪞 Agent 自我认知与叙事一致性引擎 — SelfModel + ToM + 叙事一致性 | ✅ 完成 |
| **29** | 📖 世界年鉴与历史叙事 — 世界快照 + 趋势 + 名人堂 + 前端面板 | ✅ 完成 |

详细见 [`docs/ROADMAP.md`](docs/ROADMAP.md)。

## 🚀 技术栈

| 层 | 技术 |
|----|------|
| 前端 | PixiJS Canvas + 原生 JS + CSS 暗色主题 |
| 后端 | Python 3.11 + FastAPI + SQLite |
| AI | Anthropic Claude (Opus 4.8 + Haiku 4.5) via 中转 |
| 部署 | Cloudflare Workers (前端) + Cloudflare Tunnel (后端) |
- **测试**: pytest (1440 passed)

## 🚀 本地启动

```bash
# 后端
cd backend && source .venv/bin/activate
PYTHONPATH=src python -m uvicorn digimon_world.api.app:app --host 127.0.0.1 --port 8000

# 测试
cd backend && source .venv/bin/activate && python -m pytest tests/ -q
```

## 📊 当前状态

- **数码兽**: 100 只（亚古兽/加布兽/比丘兽/甲虫兽/巴鲁兽/哥玛兽/巴达兽/迪路兽/小狗兽/艾力兽 + 病毒种/数据种/自由种）
- **测试**: pytest (1543 collected)
- **部署**: Cloudflare Workers + Tunnel
- **每日调研**: 08:30 自动跑 arXiv + GitHub + 数码宝贝原作

## ⚠️ 版权声明

数码宝贝 IP 归万代 (Bandai) 所有。本项目**纯粉丝/研究用途**，不以商业为目的。

---

> 🌟 星航开发中 · 报告对象: 肖昆 · 仓库: gitee.com/robin_shaun/digimon-world
