# 📱 手机访问部署指南

> 目标: 把数码宝贝虚拟世界部署到 Cloudflare Pages,手机装梯子后访问

## ⚠️ 前提

- ✅ 仓库已推 Gitee + GitHub
- ⏳ 你需要做 2 件事:
  1. 给 GitHub Token 加 `Contents: Read and write` 权限
  2. 登录 Cloudflare Pages 接 GitHub 仓库

## 🔑 步骤 1: 给 GitHub Token 加权限

> Token 之前能 clone 但不能 push 到空仓库,需要勾 write 权限。

1. 打开 https://github.com/settings/tokens?type=beta
2. 找到 token `github_pat_11AE437OQ...`,点 **Edit**
3. **Repository access**:
   - 选 `Only select repositories`
   - 选 `robin-shaun/digimon-world`
4. **Repository permissions** → `Contents`: 改成 **Read and write**
5. **Save**

完成后回我"Token 好了",我会重新推到 GitHub。

---

## ☁️ 步骤 2: Cloudflare Pages 接入

(等 GitHub 推完之后再做)

1. 打开 https://dash.cloudflare.com/
2. 登录(没账号用邮箱注册,免费)
3. 左侧菜单 → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**
4. 选 **GitHub** → 授权 Cloudflare 访问你的 GitHub → 选 `robin-shaun/digimon-world`
5. **Set up builds and deployments**:
   - **Project name**: `digimon-world`
   - **Production branch**: `main`
   - **Framework preset**: `None`
   - **Build command**: *(留空)*
   - **Build output directory**: `frontend`
6. 点 **Save and Deploy**

等 1-2 分钟,Cloudflare 给你一个 URL:
```
https://digimon-world-<random>.pages.dev
```

---

## 📱 步骤 3: 手机访问

1. 手机装梯子(你已经装了)
2. 浏览器打开 Cloudflare 给的 URL
3. 应该看到 Canvas 画的"无限山 + 文件岛 + 启程海滩"

---

## 🔄 后续自动部署

之后你或我每次 `git push` 到 GitHub `main` 分支:
- Cloudflare Pages 自动重新部署(约 30 秒)
- 不用手动操作

Gitee 的代码也会同步,因为我们 `origin`(Gitee) 和 `github`(GitHub) 都设了。
