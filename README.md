# 🐉 DIGIMON WORLD / 数码宝贝虚拟世界

> 肖昆 (星航) 的长期项目 —— 构建一个网页版的**数码宝贝虚拟世界**

## 🎯 项目愿景

这是一个**涌现式数字生命世界**。数码兽们(亚古兽、加布兽……)在 2D 插画风的世界里**自主生活、战斗、进化、社交**。

用户(肖昆)先以**观察者 / 导演**身份进入,观看一个个故事自发地展开。

## 🧬 核心思想

- **Stanford Generative Agents (2023)** 的多智能体架构(Observe → Memory → Reflect → Plan → Act)
- **数码宝贝动画**的世界观(无限山、文件岛、进化体系、徽章、被选召的孩子)
- 当前 LLM Agent 进展(分层模型调用、长期记忆、规划)

我们**不**做聊天机器人;我们**做**一个会自己活起来的世界。

## 📂 目录结构

```
digimon-world/
├── README.md                # 本文件
├── docs/                    # 设计文档
│   ├── DESIGN.md            # 总体设计
│   ├── ROADMAP.md           # 路线图
│   ├── RESEARCH.md          # 调研笔记
│   └── DEPLOY_CLOUDFLARE_PAGES.md
├── frontend/                # 前端(2D 插画) - Cloudflare Pages 部署这个目录
│   ├── index.html
│   ├── style.css
│   ├── main.js
│   ├── 404.html
│   ├── package.json         # 告诉 Cloudflare 这是静态站
│   └── _headers/_redirects  # Cloudflare 配置
├── backend/                 # Python 后端(Phase 1+)
│   ├── pyproject.toml
│   ├── src/digimon_world/   # 核心代码
│   │   ├── world/
│   │   ├── agents/          # 数码兽智能体
│   │   ├── memory/          # 记忆流
│   │   ├── battle/
│   │   ├── evolution/
│   │   └── api/             # FastAPI 接口
│   └── tests/
└── .gitignore
```

## 🚀 启动(规划中,本仓库尚未实现)

```bash
# 后端 (Phase 1+)
cd backend && pip install -e .
uvicorn digimon_world.api.app:app --reload

# 前端
cd frontend && python -m http.server 8080
# 或者直接用 Cloudflare Pages 部署(见 docs/DEPLOY_CLOUDFLARE_PAGES.md)
```

## 🗺️ 路线图(分阶段)

| Phase | 内容 | 状态 |
|------|------|------|
| **0** | 技术调研 + Stanford Agent 复现 + 项目骨架 | 🔄 进行中 |
| **1** | 网页地图雏形 + 数码兽在地图上移动 | ⏳ |
| **2** | Agent 自主行为循环(Observe/Memory/Reflect/Plan/Act) | ⏳ |
| **3** | 数码兽进化系统 + 战斗 | ⏳ |
| **4** | 多智能体社交、剧情涌现、观察者 UI | ⏳ |

详细见 [`docs/ROADMAP.md`](docs/ROADMAP.md)。

## ⚠️ 版权声明

数码宝贝 IP 归万代(Bandai)所有。本项目**纯粉丝/研究用途**,不以商业为目的,所有相关 IP 的版权归原作方。

---

> 🌟 星航开发中 · 报告对象: 肖昆 · 仓库: gitee.com/robin_shaun/digimon-world
