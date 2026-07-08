#!/usr/bin/env bash
# ============================================================
# Phase 1 端到端验证脚本
# 作者: 星航
# 日期: 2026-07-08
# 用法: bash backend/scripts/verify_phase1.sh
# ============================================================

set -euo pipefail

# 基础 URL (cloudflared tunnel)
BASE_URL="${BASE_URL:-https://stands-infrared-pottery-promoting.trycloudflare.com}"
WS_URL="wss://stands-infrared-pottery-promoting.trycloudflare.com/ws/world"

PASSED=0
FAILED=0

# 打印结果的辅助函数
pass() {
    echo "  ✅ $1"
    ((PASSED++))
}

fail() {
    echo "  ❌ $1"
    ((FAILED++))
}

echo "============================================"
echo " Phase 1 端到端验证"
echo " 目标: ${BASE_URL}"
echo "============================================"
echo ""

# ---- a) 健康检查: GET / → 200 + version=0.1.0 ----
echo "[1/5] 健康检查 (GET /)"
HTTP_CODE=$(curl -s -o /tmp/p1_health.json -w "%{http_code}" "${BASE_URL}/")
if [[ "$HTTP_CODE" == "200" ]]; then
    VERSION=$(python3 -c "import json; print(json.load(open('/tmp/p1_health.json'))['version'])" 2>/dev/null || echo "")
    if [[ "$VERSION" == "0.1.0" ]]; then
        pass "HTTP 200, version=${VERSION}"
    else
        fail "HTTP 200 但 version='${VERSION}' (期望 0.1.0)"
    fi
else
    fail "HTTP ${HTTP_CODE} (期望 200)"
fi

# ---- b) 数码兽列表: GET /api/digimon → count >= 3 ----
echo "[2/5] 数码兽列表 (GET /api/digimon)"
HTTP_CODE=$(curl -s -o /tmp/p1_digimon_list.json -w "%{http_code}" "${BASE_URL}/api/digimon")
if [[ "$HTTP_CODE" == "200" ]]; then
    COUNT=$(python3 -c "import json; print(json.load(open('/tmp/p1_digimon_list.json'))['count'])" 2>/dev/null || echo "0")
    if [[ "$COUNT" -ge 3 ]]; then
        pass "HTTP 200, count=${COUNT} (>= 3)"
    else
        fail "HTTP 200 但 count=${COUNT} (期望 >= 3)"
    fi
else
    fail "HTTP ${HTTP_CODE} (期望 200)"
fi

# ---- c) 单只数码兽: GET /api/digimon/亚古兽 → name=亚古兽 ----
echo "[3/5] 单只数码兽 (GET /api/digimon/亚古兽)"
# URL 编码中文
ENCODED_NAME=$(python3 -c "import urllib.parse; print(urllib.parse.quote('亚古兽'))")
HTTP_CODE=$(curl -s -o /tmp/p1_agumon.json -w "%{http_code}" "${BASE_URL}/api/digimon/${ENCODED_NAME}")
if [[ "$HTTP_CODE" == "200" ]]; then
    NAME=$(python3 -c "import json; print(json.load(open('/tmp/p1_agumon.json'))['name'])" 2>/dev/null || echo "")
    if [[ "$NAME" == "亚古兽" ]]; then
        pass "HTTP 200, name=亚古兽"
    else
        fail "HTTP 200 但 name='${NAME}' (期望 亚古兽)"
    fi
else
    fail "HTTP ${HTTP_CODE} (期望 200)"
fi

# ---- d) 移动数码兽: POST /api/digimon/亚古兽/move ----
echo "[4/5] 移动数码兽 (POST /api/digimon/亚古兽/move)"
HTTP_CODE=$(curl -s -o /tmp/p1_move.json -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d '{"dx": 10, "dy": 0}' \
    "${BASE_URL}/api/digimon/${ENCODED_NAME}/move")
if [[ "$HTTP_CODE" == "200" ]]; then
    MOVE_NAME=$(python3 -c "import json; print(json.load(open('/tmp/p1_move.json'))['name'])" 2>/dev/null || echo "")
    if [[ "$MOVE_NAME" == "亚古兽" ]]; then
        pass "HTTP 200, 移动成功 (name=亚古兽)"
    else
        fail "HTTP 200 但响应异常: name='${MOVE_NAME}'"
    fi
else
    fail "HTTP ${HTTP_CODE} (期望 200)"
fi

# ---- e) WebSocket 连接测试 ----
echo "[5/5] WebSocket 连接 (wss://...//ws/world)"
# 用 python3 websockets 库尝试连接并接收第一条消息
WS_RESULT=$(python3 -c "
import asyncio, json
async def test():
    try:
        import websockets
    except ImportError:
        print('SKIP:websockets库未安装')
        return
    try:
        async with websockets.connect('${WS_URL}', open_timeout=5) as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            if data.get('type') == 'snapshot':
                print('OK:收到snapshot')
            else:
                print('OK:收到消息type=' + data.get('type', 'unknown'))
    except Exception as e:
        print(f'FAIL:{e}')
asyncio.run(test())
" 2>/dev/null || echo "FAIL:python执行异常")

if [[ "$WS_RESULT" == OK:* ]]; then
    pass "WebSocket 连接成功 (${WS_RESULT#OK:})"
elif [[ "$WS_RESULT" == SKIP:* ]]; then
    echo "  ⚠️  跳过: ${WS_RESULT#SKIP:}"
    echo "     安装: pip install websockets"
else
    fail "WebSocket 失败: ${WS_RESULT#FAIL:}"
fi

# ---- 汇总 ----
echo ""
echo "============================================"
echo " 结果: ${PASSED} 通过, ${FAILED} 失败"
echo "============================================"

# 清理临时文件
rm -f /tmp/p1_health.json /tmp/p1_digimon_list.json /tmp/p1_agumon.json /tmp/p1_move.json

if [[ "$FAILED" -eq 0 ]]; then
    echo ""
    echo "Phase 1 verify: PASSED"
    exit 0
else
    echo ""
    echo "Phase 1 verify: FAILED"
    exit 1
fi
