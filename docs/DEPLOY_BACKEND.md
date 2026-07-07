# 后端部署到公网方案

## 快速开始

一行命令, 5 分钟把本机 FastAPI 暴露到公网:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

运行后终端会输出一个临时域名 `https://xxx.trycloudflare.com`, 前端把 `API_BASE` 改成这个地址即可联调。

---

## 背景

| 组件 | 当前状态 |
|------|----------|
| 后端 | FastAPI, 跑在本机 `127.0.0.1:8000` |
| 前端 | 已部署到 `https://digimon-world.robin-shaun.workers.dev/` |
| 问题 | 浏览器从 HTTPS 页面 fetch `http://127.0.0.1:8000` → CORS 拦截 + Mixed Content |

核心需求: 把后端暴露为一个 HTTPS 公网地址, 让 Workers 上的前端能正常请求。

---

## 决策点

| 问题 | 回答 |
|------|------|
| 真实需求是什么? | **当前**: 开发联调, 跑通前后端; **未来**: 7x24 生产可用 |
| 哪个方案最快? | Cloudflare Tunnel 临时模式, < 5 分钟 |
| 哪个最稳定? | Cloudflare Tunnel + 自定义域名 (守护进程模式) |
| 哪个最省? | Cloudflare Tunnel 免费; token 成本取决于 AI API 调用量, 与部署方案无关 |

---

## 方案对比

### 1. Cloudflare Tunnel (推荐)

**原理**: 本机运行 `cloudflared` 守护进程, 它主动与 Cloudflare 边缘建立出站连接 (不需要开放入站端口), Cloudflare 将公网流量通过这条隧道转发到本机服务。

**优点**:
- 零配置防火墙 — 不需要公网 IP、端口映射
- 自带 HTTPS, 证书自动管理
- 免费, 无流量限制
- 临时模式一行命令即用; 生产模式可绑自定义域名
- 与前端同在 Cloudflare 生态, 延迟最优

**缺点**:
- 临时域名每次重启会变 (需重新配置前端)
- 稳定运行依赖本机不关机、不断网

**适用场景**: 开发联调 (临时域名) / 长期生产 (自定义域名 + systemd 守护进程)

**配置步骤**:

```bash
# 1. 安装 cloudflared (macOS)
brew install cloudflared

# Linux (Debian/Ubuntu)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb

# 2. 临时模式 — 立即可用, 无需登录
cloudflared tunnel --url http://127.0.0.1:8000
# 终端输出: https://xxx.trycloudflare.com

# 3. 生产模式 — 绑定自定义域名
cloudflared tunnel login                    # 浏览器授权
cloudflared tunnel create digimon-api       # 创建命名隧道
cloudflared tunnel route dns digimon-api api.digimon.example.com  # 绑域名
cloudflared tunnel run digimon-api          # 启动
```

**费用**: 免费 (Cloudflare Zero Trust Free Plan, 无流量上限)

---

### 2. Cloudflare Workers 反代

**原理**: 在 Worker 中编写 JS 代码, 将请求转发到后端。但由于后端跑在本机, Worker 无法直达 `127.0.0.1`, 实质上还是需要后端先暴露公网 — 等于套了一层没用的中间层。若要完全跑在 Worker 内, 需把 Python 后端重写为 JS/TS。

**优点**:
- 全球边缘节点, 延迟极低
- 无服务器, 无需运维

**缺点**:
- Python → JS 重写工作量大, 不现实
- Worker 运行时限制: 无文件系统、内存 128MB、CPU 时间 30s
- 依赖 (如 LangChain / 向量库) 无法在 Worker 环境运行

**适用场景**: 纯前端逻辑或轻量 API 网关; **不适合**我们的 AI 后端

**费用**: Free Plan 10 万次/天; Paid $5/月起

---

### 3. 国内云厂商 (阿里云 / 腾讯云 Serverless)

**原理**: 将 FastAPI 打包为 Docker 镜像, 部署到云厂商的 Serverless 容器平台 (如阿里云 FC、腾讯云 SCF)。

**优点**:
- 弹性伸缩, 按调用计费
- 国内访问延迟低

**缺点**:
- 镜像打包、配置网关、域名备案流程繁琐
- 冷启动 3-10s, AI 场景体验差
- 国内域名需 ICP 备案 (≥ 2 周)
- 调试链路长, 日志分散

**适用场景**: 面向国内用户的生产环境; **不推荐初期联调阶段**

**费用**: 按量付费, 小规模 < ¥10/月; 备案域名另计

---

### 4. ngrok / frp

**原理**: 内网穿透经典方案。ngrok 商业化 SaaS, frp 自建服务端。客户端在本机建立到中继服务器的隧道, 公网流量经中继转发到本机。

**优点**:
- 成熟稳定, 社区资源多
- ngrok 提供 Web 调试面板 (请求回放)

**缺点**:
- ngrok 免费版: 随机域名 + 限速 (40 连接/分钟) + 8 小时过期
- frp 需要自有公网服务器做中继
- 相比 Cloudflare Tunnel 多一跳延迟、多一个故障点

**适用场景**: 已有 ngrok 付费账号或自有 VPS 的团队

**费用**: ngrok Free 免费但限制多; Pro $10/月; frp 需自备 VPS (≥ ¥30/月)

---

## 方案总结

| 方案 | 上手速度 | 稳定性 | 费用 | 推荐度 |
|------|----------|--------|------|--------|
| Cloudflare Tunnel | ⚡ 5 分钟 | ⭐⭐⭐⭐ | 免费 | ✅ 强烈推荐 |
| Workers 反代 | ❌ 需重写 | ⭐⭐⭐⭐⭐ | $5/月 | ❌ 不适用 |
| 国内云 Serverless | 🐢 1-2 天 | ⭐⭐⭐⭐ | ¥10+/月 | ⚠️ 后期可选 |
| ngrok / frp | ⚡ 10 分钟 | ⭐⭐⭐ | $0-10/月 | ⚠️ 备选 |

---

## 推荐路径

### Phase 1 — 现在 (开发联调)

使用 **Cloudflare Tunnel 临时模式**, 5 分钟搞定:

1. 安装 `cloudflared`
2. 运行 `cloudflared tunnel --url http://127.0.0.1:8000`
3. 拿到临时域名, 前端 `API_BASE` 指向它
4. 联调完成

### Phase 2+ — 未来 (持续可用)

升级到 **Cloudflare Tunnel + 自定义域名**:

1. `cloudflared tunnel login` 绑定 Cloudflare 账号
2. 创建命名隧道, 绑定子域名 (如 `api.digimon.robin-shaun.com`)
3. 配置 systemd 服务, 开机自启
4. 前端写死自定义域名, 不再变动

---

## 待用户决策

请确认以下 3 个问题 (yes/no):

1. **我去装一下 cloudflared, 跑一个临时 tunnel 行不行?**
   → yes 的话我给你逐步操作指引

2. **你的 API 中转需要细化 CORS 配置吗? (当前后端是 `allow_origins=["*"]`)**
   → 临时联调 `*` 没问题; 生产建议收窄为前端域名

3. **后期想不想绑自定义域名 (如 `api.digimon.robin-shaun.com`) ?**
   → yes 的话需要你在 Cloudflare 有一个托管域名, 我来配 DNS 记录
