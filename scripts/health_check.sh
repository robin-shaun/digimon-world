#!/usr/bin/env bash
# ============================================================
# digimon-world 健康检查脚本 / Health Check Script
# ============================================================
# 用法: ./scripts/health_check.sh [BASE_URL]
# 默认 BASE_URL=http://localhost:8000
# 退出码: 0=健康, 1=不可达/异常
# ============================================================

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
ENDPOINT="${BASE_URL}/api/health/perf"
TIMEOUT=10

echo "🔍 Checking health at ${ENDPOINT}..."

# 使用 curl 调用健康检查端点
RESP=$(curl -sS --max-time "${TIMEOUT}" -w "\n%{http_code}" "${ENDPOINT}" 2>/dev/null) || {
    echo "❌ UNHEALTHY: Backend unreachable at ${BASE_URL}"
    exit 1
}

# 提取 HTTP 状态码 (最后一行)
HTTP_CODE=$(echo "${RESP}" | tail -1)
BODY=$(echo "${RESP}" | sed '$d')

if [ "${HTTP_CODE}" != "200" ]; then
    echo "❌ UNHEALTHY: HTTP ${HTTP_CODE}"
    echo "${BODY}" | head -20
    exit 1
fi

# 解析 JSON (需要 python3)
if command -v python3 &>/dev/null; then
    echo "${BODY}" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    pid = data.get('pid', '?')
    uptime = data.get('uptime_seconds', 0)
    mem = data.get('memory', {}).get('rss_mb', '?')
    db = data.get('database', {}).get('size_mb', '?')
    agents = data.get('world', {}).get('agent_count', '?')
    memories = data.get('world', {}).get('total_memories', '?')
    events = data.get('world', {}).get('event_count', '?')
    ws = data.get('world', {}).get('ws_connections', '?')
    tick = data.get('world', {}).get('clock_tick', '?')
    print(f'✅ HEALTHY  PID={pid}  uptime={uptime:.0f}s  mem={mem}MB  db={db}MB')
    print(f'   agents={agents}  memories={memories}  events={events}  ws={ws}  tick={tick}')
except Exception as e:
    print(f'✅ HEALTHY (HTTP 200, raw JSON below)')
    print(sys.stdin.read())
" || {
        echo "✅ HEALTHY (HTTP 200, python3 unavailable for JSON parse)"
        echo "${BODY}" | head -10
    }
else
    echo "✅ HEALTHY (HTTP 200)"
    echo "${BODY}" | head -10
fi

exit 0
