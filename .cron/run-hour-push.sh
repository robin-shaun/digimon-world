#!/bin/bash
# digimon-world hour-push 启动脚本
# 由 22:00 cron 派发,跑 Phase 2 推进
# 约束: 4 小时超时、429 三次就停、不切备用 key
set -u

cd ~/projects/digimon-world

# 写出错码到日志,方便下次 cron 检查
LOG=~/projects/digimon-world/.cron/hour-push-$(date +%Y%m%d-%H%M).log
exec > "$LOG" 2>&1

echo "[hour-push] 启动 $(date)"

# 检查主 key 状态
if [ -z "${ANTHROPIC_AUTH_TOKEN:-}" ]; then
    source ~/.bashrc
fi

echo "[hour-push] TOKEN 前缀: ${ANTHROPIC_AUTH_TOKEN:0:15}"
echo "[hour-push] BASE: ${ANTHROPIC_BASE_URL:-default}"

# 跑 claude,带超时(4h)
timeout 14400 claude -p --model claude-3-5-haiku-20241022 --effort medium "$(cat <<'PROMPT'
你是 digimon-world hour-push 任务。仓库 ~/projects/digimon-world,当前 commit 见 git log -1。

【上下文】
- Phase 0 + Phase 1 已闭环
- Phase 2 第一项 MemoryStream 已实现并 commit (memory/memory_stream.py)
- 部署: https://digimon-world.robin-shaun.workers.dev/

【本任务目标】
推进 Phase 2 后面的项,按 ROADMAP.md 顺序:
1. Reflector: 触发反思 → 生成高级抽象(reflection 类型记忆),importance 用 LLM 评
2. Planner: 高层+子计划+行动三层(可以先 stub,Phase 2 末尾填充)
3. LLM 客户端: 中转 API 调用(opus 做反思/计划,haiku 做日常)
4. DigimonAgent 主循环(Observe → Memory → Reflect → Plan → Act)
5. 测试(每个新模块都有 pytest)

【工作风格】
- 每个文件 ≤ 200 行
- 中文注释、英文代码
- 不破坏现有测试
- 复用 Phase 1 的 WorldState 单例模式
- 复跑 pytest 全过再 commit

【额度约束】
- 每次调用尽量小,只读必要文件
- 429 出现 3 次立即停,写报告(不要切备用 key)
- 每完成 1 个模块就 commit 1 次,推送 Gitee

【时间约束】
4 小时(14400s)超时,到点会 SIGTERM,你来之前已经 commit 的不算白费。
PROMPT
)" &
CLAUDE_PID=$!

echo "[hour-push] claude PID=$CLAUDE_PID,LOG=$LOG"

# 后台 watchdog
(
    sleep 14400
    if kill -0 $CLAUDE_PID 2>/dev/null; then
        echo "[hour-push] watchdog: 4h 到,杀 claude PID=$CLAUDE_PID"
        kill -TERM $CLAUDE_PID
        sleep 5
        kill -KILL $CLAUDE_PID 2>/dev/null
    fi
) &
WD_PID=$!

wait $CLAUDE_PID
EXIT=$?
kill $WD_PID 2>/dev/null

echo "[hour-push] claude 退出,exit=$EXIT,$(date)"
echo "[hour-push] done"
